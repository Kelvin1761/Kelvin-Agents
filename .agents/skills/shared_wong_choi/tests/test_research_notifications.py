from __future__ import annotations

import json
import multiprocessing
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.research_notifications import (
    NotificationError, ResearchTelegramOutbox, TelegramRoute,
)
from shared_wong_choi.research_registry import ExperimentRegistry
from shared_wong_choi.research_index import record_review
from shared_wong_choi.research_presentation import prepare_review_presentation
from test_research_presentation import receipt
from test_research_index import clock_args, rehash
from test_research_registry import spec


SENT = {"ok": True, "status": "sent", "sent_parts": 1, "sent_targets": 1}


def route(**changes):
    return TelegramRoute(**{**dict(token="123456:dummy-secret", primary_chat_id="98765",
                                  authorized_chat_id="98765", enabled=True), **changes})


def fixture(tmp_path, *, config=None, run=None):
    path = receipt(tmp_path)
    root = tmp_path / "outbox"
    root.mkdir()
    helper = tmp_path / "notifier.py"
    helper.write_text("import json; print(json.dumps(" + repr(SENT) + "))\n")
    calls = []
    def fake_run(args, **kwargs):
        # Assertion failure output must not dump unrelated host environment.
        pinned = ("TELEGRAM_CHAT_ID", "TELEGRAM_BOT_TOKEN", "WC_NOTIFY_TELEGRAM_CHAT",
                  "WC_NOTIFY_TELEGRAM_TOKEN", "WC_NOTIFY_TELEGRAM_EXTRA")
        calls.append((args, {**kwargs, "env": {key: kwargs["env"][key] for key in pinned}}))
        if run:
            return run(args, **kwargs)
        return subprocess.CompletedProcess(args, 0, json.dumps(SENT), "")
    box = ResearchTelegramOutbox(root, config or route(), helper_path=helper, run=fake_run)
    return path, box, calls


def test_sent_once_across_recreated_dispatchers_and_no_model_authority(tmp_path):
    path, box, calls = fixture(tmp_path)
    first = box.dispatch(path)
    second = ResearchTelegramOutbox(box.root, route(), helper_path=box.helper_path,
                                    run=lambda *a, **k: pytest.fail("duplicate send")).dispatch(path)
    assert first["status"] == "sent" and second["status"] == "already_sent"
    assert len(calls) == 1
    assert second["transport_reported_sent"] is True
    assert second["delivery_confirmed"] is False  # helper supplies no message ID or independent receipt
    assert second["model_promotion_allowed"] is False
    assert len(list(box.root.rglob("intent.json"))) == len(list(box.root.rglob("outcome.json"))) == 1


def test_storage_summary_is_bound_to_outbox_without_widening_authority(tmp_path, monkeypatch):
    from test_research_presentation import storage_review
    (tmp_path / "review").mkdir()
    _, _, _, review, path = storage_review(tmp_path / "review", monkeypatch)
    _, box, calls = fixture(tmp_path / "box")
    kwargs = {"review_summary_path": review.report_path}
    assert box.inspect(path, **kwargs)["status"] == "not_attempted"
    assert not calls and not list(box.root.rglob("intent.json"))
    assert box.dispatch(path, **kwargs)["status"] == "sent"
    assert box.inspect(path, **kwargs)["status"] == "already_sent"
    assert box.dispatch(path, **kwargs)["delivery_confirmed"] is False
    assert len(calls) == 1
    args = calls[0][0]
    text = args[args.index("--message") + 1]
    assert "儲存健康：需留意（已核實時間點快照）" in text
    assert str(review.report_path) not in text
    # Same review without the bound storage proof is a payload conflict, not a retry.
    with pytest.raises(NotificationError, match="conflict"):
        box.dispatch(path)
    assert len(calls) == 1


def test_liveness_summary_is_bound_to_outbox_without_exposing_local_paths(tmp_path):
    from test_research_presentation import liveness_review
    (tmp_path / "review").mkdir()
    _, _, _, review, path = liveness_review(tmp_path / "review")
    _, box, calls = fixture(tmp_path / "box")

    result = box.dispatch(path, review_summary_path=review.report_path)

    assert result["status"] == "sent"
    assert result["delivery_confirmed"] is False
    assert len(calls) == 1
    args = calls[0][0]
    text = args[args.index("--message") + 1]
    assert "運行存活：來源已核實（運行 1／未核實 0／非存活 0）" in text
    assert str(review.report_path) not in text
    assert "唔代表批准部署、下注或模型升級" in text
    # Same review without the bound liveness proof is a payload conflict, not a retry.
    with pytest.raises(NotificationError, match="conflict"):
        box.dispatch(path)
    assert len(calls) == 1


@pytest.mark.parametrize("change,status", [
    ({"enabled": False}, "disabled"),
    ({"token": ""}, "not_configured"),
    ({"authorized_chat_id": ""}, "unauthorized_route"),
    ({"primary_chat_id": "other-chat"}, "unauthorized_route"),
    ({"primary_chat_id": "@channel", "authorized_chat_id": "@channel"}, "unauthorized_route"),
])
def test_no_dispatch_intent_or_send_without_enabled_pinned_authorized_route(tmp_path, change, status):
    path, box, calls = fixture(tmp_path, config=route(**change))
    assert box.dispatch(path)["status"] == status
    assert not list(box.root.rglob("*.json")) and not calls


