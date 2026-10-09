"""EXP-20261009-05 盲測第二組：未夠 2,000 場唔准出結果；候選公式鎖死。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import au_speed_recency_shadow as R  # noqa: E402

STANDARDS = ({("Flemington", 1200): 70.0}, {}, 1)


def _line(date, seconds, margin=0.0):
    return f"Flemington R1 {date} 1200m cond:Good4 WinningTime:{seconds} margin:{margin}L"


def test_recency_needs_two_runs_and_weights_newest_first():
    one = _line("2026-09-01", 69.0)
    assert R.recency_speed(one, STANDARDS, "2026-09-27") is None
    block = "\n".join([_line("2026-09-01", 69.0), _line("2026-08-01", 71.0)])
    value = R.recency_speed(block, STANDARDS, "2026-09-27")
    newest, older = 1.0 / 1.2, -1.0 / 1.2
    assert abs(value - (newest * 1.0 + older * 0.8) / 1.8) < 1e-9


def test_future_runs_are_ignored():
    block = "\n".join([_line("2026-09-01", 69.0), _line("2026-08-01", 71.0), _line("2026-10-01", 60.0)])
    assert R.recency_speed(block, STANDARDS, "2026-09-27") == R.recency_speed(
        "\n".join(block.splitlines()[:2]), STANDARDS, "2026-09-27")


def test_residual_removes_pace_figure_component():
    speed_z = [1.0, 0.0, -1.0, 0.0]
    pf_z = [1.0, 0.0, -1.0, 0.0]
    out = R.residual(speed_z, [True, True, True, False], pf_z)
    assert all(abs(v) < 1e-9 for v in out)


def test_collecting_status_has_no_outcomes(tmp_path, monkeypatch):
    rows = [{"date": "2026-09-27", "venue": "X", "race": i, "runners": []} for i in range(10)]
    monkeypatch.setattr(R, "load_terminal", lambda root: rows)
    status = R.run(tmp_path, tmp_path / "s.json")
    assert status["state"] == "collecting"
    assert status["outcomes_visible"] is False
    assert "evaluation" not in status
    assert status["config"]["speed_k"] == 0.5
