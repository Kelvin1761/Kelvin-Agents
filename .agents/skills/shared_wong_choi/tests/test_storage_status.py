from __future__ import annotations

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
