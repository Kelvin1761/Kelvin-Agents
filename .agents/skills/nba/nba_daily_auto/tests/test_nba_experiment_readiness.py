"""Experiment readiness: Monday digest, one-off checkpoint alerts, never breaks postgame."""
from __future__ import annotations

import sys
from pathlib import Path

AUTO_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AUTO_DIR))
import nba_experiment_readiness as readiness  # noqa: E402
import nba_daily_schedule as schedule  # noqa: E402


REPORT = {"until": "2026-11-16", "items": [
    {"name": "MS2 REB+3PM", "protocol": "EXP-20261025-15", "status": "ACCUMULATING",
     "progress": "160 場／16 日（下一個檢查點 400 場）", "checkpoint": "harm"},
    {"name": "MS1", "protocol": "EXP-20261025-12", "status": "ACCUMULATING",
     "progress": "90 場／9 日（下一個檢查點 150 場）", "checkpoint": None},
]}


def test_alerts_only_for_due_checkpoints_with_stable_keys():
    alerts = readiness.due_alerts(REPORT)
    assert len(alerts) == 1 and alerts[0][0] == "EXP-20261025-15:MS2 REB+3PM:harm"
    assert "可以開始判斷" in alerts[0][1]
    lines = readiness.progress_lines(REPORT)
    assert lines[1].startswith("🔔 MS2 REB+3PM") and lines[2].startswith("⏳ MS1")


def test_one_broken_tool_does_not_hide_the_others(tmp_path, monkeypatch):
    monkeypatch.setattr(readiness, "_ms_items", lambda root, until: (_ for _ in ()).throw(RuntimeError("boom")))
    (tmp_path / "ledger").mkdir()
    report = readiness.build("2026-10-28", tmp_path, analysis_roots=[tmp_path])
    names = [i["name"] for i in report["items"]]
    assert names[0] == "error" and "S_v4 vs S_v2" in names and "最佳落注時間研究" in names


class _Log:
    def __init__(self):
        self.steps = []

    def step(self, name, status, **detail):
        self.steps.append((name, status, detail))


def test_postgame_sends_digest_on_monday_and_each_alert_once(monkeypatch):
    sent = []
    monkeypatch.setattr(readiness, "build", lambda until: REPORT)
    monkeypatch.setattr(schedule, "notify_once", lambda key, msg, audience="primary": sent.append((key, audience)) or {})
    log = _Log()
    schedule._experiment_readiness("2026-11-16", log)            # a Monday
    assert ("experiment-ready:EXP-20261025-15:MS2 REB+3PM:harm", "primary") in sent
    assert ("experiment-progress:2026-11-16", "primary") in sent
    sent.clear()
    schedule._experiment_readiness("2026-11-17", log)            # Tuesday: alert key only (deduped by notify_once)
    assert [k for k, _ in sent] == ["experiment-ready:EXP-20261025-15:MS2 REB+3PM:harm"]
    monkeypatch.setattr(readiness, "build", lambda until: 1 / 0)
    schedule._experiment_readiness("2026-11-17", log)
    assert log.steps[-1][:2] == ("experiment_readiness", "failed")


def test_guard_trips_are_warnings_not_ready_to_judge():
    report = {"until": "2026-10-27", "items": [
        {"name": "MS1", "protocol": "EXP-20261025-12", "status": "INVALID_DATA", "progress": "9 場／1 日",
         "checkpoint": "INVALID_DATA"}]}
    (key, line), = readiness.due_alerts(report)
    assert line.startswith("⚠️ MS1") and "可以開始判斷" not in line and key.endswith(":INVALID_DATA")
