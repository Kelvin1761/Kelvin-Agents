"""Banker 速覽 showed N/A on every row (2026-10-22).

`extract_banker_leg` searched for "最強一關"; the report prints "最強關" (the best
leg of the whole game, which can be a @7.5 long shot). The 穩膽 banker leg is the
highest-EV leg inside combo 1.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from generate_nba_sgm_reports import extract_banker_leg  # noqa: E402

REPORT = """## 🎯 投注組合

### 🛡️ 組合 1: 穩膽 SGM (Low Risk) — 組合賠率 @2.84
> 2-3 Legs | L10/L5 ≥80% | 目標 2.0-3.2x

| Leg | 選項 | 賠率 | L10 命中 | 預期勝率 | Edge | EV% | CoV |
|-----|------|------|----------|----------|------|-----|-----|
| 🧩 1 | Paolo Banchero (ORL) REB 8+ | @1.52 | 90.0% (9/10) | **98.0%** | +32.21% | +48.96% | 0.165 ✅穩定 |
| 🧩 2 | Wendell Carter Jr. (ORL) AST 2+ | @1.87 | 70.0% (7/10) | **73.0%** | +19.52% | +36.51% | 0.702 🎲神經刀 |

### 🔥 組合 2: 平衡 SGM

| Leg | 選項 | 賠率 | L10 命中 | 預期勝率 | Edge | EV% | CoV |
|-----|------|------|----------|----------|------|-----|-----|
| 🧩 1 | Someone (ATL) PTS 30+ | @7.5 | 50.0% (5/10) | **60.0%** | +40.00% | +440.0% | 0.300 ➖中波 |

## 📌 總結
- **最強關**: Someone (ATL) PTS 30+ @7.5 — EV% +440.0% 💎核心高價值
"""


def test_picks_highest_ev_leg_inside_combo_one() -> None:
    assert extract_banker_leg(REPORT) == "Paolo Banchero (ORL) REB 8+ @1.52 (EV +49.0%)"


def test_does_not_use_game_wide_longshot() -> None:
    assert "Someone" not in extract_banker_leg(REPORT)


def test_no_combo_one_gives_none() -> None:
    assert extract_banker_leg("## 📌 總結\n- **最強關**: x @2 — EV% +1%") is None
