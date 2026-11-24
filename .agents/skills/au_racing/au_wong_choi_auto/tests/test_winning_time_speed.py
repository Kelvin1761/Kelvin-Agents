"""EXP-20261124-40：WinningTime 速度分 overlay —— 公式、場內 z、回退開關、point-in-time。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from au_racing_engine import winning_time_speed as W  # noqa: E402


def test_parse_run_reads_time_margin_and_skips_trials():
    line = "Ballina R3 2026-11-01 1200m cond:Good4 $20000 X (3) 58.0kg margin:1.50L finish:2/9 WinningTime:1:10.50"
    run = W.parse_run(line)
    assert run["winning_time"] == pytest.approx(70.5) and run["margin"] == 1.5 and run["distance"] == 1200
    assert W.parse_run(line + " **(TRIAL)**") is None
    assert W.parse_run(line.replace("WinningTime:1:10.50", "")) is None


def test_standards_use_only_races_strictly_before_the_day():
    rows = [{"track": "T", "date": f"2026-10-{d:02d}", "race": 1, "distance": 1200, "condition": "Good4",
             "winning_time": 70.0} for d in range(1, 11)] + [
        {"track": "T", "date": "2026-10-20", "race": 1, "distance": 1200, "condition": "Good4", "winning_time": 99.0}]
    base, _going, n = W.build_asof_standards(rows, ["2026-10-20"])["2026-10-20"]
    assert n == 10 and base[("T", 1200)] == 70.0      # 當日嗰場唔入標準


def test_feature_is_half_field_z_and_neutral_without_value(monkeypatch):
    monkeypatch.delenv("WC_AU_SPEED_LIVE", raising=False)
    field = [1.0, 0.0, -1.0, None]
    sd = (2 / 3) ** 0.5
    assert W.feature(1.0, field) == pytest.approx(round(0.5 * 1.0 / sd, 4))
    assert W.feature(None, field) == 0.0
    assert W.feature(0.5, [0.5, None]) == 0.0           # 場內得 1 個值
    monkeypatch.setenv("WC_AU_SPEED_LIVE", "0")
    assert W.feature(1.0, field) == 0.0


def test_prepare_field_reads_formguide_and_ignores_runs_on_or_after_the_day(tmp_path):
    ref = tmp_path / "ref.json"
    rows = [{"track": "T", "date": f"2026-10-{d:02d}", "race": d, "distance": 1200, "condition": "Good4",
             "winning_time": 70.0} for d in range(1, 13)]
    ref.write_text(json.dumps({"rows": rows}))
    lines = [f"T R{d} 2026-10-{d:02d} 1200m cond:Good4 margin:{m}L WinningTime:1:10.00" for d, m in ((1, 0), (2, 1), (3, 2))]
    future = "T R9 2026-11-05 1200m cond:Good4 margin:0L WinningTime:1:05.00"
    fg = "RACE 4 — 1200m\n[1] Fast Horse (3)\n" + "\n".join(lines + [future]) + "\n[2] New Horse (5)\nT R1 2026-10-01 1200m cond:Good4 margin:0L WinningTime:1:10.00\n"
    (tmp_path / "2026-11-05 T Race 4 Formguide.md").write_text(fg)
    logic = {"horses": {"1": {"horse_name": "Fast Horse"}, "2": {"horse_name": "New Horse"}}}
    speeds = W.prepare_field(logic, tmp_path, 4, "2026-11-05", reference=ref)
    assert speeds[1] is None and logic["horses"]["2"]["winning_time_speed"]["status"] == "insufficient_runs"
    sec_per_len = 2.4 / (1200 / 70.0)
    expected = sum(-(m * sec_per_len) / 1.2 for m in (0, 1, 2)) / 3   # 11-05 嗰仗（未來）唔計
    assert speeds[0] == pytest.approx(expected, abs=1e-6)


def test_own_value_is_not_counted_twice(monkeypatch):
    """Sol 2026-11-24：全場名單同每匹自己嘅值要同一個捨入，唔可以因為搵唔到自己而再加一次。"""
    monkeypatch.delenv("WC_AU_SPEED_LIVE", raising=False)
    assert W.feature(0.333333, [0.333333, 0.333333]) == 0.0       # 同速 = 0（以前會變 +0.7071）
    assert W.feature(1.0, [1.0, -1.0]) == pytest.approx(0.5)
