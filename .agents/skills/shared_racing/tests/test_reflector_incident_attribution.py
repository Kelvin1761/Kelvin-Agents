from __future__ import annotations

import sys
from pathlib import Path


REFLECTOR = Path(__file__).resolve().parents[1] / "race_reflector" / "scripts"
sys.path.insert(0, str(REFLECTOR))
import unified_reflector_core as core  # noqa: E402


def test_incident_excerpt_is_horse_specific() -> None:
    report = (
        "1 4 甲馬 (K001) 三百米處受阻。 "
        "2 11 乙馬 (K002) 無特別報告。 "
        "3 7 丙馬 (K003) 賽後發現氣管有血。"
    )

    assert "無特別報告" in core.incident_excerpt(report, "乙馬", 11)
    assert "受阻" not in core.incident_excerpt(report, "乙馬", 11)
    assert core.incident_excerpt(report, "不存在", 12) == ""


def test_missed_horse_without_own_incident_is_not_forgiven() -> None:
    report = "1 4 甲馬 (K001) 三百米處受阻。 2 11 乙馬 (K002) 無特別報告。"
    predictions = [
        {
            "horse_no": number,
            "horse_name": name,
            "derived_rank": rank,
            "grade": "B",
            "composite_score": score,
            "factor_scores": {"draw_score": 50.0, "class_score": 80.0},
        }
        for number, name, rank, score in (
            (4, "甲馬", 1, 80.0),
            (3, "丁馬", 2, 75.0),
            (8, "戊馬", 3, 72.0),
            (11, "乙馬", 6, 60.0),
        )
    ]

    missed = core.analyse_missed_horse(
        {"horse_no": 11, "horse_name": "乙馬", "placing": 2},
        predictions,
        report,
        "hkjc",
    )

    assert missed["verdict"] == "模型失誤"
    assert missed["incident_excerpt"].endswith("無特別報告。")


def test_improvement_theme_uses_weakest_not_strongest_factor() -> None:
    theme, _ = core.derive_improvement_theme(
        {
            "factor_scores": {
                "class_score": 95.0,
                "trainer_score": 90.0,
                "jockey_score": 88.0,
                "speed_score": 85.0,
                "draw_score": 40.0,
            }
        }
    )

    assert theme == "draw_pace"
