"""HKJC had no field-level publish gate; AU has had one since 2026-08-22.

That incident: ten AU meetings scored with `pace_figure_score` flat at 60, 12.2%
of the ranking weight silently dead, while extraction reported success, nine
suites were green and the logs were clean. HKJC's only equivalent was
`health_status()`, which formats a Telegram line and gates nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL))

import hkjc_daily_schedule as sched  # noqa: E402


def _meeting(tmp_path):
    (tmp_path / "Race_1_Logic.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_a_dead_field_blocks_publishing(tmp_path, monkeypatch):
    monkeypatch.setattr(sched, "run_cmd", lambda *a, **k: (
        1, "  [dead-field] pace_figure_score: 118/120 匹中性，基準話平時有值"))
    blocking = sched.check_data_contract(_meeting(tmp_path))
    assert len(blocking) == 1
    assert "dead-field" in blocking[0] and "pace_figure_score" in blocking[0]


def test_a_clean_meeting_does_not_block(tmp_path, monkeypatch):
    monkeypatch.setattr(sched, "run_cmd", lambda *a, **k: (0, "✅ 全部欄位符合基準"))
    assert sched.check_data_contract(_meeting(tmp_path)) == []


def test_thin_small_field_warnings_do_not_block(tmp_path, monkeypatch):
    """A gate that blocks normal days is a gate someone switches off."""
    monkeypatch.setattr(sched, "run_cmd", lambda *a, **k: (
        0, "⚠️ [spread] trainer_score: 場內分數散開度 2.69 —— 偏平，細場次屬正常"))
    assert sched.check_data_contract(_meeting(tmp_path)) == []


def test_a_nonzero_exit_without_a_dead_line_still_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(sched, "run_cmd", lambda *a, **k: (3, "contract crashed"))
    blocking = sched.check_data_contract(_meeting(tmp_path))
    assert blocking and "exit=3" in blocking[0]


def test_a_dead_line_under_a_passing_exit_is_surfaced_not_swallowed(tmp_path, monkeypatch):
    logged = []
    monkeypatch.setattr(sched, "run_cmd", lambda *a, **k: (
        0, "  [dead-field] speed_score: 120/120 匹中性"))
    monkeypatch.setattr(sched, "log", lambda msg: logged.append(msg))
    assert sched.check_data_contract(_meeting(tmp_path)) == []
    assert any("dead-field" in m for m in logged)


def test_a_meeting_without_logic_files_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(sched, "run_cmd", lambda *a, **k: pytest_fail())
    assert sched.check_data_contract(tmp_path) == []


def pytest_fail():
    raise AssertionError("contract must not run without Logic files")
