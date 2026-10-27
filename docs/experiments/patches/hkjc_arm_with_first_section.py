"""EXP-20261016-53 forward（2026-10-27 退回後）：將最快第一段四個權重設返上線時嘅值。

退回之後 live = 冇前速，所以 forward 要用呢個 arm 量「有前速」；判定器嘅比較方向唔變
（有前速 vs 冇前速）。
"""
ARM_NAME = "with_first_section"
WEIGHTS = {
    "first_section_fast_bonus": 4.0,
    "first_section_quick_bonus": 2.0,
    "first_section_slowish_pen": -1.0,
    "first_section_slow_pen": -2.0,
}


def apply():
    from hkjc_racing_engine import scoring
    for key, value in WEIGHTS.items():
        assert key in scoring.SPEED_MICRO_WEIGHTS, key
        scoring.SPEED_MICRO_WEIGHTS[key] = value