def test_process_environment_cannot_widen_or_change_recipient(tmp_path, monkeypatch):
    path, box, calls = fixture(tmp_path)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "other")
    monkeypatch.setenv("WC_NOTIFY_TELEGRAM_EXTRA", "reader-one,reader-two")
    box.dispatch(path)
    args, kwargs = calls[0]
    assert args[args.index("--audience") + 1] == "primary"
    assert kwargs["env"]["TELEGRAM_CHAT_ID"] == "98765"
    assert kwargs["env"]["WC_NOTIFY_TELEGRAM_CHAT"] == "98765"
    assert kwargs["env"]["TELEGRAM_BOT_TOKEN"] == "123456:dummy-secret"
    assert kwargs["env"]["WC_NOTIFY_TELEGRAM_EXTRA"] == ""
    assert "dummy-secret" not in repr(args)
    records = "".join(p.read_text() for p in box.root.rglob("*.json"))
    assert "dummy-secret" not in records and "98765" not in records
    assert "dummy-secret" not in repr(route())


def test_process_disable_switch_is_respected_before_claim(tmp_path, monkeypatch):
    path, box, calls = fixture(tmp_path)
    monkeypatch.setenv("WC_TELEGRAM_DISABLE", "true")
    assert box.dispatch(path)["status"] == "disabled"
    assert not calls and not list(box.root.rglob("*.json"))


@pytest.mark.parametrize("reply", [
    {"ok": True, "status": "dry_run", "sent_parts": 1},
    {"ok": True, "status": "disabled", "sent_parts": 0},
    {"ok": False, "status": "request_failed", "sent_parts": 0, "error": "SECRET"},
    {"ok": False, "status": "partial_failure", "sent_parts": 1, "sent_targets": 0},
    {**SENT, "sent_targets": 2}, {**SENT, "sent_parts": True},
    {**SENT, "sent_parts": 2}, {**SENT, "ok": 1}, {"ok": True},
])
def test_uncertain_disabled_partial_or_unbound_reply_never_autoretries(tmp_path, reply):
    path, box, calls = fixture(tmp_path, run=lambda args, **k: subprocess.CompletedProcess(args, 0, json.dumps(reply), ""))
    assert box.dispatch(path)["status"] == "reconcile_required"
    assert box.dispatch(path)["status"] == "reconcile_required"
    assert len(calls) == 1
    assert "SECRET" not in "".join(p.read_text() for p in box.root.rglob("*.json"))


@pytest.mark.parametrize("fault", ["timeout", "invalid_json", "nonzero"])
def test_transport_exception_or_bad_process_reply_is_not_a_safe_retry(tmp_path, fault):
    def failed(args, **kwargs):
        if fault == "timeout":
            raise subprocess.TimeoutExpired(args, 10, stderr="SECRET")
        return subprocess.CompletedProcess(args, 1 if fault == "nonzero" else 0,
                                           json.dumps(SENT) if fault == "nonzero" else "SECRET", "SECRET")
    path, box, calls = fixture(tmp_path, run=failed)
    assert box.dispatch(path)["status"] == "reconcile_required"
    assert box.dispatch(path)["status"] == "reconcile_required"
    assert len(calls) == 1
    assert "SECRET" not in "".join(p.read_text() for p in box.root.rglob("*.json"))


def test_concurrent_dispatches_only_one_transport_call(tmp_path):
    path, box, calls = fixture(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: box.dispatch(path), range(4)))
    assert len(calls) == 1
    assert sum(r["status"] == "sent" for r in results) == 1
    assert all(r["status"] in {"sent", "already_sent", "reconcile_required"} for r in results)


@pytest.mark.parametrize("boundary", ["before_send", "after_send"])
def test_real_worker_crash_never_repeats_possible_send(tmp_path, boundary):
    path, box, _ = fixture(tmp_path)
    sent_marker = tmp_path / "sent-marker"
    def worker():
        def crash(args, **kwargs):
            if boundary == "after_send":
                sent_marker.write_text("fake transport called")
            os._exit(77)
        child = ResearchTelegramOutbox(box.root, route(), helper_path=box.helper_path, run=crash)
        child.dispatch(path)
    process = multiprocessing.get_context("fork").Process(target=worker)
    process.start()
    process.join(10)
    if process.is_alive():
        process.kill()
        process.join()
        pytest.fail("crash fixture timed out")
    assert process.exitcode == 77
    assert sent_marker.exists() == (boundary == "after_send")
    result = box.dispatch(path)
    assert result["status"] == "reconcile_required"


