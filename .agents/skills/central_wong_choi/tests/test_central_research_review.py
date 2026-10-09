from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PACKAGE_ROOT / "scripts"
REPO_ROOT = PACKAGE_ROOT.parents[2]
SHARED_ROOT = REPO_ROOT / ".agents" / "skills" / "shared_wong_choi"
sys.path.insert(0, str(SCRIPTS))

import central_research_review as review_module  # noqa: E402
from central_research_review import (  # noqa: E402
    CONTRACT_PATH,
    _write_run,
    initialize_review_state,
    load_runtime_contract,
    run_review_pass,
    review_runtime_status,
)
from shared_wong_choi.contracts import Domain  # noqa: E402
from shared_wong_choi.research_runner import ResearchDisposition  # noqa: E402


NOW = datetime(2026, 9, 19, 14, 5, tzinfo=timezone.utc)


def _roots(tmp_path: Path) -> dict:
    roots = {
        "repo_root": tmp_path / "repo",
        "state_root": tmp_path / "hot",
        "warm_root": tmp_path / "warm",
        "production_lock_paths": (tmp_path / "locks" / "domain.lock",),
    }
    roots["repo_root"].mkdir()
    roots["warm_root"].mkdir()
    return roots


def _payloads(path: Path) -> dict[str, dict]:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as database:
        return {
            table: json.loads(
                database.execute(f"SELECT payload FROM {table} WHERE id=1").fetchone()[0]
            )
            for table in (
                "cursor_state",
                "racing_sample_state",
                "storage_evidence_state",
                "liveness_evidence_state",
            )
        }


def test_contract_pins_all_four_frozen_rulers_by_exact_bytes() -> None:
    contract = load_runtime_contract()

    assert tuple(contract.domains) == ("au", "hkjc", "tennis", "nba")
    assert contract.evaluation_release_commit == (
        "297a293e6e00f6dab2ef17e59db13abd9a3b8526"
    )
    assert contract.model_promotion_allowed is False
    assert contract.telegram_delivery_confirmed is False
    for name, binding in contract.domains.items():
        source = SHARED_ROOT / "resources" / "evaluation_rulers" / f"{binding.ruler_id}.json"
        assert hashlib.sha256(source.read_bytes()).hexdigest() == binding.ruler_digest
        assert binding.domain is Domain(name)
        assert binding.model_release_id.startswith(f"wc:{name}:model-release:")


def test_explicit_initialization_creates_four_fully_bound_hot_cursors(
    tmp_path: Path,
) -> None:
    roots = _roots(tmp_path)

    result = initialize_review_state(**roots)

    assert result["status"] == "initialized"
    assert result["model_promotion_allowed"] is False
    assert result["telegram_delivery_confirmed"] is False
    for domain in Domain:
        path = roots["state_root"] / "research-review-cursors" / f"{domain.value}.sqlite3"
        payloads = _payloads(path)
        assert set(payloads) == {
            "cursor_state",
            "racing_sample_state",
            "storage_evidence_state",
            "liveness_evidence_state",
        }
        assert all(item["config"]["domain"] == domain.value for item in payloads.values())
        assert all(item["model_promotion_allowed"] is False for item in payloads.values())
        assert payloads["cursor_state"]["telegram_delivery_confirmed"] is False
        assert payloads["liveness_evidence_state"]["queue_mutation_allowed"] is False


def test_exact_reinitialization_is_read_only_but_changed_binding_fails_closed(
    tmp_path: Path,
) -> None:
    roots = _roots(tmp_path)
    initialize_review_state(**roots)
    cursor_root = roots["state_root"] / "research-review-cursors"
    before = {path.name: path.read_bytes() for path in cursor_root.glob("*.sqlite3")}

    repeated = initialize_review_state(**roots)

    assert repeated["status"] == "verified"
    assert {path.name: path.read_bytes() for path in cursor_root.glob("*.sqlite3")} == before
    other_warm = tmp_path / "other-warm"
    other_warm.mkdir()
    with pytest.raises(ValueError, match="configuration changed"):
        initialize_review_state(**{**roots, "warm_root": other_warm})
    assert {path.name: path.read_bytes() for path in cursor_root.glob("*.sqlite3")} == before


