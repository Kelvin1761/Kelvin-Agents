"""賽道偏差 ledger：賽道由排位表讀、偏差方向啱、重跑唔重複、樣本未夠唔會判。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"))

import hkjc_rail_bias_ledger as L  # noqa: E402


def _meeting(tmp_path: Path, name="2026-10-07_HappyValley", inside_wins=True) -> Path:
    m = tmp_path / name
    m.mkdir()
    (m / "10-07 Race 1 排位表.md").write_text("場次: 第1場\n場地: 草地\n賽道: C+3 賽道\n", encoding="utf-8")
    results = []
    for draw in range(1, 9):
        pos = draw if inside_wins else 9 - draw
        results.append({"pos": str(pos), "horse_no": str(draw), "draw": str(draw),
                        "running_positions": f"{pos} {pos} {pos}"})
    payload = {"1": {"race_no": 1, "venue": "HappyValley", "going": "好地", "course": '草地 - "C+3" 賽道',
                     "results": results}}
    (m / f"{name}_全日賽果.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return m


def test_inside_day_is_negative_and_rail_comes_from_racecard(tmp_path):
    rows = L.race_rows(_meeting(tmp_path))
    assert rows[0]["rail"] == "C+3" and rows[0]["going"] == "好地" and rows[0]["venue"] == "跑馬地"
    assert rows[0]["inside_bias"] < 0 and rows[0]["front_bias"] < 0


def test_outside_day_is_positive(tmp_path):
    assert L.race_rows(_meeting(tmp_path, inside_wins=False))[0]["inside_bias"] > 0


def test_record_is_idempotent_and_report_refuses_small_samples(tmp_path):
    m = _meeting(tmp_path)
    ledger = tmp_path / L.LEDGER_NAME
    L.record(m, ledger)
    L.record(m, ledger)
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 1
    assert "樣本未夠" in L.report(ledger)


def test_meeting_without_results_records_nothing(tmp_path):
    m = tmp_path / "2026-10-11_ShaTin"
    m.mkdir()
    assert L.record(m, tmp_path / L.LEDGER_NAME) == 0
