"""覆盤要評開跑前嘅版本，唔係開跑後重評或者開跑後先寫嘅「immutable」快照。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".agents/skills/shared_racing/race_reflector/scripts"))

import unified_reflector_core as core  # noqa: E402


def _snapshot(meeting: Path, folder: str, name: str, created: str) -> Path:
    path = meeting / folder / name
    path.mkdir(parents=True)
    (path / "manifest.json").write_text(json.dumps({"created_at": created}), encoding="utf-8")
    (path / "Race_1_Auto_Scoring.csv").write_text("race_number\n1\n", encoding="utf-8")
    return path


def test_picks_last_snapshot_before_first_post(tmp_path):
    meeting = tmp_path / "2026-10-07_HappyValley"
    meeting.mkdir()
    (meeting / "10-07 Race 1 排位表.md").write_text("時間: 18:35\n", encoding="utf-8")
    (meeting / "10-07 Race 2 排位表.md").write_text("時間: 19:10\n", encoding="utf-8")
    early = _snapshot(meeting, "_prediction_snapshots", "a", "2026-10-07T08:16:32+11:00")
    pre = _snapshot(meeting, "_prediction_snapshots", "b", "2026-10-07T11:17:22+11:00")
    _snapshot(meeting, "Prediction_Snapshots", "c", "2026-10-08T00:05:39+11:00")   # 21:05 HKT, after R1
    snapshot, created, post = core.select_prerace_snapshot(meeting)
    assert snapshot == pre and snapshot != early
    assert post.hour == 18 and post.minute == 35
    assert created < post


def test_no_prerace_snapshot_is_reported_not_guessed(tmp_path):
    meeting = tmp_path / "2026-10-07_HappyValley"
    meeting.mkdir()
    (meeting / "10-07 Race 1 排位表.md").write_text("時間: 18:35\n", encoding="utf-8")
    _snapshot(meeting, "Prediction_Snapshots", "c", "2026-10-08T00:05:39+11:00")
    snapshot, _created, post = core.select_prerace_snapshot(meeting)
    assert snapshot is None and post is not None


def test_retired_hkjc_backtest_returns_nothing(tmp_path):
    assert core.run_hkjc_backtests(tmp_path) == []
