"""One blocked game must not erase the whole day's prediction snapshot.

2026-10-10/11/12: the per-game firewall blocked one game a day (partly a
decimal-point false positive in FW-04), the orchestrator exited 1, the
scheduler froze nothing, and every postgame raised
``live_analysis_has_no_prediction_snapshot``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import pytest

AUTO_DIR = Path(__file__).resolve().parents[1]
NBA_SKILL = AUTO_DIR.parent
sys.path.insert(0, str(AUTO_DIR))
import nba_daily_schedule as schedule  # noqa: E402

SYDNEY = ZoneInfo("Australia/Sydney")
DATE = "2026-10-21"


class _Log:
    def __init__(self) -> None:
        self.steps = []
        self.payload = {"warnings": [], "errors": []}

    def step(self, name, status, **detail):
        self.steps.append((name, status, detail))


def _game(folder: Path, tag: str) -> None:
    (folder / f"Sportsbet_Odds_{tag}.json").write_text(
        json.dumps({"target_analysis_date": DATE}), encoding="utf-8"
    )
    (folder / f"nba_game_data_{tag}.json").write_text("{}\n", encoding="utf-8")
    (folder / f"Game_{tag}_Full_Analysis.md").write_text(tag * 1000, encoding="utf-8")


def _aggregates(folder: Path) -> None:
    (folder / "NBA_All_SGM_Report.txt").write_text("SGM\n", encoding="utf-8")
    (folder / "NBA_Banker_Report.txt").write_text("BANKER\n", encoding="utf-8")


def _payload(**body) -> str:
    return "noise\nNBA_PIPELINE_RESULT: " + json.dumps(body) + "\n"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("WONGCHOI_CONTROL_STATE_ROOT", str(tmp_path / "control"))
    monkeypatch.setenv("WC_REQUIRE_EVIDENCE", "0")


def test_blocked_games_payload_is_parsed_only_for_exit_one() -> None:
    body = _payload(status="games_blocked", passed_games=["A_B"],
                    blocked_games=["C_D"], waiting_games=[], sgm_ok=True)
    ok = subprocess.CompletedProcess([], 1, body, "")
    assert schedule.blocked_games_result(ok) == {
        "blocked": ["C_D"], "passed": ["A_B"], "sgm_ok": True,
    }
    assert schedule.blocked_games_result(subprocess.CompletedProcess([], 0, body, "")) is None
    bad = _payload(status="games_blocked", passed_games=["A_B"], blocked_games=[])
    assert schedule.blocked_games_result(subprocess.CompletedProcess([], 1, bad, "")) is None


def _run_pregame(folder: Path, orchestrate) -> tuple[_Log, Exception | None]:
    log = _Log()
    now = datetime(2026, 10, 21, 0, 30, tzinfo=SYDNEY)
    events = {"BOS_LAL": now + timedelta(hours=9), "NYK_MIA": now + timedelta(hours=10)}
    error = None
    with mock.patch.object(schedule, "live_dir", return_value=folder), \
            mock.patch.object(schedule, "refresh_sportsbet_odds"), \
            mock.patch.object(schedule, "_run", side_effect=orchestrate), \
            mock.patch.object(schedule, "_deploy") as deploy, \
            mock.patch.object(schedule, "notify_once") as notify:
        try:
            schedule.run_pregame(
                DATE, log, freshness_role=schedule.FreshnessRole.PRODUCTION,
                at=now, schedule_events=(events, True),
            )
        except schedule.TemporaryFailure as exc:
            error = exc
        deploy.assert_not_called()
        notify.assert_not_called()
    return log, error


def _orchestrator_blocks_nyk(command, timeout=3600):
    if command[:2] == ["git", "rev-parse"]:
        return subprocess.CompletedProcess(command, 0, "abc123\n", "")
    folder = schedule.live_dir(DATE)
    _game(folder, "BOS_LAL")
    _game(folder, "NYK_MIA")
    _aggregates(folder)
    return subprocess.CompletedProcess(
        command, 1,
        _payload(status="games_blocked", passed_games=["BOS_LAL"],
                 blocked_games=["NYK_MIA"], waiting_games=[], sgm_ok=True),
        "",
    )


def test_blocked_game_freezes_partial_snapshot_and_still_fails(tmp_path) -> None:
    folder = tmp_path / "live"
    folder.mkdir()
    log, error = _run_pregame(folder, _orchestrator_blocks_nyk)

    assert error is not None
    assert str(error) == "games_blocked:NYK_MIA:partial_snapshot_frozen"
    snapshots = [p for p in (folder / "_prediction_snapshots").iterdir() if not p.name.startswith(".")]
    assert len(snapshots) == 1
    manifest = json.loads((snapshots[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["completeness"] == "partial"
    assert manifest["game_tags"] == ["BOS_LAL"]
    assert manifest["blocked_game_tags"] == ["NYK_MIA"]
    names = {entry["name"] for entry in manifest["files"]}
    assert "Game_BOS_LAL_Full_Analysis.md" in names
    assert not any("NYK_MIA" in name for name in names)
    assert ("prediction_snapshot", "partial") in [(n, s) for n, s, _ in log.steps]

    # A partial snapshot is a real prediction for postgame and health ...
    assert schedule.latest_snapshot(folder) == snapshots[0]
    # ... but never "already snapshotted" for the pregame retry.
    assert schedule.latest_snapshot(folder, role=schedule.FreshnessRole.PRODUCTION) is None


def test_retry_with_identical_artifacts_does_not_duplicate_partial(tmp_path) -> None:
    folder = tmp_path / "live"
    folder.mkdir()
    _run_pregame(folder, _orchestrator_blocks_nyk)
    log, error = _run_pregame(folder, _orchestrator_blocks_nyk)
    assert error is not None
    snapshots = [p for p in (folder / "_prediction_snapshots").iterdir() if not p.name.startswith(".")]
    assert len(snapshots) == 1
    assert ("prediction_snapshot", "partial_unchanged") in [(n, s) for n, s, _ in log.steps]


def test_unparseable_exit_one_still_freezes_nothing(tmp_path) -> None:
    folder = tmp_path / "live"
    folder.mkdir()

    def broken(command, timeout=3600):
        _game(folder, "BOS_LAL")
        return subprocess.CompletedProcess(command, 1, "crash\n", "")

    _, error = _run_pregame(folder, broken)
    assert str(error) == "orchestrator_exit_1:all"
    assert not (folder / "_prediction_snapshots").exists()


def test_postgame_reviews_a_partial_snapshot(tmp_path) -> None:
    folder = tmp_path / "live"
    folder.mkdir()
    _run_pregame(folder, _orchestrator_blocks_nyk)
    review = subprocess.CompletedProcess([], 0, '{"status":"archive_skipped","message":"results not ready"}\n', "")
    with mock.patch.object(schedule, "live_dir", return_value=folder), \
            mock.patch.object(schedule, "_run", return_value=review) as run:
        with pytest.raises(schedule.TemporaryFailure, match="results not ready"):
            schedule.run_postgame(DATE, _Log())
    run.assert_called_once()


def test_health_reports_partial_prediction(tmp_path) -> None:
    folder = tmp_path / "live"
    folder.mkdir()
    _run_pregame(folder, _orchestrator_blocks_nyk)
    with mock.patch.object(schedule, "live_dir", return_value=folder), \
            mock.patch.object(schedule, "archived_dirs", return_value=[]), \
            mock.patch.object(schedule, "load_espn_schedule", return_value=({"BOS_LAL", "NYK_MIA"}, True)):
        payload, code = schedule.health_payload(DATE)
    assert code == 1
    assert payload["status"] == "partial_prediction"
    assert payload["reason"] == "blocked_games:NYK_MIA"


def test_orchestrator_emits_machine_readable_blocked_result() -> None:
    source = (NBA_SKILL / "nba_orchestrator.py").read_text(encoding="utf-8")
    assert '"status": "games_blocked"' in source
    assert '"blocked_games": sorted(results["failed"])' in source


def test_opportunity_raw_sources_are_hash_bound_in_prediction_snapshot(tmp_path):
    folder = tmp_path / (DATE + ' NBA Analysis'); folder.mkdir()
    _game(folder, 'BOS_LAL'); _aggregates(folder)
    raw = b'{"contract":"nba-opportunities/v1","sources":{}}'
    (folder / 'NBA_Opportunity_Sources.json').write_bytes(raw)
    with mock.patch.object(schedule, 'validate_analysis', return_value=[]):
        snapshot = schedule.create_prediction_snapshot(folder, DATE, ['BOS_LAL'])
    assert (snapshot / 'NBA_Opportunity_Sources.json').read_bytes() == raw
    manifest = schedule.snapshot_manifest(snapshot)
    files = {row['name']: row for row in manifest['files']}
    import hashlib
    assert files['NBA_Opportunity_Sources.json']['sha256'] == hashlib.sha256(raw).hexdigest()
