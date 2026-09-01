from __future__ import annotations

import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi import storage_status


def test_storage_status_is_read_only_and_scans_known_large_paths(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    state = tmp_path / "state"
    hot = tmp_path / "hot"
    warm = tmp_path / "warm"
    cold = tmp_path / "cold"
    for path in (repo, state, hot, warm, cold):
        path.mkdir()
    backups = repo / "tennis-wong-choi" / "data" / "backups"
    backups.mkdir(parents=True)
    (backups / "snapshot.db").write_bytes(b"x" * 2048)
    live = repo / "tennis-wong-choi" / "tennis_wc.db"
    live.write_bytes(b"live-db")
    monkeypatch.setenv("WC_HOT_DATA_ROOT", str(hot))
    monkeypatch.setenv("WC_WARM_ARCHIVE_ROOT", str(warm))
    monkeypatch.setenv("WC_COLD_MIRROR_ROOT", str(cold))
    monkeypatch.setattr(storage_status, "HOT_WARNING_FREE_BYTES", 1)
    monkeypatch.setattr(storage_status, "HOT_CRITICAL_FREE_BYTES", 0)

    result = storage_status.collect_storage_status(repo, state, scan=True)

    assert result["status"] == "attention"
    assert "dashboard_d1_backup_missing" in result["attention"]
    assert result["tiers"]["warm"]["status"] == "available"
    assert result["tiers"]["cold"]["status"] == "available"
    assert next(item for item in result["inventory"] if item["name"] == "tennis_db_backups")["bytes"] == 2048
    assert next(item for item in result["inventory"] if item["name"] == "tennis_live_db")["bytes"] == 7
    assert not (warm / "snapshot.db").exists()


def test_storage_status_flags_unmounted_warm_and_hot_pressure(
    tmp_path: Path, monkeypatch
) -> None:
    hot = tmp_path / "hot"
    hot.mkdir()
    monkeypatch.setenv("WC_HOT_DATA_ROOT", str(hot))
    monkeypatch.setenv("WC_WARM_ARCHIVE_ROOT", str(tmp_path / "missing"))
    monkeypatch.delenv("WC_COLD_MIRROR_ROOT", raising=False)
    monkeypatch.setattr(storage_status, "HOT_WARNING_FREE_BYTES", 10**30)
    monkeypatch.setattr(storage_status, "HOT_CRITICAL_FREE_BYTES", 10**29)

    result = storage_status.collect_storage_status(tmp_path, tmp_path / "state")

    assert result["status"] == "attention"
    assert "hot_storage_critical" in result["attention"]
    assert "warm_archive_unavailable" in result["attention"]
    assert result["tiers"]["cold"]["status"] == "unconfigured"


def _write_catalog_record(state: Path, artifact_id: str, domain: str) -> dict:
    digest = {"sha256": artifact_id.rsplit(":", 1)[-1].ljust(64, "0")[:64], "bytes": 10, "files": 1}
    records = state / "storage" / "catalog" / "records"
    records.mkdir(parents=True, exist_ok=True)
    (records / f"{artifact_id.replace(':', '_')}.json").write_text(
        json.dumps(
            {
                "schema_version": "wong-choi-artifact/v1",
                "artifact_id": artifact_id,
                "domain": domain,
                "artifact_class": "db-snapshot",
                "destination_digest": digest,
            }
        ),
        encoding="utf-8",
    )
    return digest


def _write_remote_proof(state: Path, artifact_id: str, digest: dict) -> None:
    events = state / "storage" / "catalog" / "events"
    events.mkdir(parents=True, exist_ok=True)
    (events / f"{artifact_id.replace(':', '_')}.json").write_text(
        json.dumps(
            {
                "schema_version": "wong-choi-artifact-remote-mirror/v1",
                "event_id": f"proof:{artifact_id}",
                "artifact_id": artifact_id,
                "provider": "google_drive",
                "remote_url": "https://drive.google.com/drive/folders/verified",
                "verification_method": "full_download_content_digest",
                "verification_status": "pass",
                "verified_at": "2026-08-29T00:00:00+00:00",
                "digest": digest,
            }
        ),
        encoding="utf-8",
    )


def test_storage_status_projects_provider_cold_coverage_and_backlog(
    tmp_path: Path, monkeypatch
) -> None:
    hot = tmp_path / "hot"
    warm = tmp_path / "warm"
    hot.mkdir()
    warm.mkdir()
    state = tmp_path / "state"
    tennis_digest = _write_catalog_record(state, "wc-artifact:tennis", "tennis")
    _write_catalog_record(state, "wc-artifact:nba", "nba")
    _write_remote_proof(state, "wc-artifact:tennis", tennis_digest)
    monkeypatch.setenv("WC_HOT_DATA_ROOT", str(hot))
    monkeypatch.setenv("WC_WARM_ARCHIVE_ROOT", str(warm))
    monkeypatch.delenv("WC_COLD_MIRROR_ROOT", raising=False)
    monkeypatch.setattr(storage_status, "HOT_WARNING_FREE_BYTES", 1)
    monkeypatch.setattr(storage_status, "HOT_CRITICAL_FREE_BYTES", 0)

    result = storage_status.collect_storage_status(tmp_path, state)
    coverage = result["backups"]["catalog_artifacts"]

    assert coverage["status"] == "attention"
    assert coverage["known_artifacts"] == 2
    assert coverage["verified_artifacts"] == 1
    assert coverage["domains"]["tennis"] == {"known": 1, "verified": 1}
    assert "artifact_cold_backlog" in result["attention"]

    nba_digest = next(
        record["destination_digest"]
        for record in (
            json.loads(path.read_text(encoding="utf-8"))
            for path in (state / "storage" / "catalog" / "records").glob("*.json")
        )
        if record["artifact_id"] == "wc-artifact:nba"
    )
    _write_remote_proof(state, "wc-artifact:nba", nba_digest)
    complete = storage_status.collect_storage_status(tmp_path, state)

    assert complete["backups"]["catalog_artifacts"]["status"] == "ok"
    assert "artifact_cold_backlog" not in complete["attention"]
