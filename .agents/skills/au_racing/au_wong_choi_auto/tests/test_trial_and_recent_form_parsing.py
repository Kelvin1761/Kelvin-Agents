"""2026-10-12 Tamworth R4 Platinum Card：一場第 10 嘅馬排第 2。三個獨立缺陷。"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / ".agents" / "scripts"))

from au_racing_engine.engine_core import RacingEngine  # noqa: E402
from au_racing_engine.scoring import parse_recent_finishes  # noqa: E402


def test_single_tenth_is_not_a_win_plus_a_tenth():
    assert parse_recent_finishes("10") == [10]
    assert parse_recent_finishes("5-10-9") == [5, 10, 9]
    assert parse_recent_finishes("2134") == [2, 1, 3, 4]


def test_missing_form_lines_use_official_last10_not_neutral():
    # 生涯 1 場、跑第 10，但 Sportsbet 往績頁只剩試閘：form 唔可以係中性 60。
    horse = {"horse_name": "Platinum Card", "horse_number": "2", "career_race_starts": 1,
             "_data": {"recent_form": "10", "career_record_line": "1 : 0-0-0"}}
    engine = RacingEngine(horse, {"race_class": "Maiden Plate"}, facts_section="",
                          facts_path="/tmp/x.md")
    engine._career_starts = lambda: 1
    engine._official_entries = lambda: []
    score, _note, _src = engine._form_score()
    assert score < 60
    assert engine.form_detail.get("source") == "official_last10_without_form_lines"


def test_injector_trusts_raceclass_over_distance_guess():
    import inject_fact_anchors as inj
    fg = ("[4] Smashit (1)\n"
          "Scone R1 2026-09-25 900m cond:Good $27000 Mitchell Bell (4) 57.0kg 4th@400m. margin:1.86L "
          "starters:8 finish:2/8 RaceClass:[MDN-SW] WinningTime:51.740\n"
          "1-Mainstay (59.0kg), 2-Smashit (57.0kg) 1.86L, 3-Our Astute Lass (55.0kg) 4.11L\n\n"
          "Gosford **(TRIAL)** R15 2026-08-31 800m cond:Soft $0 X (None) Nonekg . margin:2.0L starters:9 "
          "finish:4/9 RaceClass:[4Y+ MDN-BT Barrier Trial] WinningTime:47.100\n"
          "1-A (Nonekg), 2-B (Nonekg) 1.0L, 3-C (Nonekg) 1.5L\n")
    entries = inj.parse_formguide_for_horse(fg, 4, "Smashit", [2], as_of="2026-10-12")
    kinds = {e.get("date"): e.get("is_trial") for e in entries}
    assert kinds == {"2026-09-25": False, "2026-08-31": True}
