"""no_prediction write-off: marker, postgame, health, pregame, ledger, archive.

2026-10-10/11/12 were blocked by FW-04 and never froze a prediction snapshot.
Kelvin decided not to create post-hoc snapshots; these tests pin the supported
write-off path instead.  Synthetic fixtures only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import pytest

AUTO_DIR = Path(__file__).resolve().parents[1]
REFLECTOR_SCRIPTS = AUTO_DIR.parent / "nba_reflector" / "scripts"
sys.path.insert(0, str(AUTO_DIR))
import nba_daily_schedule as schedule  # noqa: E402
import nba_market_ledger as ledger  # noqa: E402
import nba_no_prediction as no_prediction  # noqa: E402

SYDNEY = schedule.SYDNEY
DAY = "2026-10-11"
NOW = datetime(2026, 10, 15, 19, 0, tzinfo=SYDNEY)


class _Log:
    def __init__(self) -> None:
        self.steps = []

    def step(self, name, status, **detail):
        self.steps.append((name, status, detail))

    def states(self, name):
        return [state for step, state, _ in self.steps if step == name]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv(ledger.ENV_ROOT, str(tmp_path / "ledger_root"))
    monkeypatch.setenv("WONGCHOI_CONTROL_STATE_ROOT", str(tmp_path / "control"))
    monkeypatch.setenv("WC_REQUIRE_EVIDENCE", "0")


def _day(tmp_path: Path, tags=("ATL_IND", "DAL_HOU")) -> Path:
    folder = tmp_path / f"{DAY} NBA Analysis"
    folder.mkdir()
    for tag in tags:
        (folder / f"Sportsbet_Odds_{tag}.json").write_text(
            json.dumps({"target_analysis_date": DAY}), encoding="utf-8"
        )
        (folder / f"Game_{tag}_Full_Analysis.md").write_text("A" * 2500, encoding="utf-8")
    return folder


def _snapshot(folder: Path, tags, *, blocked=()) -> Path:
    snap = folder / "_prediction_snapshots" / "20261011-063000-000000"
    snap.mkdir(parents=True)
    (snap / "manifest.json").write_text(json.dumps({
        "game_tags": sorted(tags),
        "completeness": "partial" if blocked else "complete",
        "blocked_game_tags": sorted(blocked),
        "snapshot_role": "production",
    }), encoding="utf-8")
    return snap


def _mark(folder: Path, **kwargs):
    return no_prediction.mark(
        folder, DAY, reason=kwargs.pop("reason", "FW-04 blocked; no post-hoc snapshot"),
        marked_by=kwargs.pop("marked_by", "Kelvin"), now=NOW, **kwargs,
    )


# ── marker ──────────────────────────────────────────────────────────────────

def test_mark_records_reason_who_when_and_file_hashes(tmp_path):
    folder = _day(tmp_path)
    result = _mark(folder, model_commit="abc123")
    assert result["status"] == "marked"
    payload = json.loads((folder / no_prediction.MARKER_NAME).read_text())
    assert payload["kind"] == "no_prediction" and payload["append_only"] is True
    entry = payload["entries"][0]
    assert (entry["scope"], entry["reason"], entry["marked_by"], entry["marked_at"]) == (
        "date", "FW-04 blocked; no post-hoc snapshot", "Kelvin", NOW.isoformat()
    )
    assert entry["game_tags"] == ["ATL_IND", "DAL_HOU"]
    assert entry["model_commit"] == "abc123"
    names = {item["name"] for item in entry["files_present_at_mark"]}
    assert "Game_ATL_IND_Full_Analysis.md" in names and no_prediction.MARKER_NAME not in names
    # Never a prediction snapshot.
    assert not (folder / "_prediction_snapshots").exists()
    # Idempotent: re-marking appends nothing.
    assert _mark(folder)["status"] == "already_marked"
    assert len(json.loads((folder / no_prediction.MARKER_NAME).read_text())["entries"]) == 1


@pytest.mark.parametrize("kwargs, error", [
    ({"reason": "  "}, "reason_required"),
    ({"marked_by": ""}, "marked_by_required"),
    ({"game_tags": ["NYK_MIA"]}, "unknown_game_tags:NYK_MIA"),
])
def test_mark_refuses_bad_input(tmp_path, kwargs, error):
    folder = _day(tmp_path)
    with pytest.raises(no_prediction.NoPredictionError, match=error):
        _mark(folder, **kwargs)
    assert not (folder / no_prediction.MARKER_NAME).exists()


def test_mark_never_hides_a_frozen_prediction(tmp_path):
    folder = _day(tmp_path)
    _snapshot(folder, ["ATL_IND"], blocked=["DAL_HOU"])
    with pytest.raises(no_prediction.NoPredictionError, match="date_has_prediction_snapshot"):
        _mark(folder)
    with pytest.raises(no_prediction.NoPredictionError, match="game_has_prediction_snapshot:ATL_IND"):
        _mark(folder, game_tags=["ATL_IND"])
    assert _mark(folder, game_tags=["DAL_HOU"])["status"] == "marked"
    current = no_prediction.scope(folder)
    assert not current.whole_date and current.game_tags == {"DAL_HOU"}
    assert not no_prediction.covers_date(folder)


def test_corrupt_marker_fails_loudly(tmp_path):
    folder = _day(tmp_path)
    (folder / no_prediction.MARKER_NAME).write_text("{not json", encoding="utf-8")
    with pytest.raises(no_prediction.NoPredictionError, match="unreadable"):
        no_prediction.scope(folder)


# ── postgame ────────────────────────────────────────────────────────────────

def _archived(archive: Path):
    return subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout=json.dumps({"status": "archived", "archive_path": str(archive), "no_prediction": "date"}) + "\n",
        stderr="",
    )


def test_postgame_without_marker_still_blocks(tmp_path):
    folder = _day(tmp_path)
    with mock.patch.object(schedule, "live_dir", return_value=folder), \
            mock.patch.object(schedule, "_run") as run:
        with pytest.raises(schedule.TemporaryFailure, match="live_analysis_has_no_prediction_snapshot"):
            schedule.run_postgame(DAY, _Log())
    run.assert_not_called()


def test_postgame_archives_marked_day_without_snapshot_error(tmp_path):
    folder = _day(tmp_path)
    _mark(folder)
    archive = tmp_path / "archive" / folder.name
    log = _Log()
    with mock.patch.object(schedule, "live_dir", return_value=folder), \
            mock.patch.object(schedule, "_run", return_value=_archived(archive)) as run, \
            mock.patch.object(schedule, "_deploy", return_value="ok"), \
            mock.patch.object(schedule, "notify_once", return_value={"status": "sent"}) as notify, \
            mock.patch.object(schedule, "freeze_settlement_artifacts") as freeze, \
            mock.patch.object(ledger, "settle") as settle:
        assert schedule.run_postgame(DAY, log) == "archived"
    assert run.call_args.args[0][-2:] == ["--date", DAY]
    assert log.states("prediction_snapshot") == ["no_prediction"]
    assert log.states("settlement_evidence") == ["skipped"]
    assert log.states("telegram_performance") == ["skipped"]
    freeze.assert_not_called()
    settle.assert_not_called()
    keys = [call.args[0] for call in notify.call_args_list]
    assert keys == [f"postgame-ops:{DAY}"]
    assert "no_prediction" in notify.call_args.args[1]
    rows = ledger.read_rows(Path(ledger.ledger_root()), DAY)
    assert [(r["row_type"], r["game_tag"], r["marked_by"]) for r in rows] == [
        ("no_prediction", None, "Kelvin")
    ]


def test_postgame_results_not_final_stays_retryable(tmp_path):
    folder = _day(tmp_path)
    _mark(folder)
    skipped = subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout='{"status":"archive_skipped","message":"no_prediction date: results not final"}\n',
        stderr="",
    )
    with mock.patch.object(schedule, "live_dir", return_value=folder), \
            mock.patch.object(schedule, "_run", return_value=skipped):
        with pytest.raises(schedule.TemporaryFailure, match="results not final"):
            schedule.run_postgame(DAY, _Log())


def test_already_archived_marked_day_skips_settlement(tmp_path):
    folder = _day(tmp_path)
    _mark(folder)
    log = _Log()
    with mock.patch.object(schedule, "live_dir", return_value=tmp_path / "missing"), \
            mock.patch.object(schedule, "archived_dirs", return_value=[folder]), \
            mock.patch.object(schedule, "freeze_settlement_artifacts") as freeze:
        assert schedule.run_postgame(DAY, log) == "already_archived"
    freeze.assert_not_called()
    assert ("settlement_evidence", "skipped", {"reason": "no_prediction"}) in log.steps


# ── health / pregame ───────────────────────────────────────────────────────

def _health(folder: Path):
    with mock.patch.object(schedule, "load_espn_schedule", return_value=({"ATL_IND", "DAL_HOU"}, True)), \
            mock.patch.object(schedule, "live_dir", return_value=folder), \
            mock.patch.object(schedule, "archived_dirs", return_value=[]):
        return schedule.health_payload(DAY)


def test_health_respects_marker(tmp_path):
    folder = _day(tmp_path)
    payload, code = _health(folder)
    assert (payload["status"], code) == ("missing_prediction", 1)
    _mark(folder)
    payload, code = _health(folder)
    assert (payload["status"], code) == ("no_prediction", 0)
    assert payload["no_prediction"]["marked_by"] == "Kelvin"


def test_health_partial_snapshot_with_marked_blocked_games_is_ok(tmp_path):
    folder = _day(tmp_path)
    _snapshot(folder, ["ATL_IND"], blocked=["DAL_HOU"])
    assert _health(folder)[0]["status"] == "partial_prediction"
    _mark(folder, game_tags=["DAL_HOU"])
    payload, code = _health(folder)
    assert (payload["status"], code) == ("ok", 0)


def test_pregame_never_snapshots_a_marked_day(tmp_path):
    folder = _day(tmp_path)
    _mark(folder)
    log = _Log()
    starts = {"ATL_IND": NOW + timedelta(hours=3)}
    with mock.patch.object(schedule, "live_dir", return_value=folder), \
            mock.patch.object(schedule, "refresh_sportsbet_odds") as refresh, \
            mock.patch.object(schedule, "create_prediction_snapshot") as create:
        status = schedule.run_pregame(DAY, log, at=NOW, schedule_events=(starts, True))
    assert status == "no_prediction"
    refresh.assert_not_called()
    create.assert_not_called()


# ── CLI ─────────────────────────────────────────────────────────────────────

def test_cli_mark_no_prediction(tmp_path, capsys, monkeypatch):
    folder = _day(tmp_path)
    monkeypatch.setattr(schedule, "live_dir", lambda _date: folder)
    monkeypatch.setattr(schedule, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(sys, "argv", [
        "nba_daily_schedule.py", "--mode", "mark-no-prediction", "--date", DAY,
        "--reason", "FW-04 blocked", "--by", "Kelvin",
    ])
    assert schedule.main() == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["status"] == "marked" and out["market_ledger"] == {"status": "ok", "appended": 1}
    assert no_prediction.covers_date(folder)

    monkeypatch.setattr(sys, "argv", [
        "nba_daily_schedule.py", "--mode", "mark-no-prediction", "--date", DAY, "--by", "Kelvin",
    ])
    with pytest.raises(SystemExit):
        schedule.main()


# ── market ledger ──────────────────────────────────────────────────────────

def test_ledger_excludes_written_off_dates_and_games(tmp_path):
    root = Path(ledger.ledger_root())
    base = {"schema": ledger.SCHEMA, "season_phase": "EARLY_REGULAR", "snapshot_id": "s1",
            "snapshot_role": "production", "snapshot_created_at": "2026-10-22T00:00:00+00:00",
            "player": "P", "market": "pts", "line": 20.0, "side": "over", "p_final": 0.6,
            "picked": True}
    for day, tag in (("2026-10-22", "BOS_LAL"), ("2026-10-22", "NYK_MIA"), ("2026-10-23", "BOS_LAL")):
        ledger.append_rows(root, day, [{**base, "row_type": "model_obs", "target_date": day, "game_tag": tag}])
    assert ledger.evaluate(root=root)["overall"]["legs"] == 3
    ledger.record_no_prediction("2026-10-22", game_tags=["NYK_MIA"], reason="r", marked_by="K", marked_at="t")
    ledger.record_no_prediction("2026-10-23", game_tags=None, reason="r", marked_by="K", marked_at="t")
    report = ledger.evaluate(root=root)
    assert report["overall"]["legs"] == 1
    assert report["counts"]["excluded_no_prediction_rows"] == 2
    assert report["no_prediction_exclusions"] == [
        {"target_date": "2026-10-22", "game_tag": "NYK_MIA"},
        {"target_date": "2026-10-23", "game_tag": None},
    ]
    # Idempotent exclusion rows; whole-date settle is a no-op.
    assert ledger.record_no_prediction("2026-10-23", game_tags=None, reason="r2", marked_by="K", marked_at="t") == 0
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({"_version": "RESULTS_BRIEF_V1", "games": []}))
    assert ledger.settle("2026-10-23", brief)["status"] == "no_prediction"


# ── review archive ─────────────────────────────────────────────────────────

def _review_archive(tmp_path, monkeypatch, brief_status: str):
    sys.path.insert(0, str(REFLECTOR_SCRIPTS))
    import nba_daily_review_archive as review

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    folder = _day(workspace)
    _mark(folder)
    archive_root = tmp_path / "archive"
    monkeypatch.setattr(review, "WORKSPACE_ROOT", workspace)
    monkeypatch.setattr(review, "NBA_ANALYSIS", archive_root)
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if "--no-record" in command:
            results = folder / "Results_Brief_2026-10-10.json"
            results.write_text(json.dumps({
                "_version": "RESULTS_BRIEF_V1",
                "games": [{"game_id": "1", "status": brief_status}],
            }))
            (folder / f"Reflector_Run_Summary_{DAY}.json").write_text(json.dumps({
                "training_snapshot": str(folder / "t.csv"), "results_path": str(results),
                "verification_path": str(folder / "v.json"), "rows_recorded": 0,
                "no_prediction": True,
            }))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(review.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["nba_daily_review_archive.py", "--date", DAY])
    return review, folder, archive_root, calls


def test_review_archive_marked_day_archives_results_without_recording(tmp_path, monkeypatch, capsys):
    review, folder, archive_root, calls = _review_archive(tmp_path, monkeypatch, "Final")
    assert review.main() == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["status"] == "archived" and out["no_prediction"] == "date"
    assert len(calls) == 1 and "--no-record" in calls[0]  # no settlement proposal either
    assert not folder.exists()
    assert (archive_root / folder.name / no_prediction.MARKER_NAME).is_file()


def test_review_archive_marked_day_waits_for_final_results(tmp_path, monkeypatch, capsys):
    review, folder, _archive_root, _calls = _review_archive(tmp_path, monkeypatch, "7:00 pm ET")
    assert review.main() == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["status"] == "archive_skipped" and "games_not_final" in out["message"]
    assert folder.is_dir()