def test_ordinary_pass_never_initializes_missing_cursors(tmp_path: Path) -> None:
    roots = _roots(tmp_path)

    result = run_review_pass(**roots, now=NOW)

    assert result["status"] == "failed"
    assert {item["disposition"] for item in result["domains"].values()} == {"blocked"}
    assert not (roots["state_root"] / "research-review-cursors").exists()
    assert Path(result["run_log"]).is_file()
    assert result["model_promotion_allowed"] is False
    assert result["telegram_delivery_confirmed"] is False


def test_status_does_not_create_missing_state(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    result = review_runtime_status(**roots, now=NOW)
    assert result["status"] == "blocked"
    assert set(result["domains"]) == {"au", "hkjc", "tennis", "nba"}
    assert not roots["state_root"].exists()


def test_status_verifies_initialized_cursors_without_modification(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    initialize_review_state(**roots)
    files = list(roots["state_root"].rglob("*"))
    before = {str(path): path.read_bytes() for path in files if path.is_file()}
    assert review_runtime_status(**roots, now=NOW)["status"] == "verified"
    after = {str(path): path.read_bytes() for path in roots["state_root"].rglob("*") if path.is_file()}
    assert after == before


def _status_receipt(roots: dict, *, mutation=None) -> Path:
    contract = load_runtime_contract()
    path = roots["state_root"] / "runs" / "central" / "2026-09-19" / "research-review" / "pass.json"
    payload = {
        "schema_version": review_module.RUN_SCHEMA, "status": "succeeded",
        "started_at": NOW.isoformat(), "run_log": str(path),
        "evaluation_release_id": contract.evaluation_release_id,
        "evaluation_release_commit": contract.evaluation_release_commit,
        "model_promotion_allowed": False, "telegram_delivery_confirmed": False,
        "domains": {domain: {
            "disposition": "succeeded", "status": "ok",
            "model_promotion_allowed": False, "telegram_delivery_confirmed": False,
        } for domain in contract.domains},
    }
    if mutation:
        mutation(payload)
    _write_run(path, payload)
    return path


def test_status_accepts_bound_success_receipt(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    initialize_review_state(**roots)
    path = _status_receipt(roots)
    result = review_runtime_status(**roots, now=NOW, receipt_path=path)
    assert result["status"] == "verified"
    assert result["receipt"]["status"] == "succeeded"


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(evaluation_release_commit="0" * 40),
    lambda p: p.update(model_promotion_allowed=True),
    lambda p: p.update(started_at="2027-01-01T00:00:00+00:00"),
    lambda p: p["domains"].pop("nba"),
    lambda p: p["domains"]["nba"].update(disposition="blocked"),
    lambda p: p["domains"]["nba"].update(telegram_delivery_confirmed=True),
])
def test_status_rejects_invalid_even_rehashed_receipts(tmp_path: Path, mutation) -> None:
    roots = _roots(tmp_path)
    initialize_review_state(**roots)
    path = _status_receipt(roots, mutation=mutation)
    result = review_runtime_status(**roots, now=NOW, receipt_path=path)
    assert result["status"] == "blocked"
    assert "receipt_error" in result


def test_status_preserves_blocked_review_result(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    initialize_review_state(**roots)
    def mutation(payload):
        payload["status"] = "failed"
        for entry in payload["domains"].values():
            entry.update(disposition="blocked", status="missing_source")
    path = _status_receipt(roots, mutation=mutation)
    result = review_runtime_status(**roots, now=NOW, receipt_path=path)
    assert result["status"] == "blocked"
    assert result["receipt"]["status"] == "failed"
    assert "receipt_error" not in result


def test_status_rejects_symlink_and_oversized_receipts(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    initialize_review_state(**roots)
    path = _status_receipt(roots)
    link = path.with_name("link.json")
    link.symlink_to(path)
    assert "symlink" in review_runtime_status(**roots, now=NOW, receipt_path=link)["receipt_error"]
    path.write_bytes(b"x" * (1024 * 1024 + 1))
    assert "bounded" in review_runtime_status(**roots, now=NOW, receipt_path=path)["receipt_error"]


def test_status_rejects_missing_cursor_tables(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    initialize_review_state(**roots)
    path = roots["state_root"] / "research-review-cursors" / "au.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE storage_evidence_state")
    result = review_runtime_status(**roots, now=NOW)
    assert result["status"] == "blocked"
    assert "incomplete" in result["domains"]["au"]["status"]


def test_status_marks_old_success_stale_and_rejects_tampered_bytes(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    initialize_review_state(**roots)
    path = _status_receipt(roots)
    result = review_runtime_status(
        **roots, now=datetime(2026, 9, 22, tzinfo=timezone.utc), receipt_path=path,
    )
    assert result["status"] == "blocked"
    assert result["receipt_stale"] is True
    assert result["receipt"]["status"] == "succeeded"
    body = json.loads(path.read_text())
    body["started_at"] = "2026-09-18T00:00:00+00:00"
    path.write_text(json.dumps(body))
    assert "hash mismatch" in review_runtime_status(**roots, now=NOW, receipt_path=path)["receipt_error"]


@dataclass(frozen=True)
class _Result:
    disposition: ResearchDisposition
    status: str
    cursor_path: Path | None = None
    generation: int | None = 4
    advanced: bool = True


class _RecordingRunner:
    def __init__(self, results: dict[Domain, _Result]):
        self.results = results
        self.calls: list[dict] = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        return self.results[kwargs["domain"]]


def test_pass_uses_one_aware_clock_and_bounded_arguments_for_every_domain(
    tmp_path: Path,
) -> None:
    roots = _roots(tmp_path)
    fake = _RecordingRunner(
        {
            domain: _Result(ResearchDisposition.SUCCEEDED, "reviews_recorded")
            for domain in Domain
        }
    )

    result = run_review_pass(
        **roots,
        now=NOW,
        runner_factory=lambda _runtime, _registry: fake,
    )

    assert result["status"] == "succeeded"
    assert [call["domain"] for call in fake.calls] == list(Domain)
    assert all(call["now"] is NOW for call in fake.calls)
    assert all(call["estimated_bytes"] > 0 for call in fake.calls)
    assert all(call["timeout_seconds"] > 0 for call in fake.calls)
    assert all(call["max_reviews"] > 0 for call in fake.calls)
    assert all(call["queue_root"] == roots["state_root"] / "research-queue" for call in fake.calls)
    assert all(
        call["production_evidence_root"] == roots["state_root"] / "evidence"
        for call in fake.calls
    )


def test_interrupted_run_log_write_never_leaves_partial_official_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "runs" / "review.json"

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("simulated durability interruption")

    monkeypatch.setattr(review_module.os, "fsync", fail_fsync)

    with pytest.raises(OSError, match="durability interruption"):
        _write_run(target, {"schema_version": "test/v1", "status": "failed"})

    assert not target.exists()
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


def test_one_deferred_domain_is_preserved_and_cannot_fabricate_success(
    tmp_path: Path,
) -> None:
    roots = _roots(tmp_path)
    results = {
        domain: _Result(ResearchDisposition.SUCCEEDED, "reviews_recorded")
        for domain in Domain
    }
    results[Domain.TENNIS] = _Result(
        ResearchDisposition.DEFERRED,
        "production_active",
        advanced=False,
    )
    fake = _RecordingRunner(results)

    result = run_review_pass(
        **roots,
        now=NOW,
        runner_factory=lambda _runtime, _registry: fake,
    )

    assert result["status"] == "partial"
    assert result["domains"]["tennis"] == {
        "disposition": "deferred",
        "status": "production_active",
        "cursor_path": None,
        "generation": 4,
        "advanced": False,
        "model_promotion_allowed": False,
        "telegram_delivery_confirmed": False,
    }
    saved = json.loads(Path(result["run_log"]).read_text(encoding="utf-8"))
    assert saved["status"] == "partial"
    assert saved["domains"]["tennis"]["disposition"] == "deferred"
    assert saved["content_hash"]


def test_runtime_requires_explicit_production_locks_and_has_no_delivery_imports(
    tmp_path: Path,
) -> None:
    roots = _roots(tmp_path)
    with pytest.raises(ValueError, match="production lock"):
        run_review_pass(
            **{**roots, "production_lock_paths": ()},
            now=NOW,
        )

    source = (SCRIPTS / "central_research_review.py").read_text(encoding="utf-8")
    assert "racing_telegram" not in source
    assert "cloudflare" not in source.lower()
    assert "send_message" not in source
    assert json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))[
        "model_promotion_allowed"
    ] is False
