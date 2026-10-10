"""覆盤逐維度歸因：主因揀得啱、7D 舊 CSV 唔會錯計晨操、ledger 重跑唔重複。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".agents/skills/shared_racing/race_reflector/scripts"))

import dimension_attribution as a  # noqa: E402

REG = ({"race_shape": 0.5, "sectional": 0.3, "stability": 0.15, "trackwork": 0.05}, {"distance_fit": 0.02},
       {"race_shape": "檔位", "sectional": "段速", "stability": "穩定", "trackwork": "晨操", "distance_fit": "同程"})


def _h(rank, **m):
    return {"name": f"馬{rank}", "rank": rank, "m": m}


def test_missed_horse_blames_the_dimension_that_held_it_back():
    horses = {1: _h(1, race_shape=80, sectional=60), 2: _h(2, race_shape=78, sectional=60),
              3: _h(3, race_shape=79, sectional=60), 4: _h(4, race_shape=50, sectional=75)}
    rows = a.attribute_race(1, horses, {4: 1, 1: 2, 2: 3, 3: 9}, REG)
    missed = next(r for r in rows if r["kind"] == "missed")
    assert missed["horse_no"] == 4 and missed["main"] == ["race_shape"]
    over = next(r for r in rows if r["kind"] == "overrated")
    assert over["horse_no"] == 3


def test_seven_d_rows_fold_trackwork_weight_into_stability():
    old = _h(4, stability=70)            # 7D CSV: no matrix_trackwork column
    gap = a.contributions(old, [_h(1, stability=60)], REG[0], REG[1])
    assert abs(gap["stability"] - 0.20 * 10) < 1e-9 and "trackwork" not in gap


def test_centred_dimension_uses_its_own_coefficient():
    gap = a.contributions(_h(4, distance_fit=80), [_h(1, distance_fit=60)], REG[0], REG[1])
    assert abs(gap["distance_fit"] - 0.02 * 20) < 1e-9


def test_ledger_rewrites_one_meeting_and_queue_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(a, "_registry", lambda: REG)
    ledger = tmp_path / a.LEDGER_NAME
    row = {"race": 1, "horse_no": 4, "kind": "missed", "main": ["race_shape"], "gap": {}}
    a.write_ledger(ledger, "2026-10-07_HappyValley", [row, row])
    a.write_ledger(ledger, "2026-10-07_HappyValley", [row, row])
    a.write_ledger(ledger, "2026-10-04_ShaTin", [row])
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 3
    queue = a.queue_summary(ledger, threshold=3)
    assert queue[0]["horses"] == 3 and queue[0]["meetings"] == 2 and queue[0]["ready"]


def test_registry_is_the_production_one():
    weights, centred, labels = a._registry()
    assert "trackwork" in weights and "distance_fit" in centred and labels["race_shape"]
