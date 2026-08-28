from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.dashboard_backup import (  # noqa: E402
    D1_TABLES,
    DashboardBackupError,
    backup_d1_ledger,
    collect_d1_backup_status,
    verify_d1_export,
)
from shared_wong_choi import dashboard_backup  # noqa: E402


def _dashboard(root: Path) -> Path:
    dashboard = root / "Horse_Racing_Dashboard"
    dashboard.mkdir()
    (dashboard / "package.json").write_text(
        json.dumps({"devDependencies": {"wrangler": "4.86.0"}}), encoding="utf-8"
    )
    (dashboard / "wrangler.toml").write_text(
        '[[d1_databases]]\ndatabase_name = "wongchoi-ledger"\n', encoding="utf-8"
    )
    return dashboard


def _sql(rows: int = 1) -> str:
    statements = []
    for table in D1_TABLES:
        statements.append(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY);")
        for value in range(rows):
            statements.append(f"INSERT INTO {table} (id) VALUES ({value + 1});")
    return "\n".join(statements) + "\n"


def _count_payload(rows: int) -> str:
    return json.dumps(
        [{"success": True, "results": [
            {"table_name": table, "row_count": rows} for table in D1_TABLES
        ]}]
    )


class FakeRunner:
    def __init__(self, counts: list[int], sql_rows: int = 1) -> None:
        self.counts = list(counts)
        self.sql_rows = sql_rows
        self.queries = 0
        self.exports = 0

    def __call__(self, command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        assert cwd.name == "Horse_Racing_Dashboard"
        assert "wrangler@4.86.0" in command
        if "execute" in command:
            rows = self.counts[self.queries]
            self.queries += 1
            return subprocess.CompletedProcess(command, 0, _count_payload(rows), "")
        output = Path(command[command.index("--output") + 1])
        output.write_text(_sql(self.sql_rows), encoding="utf-8")
        self.exports += 1
        return subprocess.CompletedProcess(command, 0, "exported", "")


def test_d1_backup_restores_counts_and_archives_to_warm(tmp_path: Path) -> None:
    dashboard = _dashboard(tmp_path)
    state = tmp_path / "state"
    warm = tmp_path / "warm"
    warm.mkdir()
    clock = datetime(2026, 8, 28, 1, tzinfo=timezone.utc)

    result = backup_d1_ledger(
        dashboard,
        state,
        warm_root=warm,
        runner=FakeRunner([1, 1]),
        now=clock,
    )
    status = collect_d1_backup_status(state, now=clock + timedelta(hours=1))

    assert result["status"] == "pass"
    assert result["warm"]["status"] == "copied_verified"
    assert status["status"] == "ok"
    assert status["restore_verified"] is True
    assert status["warm_verified"] is True
    assert status["cold_verified"] is False
    assert all(value == 1 for value in status["row_counts"].values())
    assert not list((state / "dashboard_d1" / "snapshots").glob("*.partial-*"))


def test_d1_backup_retries_if_remote_changes_during_export(tmp_path: Path) -> None:
    dashboard = _dashboard(tmp_path)
    runner = FakeRunner([0, 1, 1, 1], sql_rows=1)

    result = backup_d1_ledger(
        dashboard,
        tmp_path / "state",
        warm_root=None,
        runner=runner,
        now=datetime(2026, 8, 28, 2, tzinfo=timezone.utc),
    )

    assert result["status"] == "pass"
    assert runner.exports == 2
    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert manifest["attempt"] == 2


def test_d1_backup_rejects_count_mismatch_and_cleans_partial(tmp_path: Path) -> None:
    dashboard = _dashboard(tmp_path)
    state = tmp_path / "state"

    with pytest.raises(DashboardBackupError, match="row counts"):
        backup_d1_ledger(
            dashboard,
            state,
            warm_root=None,
            runner=FakeRunner([2, 2], sql_rows=1),
            now=datetime(2026, 8, 28, 3, tzinfo=timezone.utc),
        )

    assert not list((state / "dashboard_d1" / "snapshots").glob("*.partial-*"))


def test_verify_export_requires_new_destination_and_valid_sql(tmp_path: Path) -> None:
    sql = tmp_path / "backup.sql"
    sql.write_text(_sql(), encoding="utf-8")
    restored = tmp_path / "restored.sqlite"

    result = verify_d1_export(sql, restored)

    assert result["status"] == "pass"
    with pytest.raises(DashboardBackupError, match="already exists"):
        verify_d1_export(sql, restored)


def test_backup_status_reports_missing_and_stale(tmp_path: Path) -> None:
    assert collect_d1_backup_status(tmp_path)["status"] == "no_data"
    dashboard = _dashboard(tmp_path)
    state = tmp_path / "state"
    clock = datetime(2026, 8, 28, 4, tzinfo=timezone.utc)
    backup_d1_ledger(
        dashboard,
        state,
        warm_root=None,
        runner=FakeRunner([1, 1]),
        now=clock,
    )

    status = collect_d1_backup_status(state, now=clock + timedelta(hours=40))

    assert status["status"] == "attention"
    assert "dashboard_d1_backup_stale" in status["attention"]
    assert "dashboard_d1_backup_warm_pending" in status["attention"]


def test_backup_status_detects_warm_corruption(tmp_path: Path) -> None:
    dashboard = _dashboard(tmp_path)
    state = tmp_path / "state"
    warm = tmp_path / "warm"
    warm.mkdir()
    clock = datetime(2026, 8, 28, 5, tzinfo=timezone.utc)
    result = backup_d1_ledger(
        dashboard,
        state,
        warm_root=warm,
        runner=FakeRunner([1, 1]),
        now=clock,
    )
    destination = Path(result["warm"]["destination"])
    (destination / "wongchoi-ledger.sql").write_text("corrupt", encoding="utf-8")

    status = collect_d1_backup_status(state, now=clock + timedelta(hours=1))

    assert status["status"] == "attention"
    assert status["warm_verified"] is False
    assert "dashboard_d1_backup_warm_pending" in status["attention"]


def test_backup_status_accepts_verified_google_drive_proof(tmp_path: Path) -> None:
    from shared_wong_choi.artifact_archive import mirror_artifact, record_remote_mirror_proof

    dashboard = _dashboard(tmp_path)
    state = tmp_path / "state"
    warm = tmp_path / "warm"
    warm.mkdir()
    clock = datetime(2026, 8, 28, 6, tzinfo=timezone.utc)
    result = backup_d1_ledger(
        dashboard,
        state,
        warm_root=warm,
        runner=FakeRunner([1, 1]),
        now=clock,
    )
    cold = tmp_path / "cold"
    cold.mkdir()
    local_mirror = mirror_artifact(Path(result["warm"]["manifest"]), cold_root=cold)
    Path(local_mirror["destination"]).joinpath("wongchoi-ledger.sql").write_text(
        "corrupt", encoding="utf-8"
    )
    record_remote_mirror_proof(
        Path(result["warm"]["manifest"]),
        provider="google_drive",
        remote_id="folder-123",
        remote_url="https://drive.google.com/drive/folders/folder-123",
        digest=result["warm"]["destination_digest"],
        verification_method="full_download_content_digest",
        actor="codex:drive-connector",
    )

    status = collect_d1_backup_status(state, now=clock + timedelta(hours=1))

    assert status["status"] == "ok"
    assert status["cold_verified"] is True
    assert status["cold_provider"] == "google_drive"
    assert status["cold_destination"].endswith("folder-123")


def test_remote_count_parser_accepts_single_scalar_row() -> None:
    payload = json.dumps([{
        "success": True,
        "results": [{table: index for index, table in enumerate(D1_TABLES)}],
    }])

    counts = dashboard_backup._parse_counts(payload)

    assert counts == {table: index for index, table in enumerate(D1_TABLES)}
    query = dashboard_backup._count_query()
    assert "UNION" not in query
    assert query.count("SELECT COUNT(*)") == len(D1_TABLES)
