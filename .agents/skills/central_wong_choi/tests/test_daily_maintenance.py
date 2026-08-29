from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PACKAGE_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from central_daily_maintenance import run_maintenance  # noqa: E402
from shared_wong_choi.artifact_archive import artifact_digest  # noqa: E402


def test_daily_maintenance_logs_and_notifies_success(tmp_path: Path) -> None:
    sent = []

    def backup(*args, **kwargs):
        return {
            "status": "pass",
            "row_counts": {"bets": 3, "settlements": 2, "audit_log": 4},
            "warm": {"status": "copied_verified"},
            "cold": {"status": "deferred"},
            "sql": {"sha256": "abc123456789ffff"},
        }

    def notify(message: str, **kwargs):
        sent.append((message, kwargs))
        return {"ok": True, "status": "sent"}

    result = run_maintenance(
        tmp_path / "repo",
        tmp_path / "state",
        warm_root=tmp_path / "warm",
        cold_root=None,
        clock=datetime(2026, 8, 28, 1, tzinfo=timezone.utc),
        backup_fn=backup,
        notify_fn=notify,
    )

    assert result["status"] == "succeeded"
    assert Path(result["run_log"]).is_file()
    assert "bets 3" in sent[0][0]
    assert sent[0][1]["audience"] == "primary"


def test_daily_maintenance_skips_verified_same_sydney_day(tmp_path: Path) -> None:
    state = tmp_path / "state"
    snapshot = state / "dashboard_d1" / "snapshots" / "20260828T010000Z"
    snapshot.mkdir(parents=True)
    (snapshot / "manifest.json").write_text(json.dumps({
        "snapshot_at": "2026-08-28T01:00:00+00:00",
        "database": "wongchoi-ledger",
        "sql": {},
        "restore": {"status": "pass", "row_counts": {}},
    }), encoding="utf-8")
    destination = tmp_path / "warm-copy"
    destination.mkdir()
    digest = artifact_digest(destination)
    records = state / "storage" / "catalog" / "records"
    records.mkdir(parents=True)
    (records / "record.json").write_text(json.dumps({
        "artifact_id": "wc-artifact:test",
        "source": str(snapshot),
        "destination": str(destination),
        "source_digest": digest,
        "destination_digest": digest,
    }), encoding="utf-8")

    result = run_maintenance(
        tmp_path / "repo",
        state,
        warm_root=tmp_path / "warm",
        cold_root=None,
        clock=datetime(2026, 8, 28, 4, tzinfo=timezone.utc),
        backup_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must skip")),
        notify=False,
    )

    assert result["status"] == "dormant"
    assert result["reason"] == "today_already_verified"


def test_daily_maintenance_treats_external_tcc_as_deferred_not_failed(
    tmp_path: Path,
) -> None:
    sent = []

    def backup(*_args, **_kwargs):
        return {
            "status": "deferred",
            "row_counts": {"bets": 3},
            "warm": {"status": "deferred", "reason": "Operation not permitted"},
            "cold": {"status": "deferred"},
            "sql": {"sha256": "abc"},
        }

    result = run_maintenance(
        tmp_path / "repo",
        tmp_path / "state",
        warm_root=tmp_path / "external",
        cold_root=None,
        clock=datetime(2026, 8, 28, 2, tzinfo=timezone.utc),
        backup_fn=backup,
        notify_fn=lambda message, **_kwargs: sent.append(message) or {"ok": True},
    )

    assert result["status"] == "deferred"
    assert "本機驗證完成" in sent[0]
    assert "Operation not permitted" in sent[0]


def test_daily_maintenance_notification_failure_preserves_backup_result(
    tmp_path: Path,
) -> None:
    result = run_maintenance(
        tmp_path / "repo",
        tmp_path / "state",
        warm_root=tmp_path / "warm",
        cold_root=None,
        clock=datetime(2026, 8, 28, 3, tzinfo=timezone.utc),
        backup_fn=lambda *_args, **_kwargs: {
            "status": "pass",
            "warm": {"status": "copied_verified"},
            "cold": {"status": "deferred"},
            "row_counts": {},
            "sql": {"sha256": "abc"},
        },
        notify_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("telegram offline")
        ),
    )

    assert result["status"] == "succeeded"
    assert result["telegram"]["status"] == "failed"
    assert "telegram offline" in result["telegram"]["error"]


def test_launchd_template_is_daily_and_uses_production_wrapper() -> None:
    template = (PACKAGE_ROOT / "launchd" / "com.antigravity.central-wong-choi.durability.plist.template").read_text(encoding="utf-8")
    wrapper = (PACKAGE_ROOT / "scripts" / "run_central_daily_maintenance.sh").read_text(encoding="utf-8")

    assert "<integer>3</integer>" in template
    assert "<integer>20</integer>" in template
    assert "run_central_daily_maintenance.sh" in template
    assert "WC_PRIMARY_REPO_ROOT" in wrapper
    assert "WC_COLD_MIRROR_ROOT" in wrapper
