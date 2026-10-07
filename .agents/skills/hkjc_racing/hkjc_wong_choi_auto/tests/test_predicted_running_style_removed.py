from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
AUTO = ROOT / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"
sys.path.insert(0, str(AUTO))

from hkjc_racing_engine.engine_core import RacingEngine  # noqa: E402
from hkjc_racing_engine.renderer import _matrix_fact_lines  # noqa: E402


def _horse(style: str) -> dict:
    return {
        "horse_name": "測試馬",
        "barrier": "4",
        "season_stats": "季內 (0-0-0-0) | 同程 (0-0-0-0) | 同場同程 (0-0-0-0)",
        "_data": {
            "running_style": style,
            "draw_position_fit": "今仗檔4=內檔 → ✅匹配走內偏好",
            "position_pi": "[+1, +2, +3] → 趨勢: 上升軌 ✅",
            "position_window": "第1仗: 沿途位=6-6-3, 消耗=中等消耗",
            "draw_verdict": "中性",
        },
    }


def test_predicted_style_confidence_no_longer_changes_hv_score() -> None:
    context = {"venue": "跑馬地", "distance": "1200m"}
    high = RacingEngine(_horse("中段 | 信心: 高"), context)._race_shape_context_delta()[0]
    low = RacingEngine(_horse("後上 | 信心: 低"), context)._race_shape_context_delta()[0]
    assert high == low


def test_predicted_style_is_not_rendered_as_next_race_claim() -> None:
    horse = _horse("中段 | 信心: 高")
    engine = RacingEngine(horse, {"venue": "跑馬地", "distance": "1200m"})
    rows = engine._data_readout(
        {"draw_score": 65.0},
        {"race_shape": 65.0, "trainer_signal": 60.0},
    )
    assert all(row["label"] != "預測跑法" for row in rows)
    assert "預計" not in engine._describe_race_shape_matrix(65.0, {"draw_score": 65.0}, [])

    facts = "\n".join(_matrix_fact_lines("race_shape", horse))
    assert "中段 | 信心: 高" not in facts
    assert "檔位 / 歷史走位" in facts