def test_changed_snapshot_or_authorized_route_cannot_reuse_original_intent(tmp_path):
    path, box, calls = fixture(tmp_path)
    box.dispatch(path)
    store = ExperimentRegistry(tmp_path / "registry")
    store.append(replace(spec(), record_id=spec().record_id + "-new"))
    options = clock_args()
    original = json.loads(path.read_text())
    new_path = record_review(root=tmp_path / "new-reviews", registry_root=store.root,
                             clock_inputs=options, request_id=original["request_id"])["path"]
    with pytest.raises(NotificationError, match="conflict"):
        box.dispatch(new_path)
    other = ResearchTelegramOutbox(box.root, route(primary_chat_id="222", authorized_chat_id="222"),
                                   helper_path=box.helper_path, run=box.run)
    with pytest.raises(NotificationError, match="conflict"):
        other.dispatch(path)
    assert len(calls) == 1


@pytest.mark.parametrize("fault", ["hash", "rehash_outcome_identity", "symlink", "oversized"])
def test_invalid_delivery_evidence_blocks_resend(tmp_path, fault):
    path, box, calls = fixture(tmp_path)
    box.dispatch(path)
    target = next(box.root.rglob("outcome.json"))
    payload = json.loads(target.read_text())
    if fault == "hash":
        payload["status"] = "invented"
        target.write_text(json.dumps(payload))
    elif fault == "rehash_outcome_identity":
        payload["intent_hash"] = "a" * 64
        rehash(payload)
        target.write_text(json.dumps(payload))
    elif fault == "symlink":
        moved = tmp_path / "moved.json"
        target.rename(moved)
        target.symlink_to(moved)
    else:
        target.write_bytes(b" " * 65537)
    with pytest.raises((NotificationError, RuntimeError)):
        box.dispatch(path)
    assert len(calls) == 1


def test_missing_outbox_root_never_creates_storage_or_sends(tmp_path):
    path, box, calls = fixture(tmp_path)
    box.root.rmdir()
    with pytest.raises(NotificationError):
        box.dispatch(path)
    assert not calls and not box.root.exists()


def test_real_local_helper_process_without_network(tmp_path):
    path, box, _ = fixture(tmp_path)
    box.helper_path.write_text(
        "import json,os,sys\n"
        "assert os.environ['TELEGRAM_CHAT_ID']=='98765'\n"
        "assert os.environ['WC_NOTIFY_TELEGRAM_EXTRA']==''\n"
        "assert sys.argv[sys.argv.index('--audience')+1]=='primary'\n"
        "text=sys.argv[sys.argv.index('--message')+1]\n"
        "assert '未發送 Telegram' not in text and '本機預覽' not in text\n"
        "assert '唔代表批准' in text\n"
        "print(json.dumps(" + repr(SENT) + "))\n"
    )
    real = ResearchTelegramOutbox(box.root, route(), helper_path=box.helper_path)
    assert real.dispatch(path)["status"] == "sent"


def test_duplicate_json_keys_cannot_be_a_success_acknowledgement(tmp_path):
    raw = '{"ok":false,"ok":true,"status":"sent","sent_parts":1,"sent_targets":1}'
    path, box, calls = fixture(tmp_path, run=lambda args, **k: subprocess.CompletedProcess(args, 0, raw, ""))
    assert box.dispatch(path)["status"] == "reconcile_required"
    assert box.dispatch(path)["status"] == "reconcile_required"
    assert len(calls) == 1


def test_dangling_outcome_symlink_blocks_before_any_send(tmp_path):
    path, box, calls = fixture(tmp_path)
    key = prepare_review_presentation(path)["telegram"]["dedup_key"]
    folder = box.root / "au" / key
    folder.mkdir(parents=True)
    (folder / "outcome.json").symlink_to(tmp_path / "missing")
    with pytest.raises(RuntimeError):
        box.dispatch(path)
    assert not calls and not (folder / "intent.json").exists()


@pytest.mark.parametrize("boundary", ["intent_fsync", "outcome_write"])
def test_storage_failure_after_claim_never_causes_automatic_resend(tmp_path, monkeypatch, boundary):
    import shared_wong_choi.research_notifications as notifications
    path, box, calls = fixture(tmp_path)
    if boundary == "intent_fsync":
        original = notifications._sync_directory
        def failed(folder):
            if (folder / "intent.json").exists():
                raise OSError("simulated sync failure")
            original(folder)
        monkeypatch.setattr(notifications, "_sync_directory", failed)
    else:
        original = notifications._create
        def failed(target, payload):
            if target.name == "outcome.json":
                raise OSError("simulated disk full")
            return original(target, payload)
        monkeypatch.setattr(notifications, "_create", failed)
    with pytest.raises(OSError):
        box.dispatch(path)
    monkeypatch.undo()
    assert box.dispatch(path)["status"] == "reconcile_required"
    assert len(calls) == (0 if boundary == "intent_fsync" else 1)


def test_changed_receipt_after_scope_check_is_blocked_before_intent(tmp_path):
    path, box, calls = fixture(tmp_path)
    with pytest.raises(NotificationError, match="scope verification"):
        box.dispatch(path, expected_receipt_hash="f" * 64)
    assert not calls and not list(box.root.rglob("intent.json"))
