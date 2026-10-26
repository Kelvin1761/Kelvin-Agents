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


def _predictions():
    return [
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
            (11, "乙馬", 9, 60.0),
        )
    ]


def test_missed_placegetter_with_interference_is_not_forgiven() -> None:
    # 受阻都跑入前三 = 模型低估得更多，唔係寬恕理由。
    report = "2 11 乙馬 (K002) 三百米處受阻。"
    missed = core.analyse_missed_horse(
        {"horse_no": 11, "horse_name": "乙馬", "placing": 2}, _predictions(), report, "hkjc"
    )

    assert "可寬恕" not in missed["verdict"]
    assert missed["verdict"] == "模型失誤（受阻仍上名）"
    assert missed["evidence_level"] == "12.00 分"


def test_race_incident_only_forgives_failed_model_picks() -> None:
    picks = [{"horse_no": n, "horse_name": name} for n, name in ((4, "甲馬"), (3, "丁馬"), (8, "戊馬"))]
    placed_all = [{"horse_no": n, "horse_name": name} for n, name in ((3, "丁馬"), (4, "甲馬"), (8, "戊馬"))]
    report = "1 3 丁馬 (K003) 起步時發生碰撞。 5 11 乙馬 (K002) 受阻。"

    assert core.analyse_race_incidents("hkjc", picks, placed_all, report)["classification"] == "不適用"

    # 只有上咗名嘅馬有事故 —— 跑輸嘅模型首選冇，唔可以寬恕。
    placed = [{"horse_no": n, "horse_name": name} for n, name in ((3, "丁馬"), (11, "乙馬"), (9, "己馬"))]
    clean = core.analyse_race_incidents("hkjc", picks, placed, "1 3 丁馬 (K003) 受阻。 2 11 乙馬 (K002) 受阻。")
    assert clean["classification"] == "無明顯事故"

    forgiven = core.analyse_race_incidents("hkjc", picks, placed, "6 4 甲馬 (K001) 三百米處受阻。")
    assert forgiven["classification"] == "可寬恕事故"
    assert "#4 甲馬" in forgiven["summary"]


def test_improvement_theme_is_decided_by_the_single_weakest_leaf() -> None:
    # 舊版按主題次序揀，weight_score 一入最弱四個就永遠係「班次 / 路程」。
    theme, _ = core.derive_improvement_theme(
        {"factor_scores": {"draw_score": 40.0, "weight_score": 45.0, "class_score": 80.0}}
    )

    assert theme == "draw_pace"


def test_reflected_summary_replaces_pre_race_zero_kpis(tmp_path) -> None:
    import json

    (tmp_path / "evaluation_summary.json").write_text(
        json.dumps({"status": "pending_results", "evaluated_race_count": 0,
                    "kpis": {"gold": 0}, "scoring_profile": "mainline"}),
        encoding="utf-8",
    )
    race = core.RacePerformance(
        race_num=1, label="Gold",
        model_top3=[{"horse_no": 4}], model_top5=[], actual_top3=[{"horse_no": 4}],
        actual_rows=[], prediction_rows=[], top5_actual_top3_hits=3,
        top5_actual_top3_covered=[], top5_actual_top3_missed=[], winner_in_model_top5=True,
        missed_actual_top3=[], incident_analysis={},
    )

    path = core.write_reflected_evaluation_summary(tmp_path, [race], "snapshot X")
    summary = json.loads(path.read_text(encoding="utf-8"))

    assert summary["status"] == "reflected"
    assert summary["evaluated_race_count"] == 1
    assert summary["kpis"]["gold"] == 1 and summary["kpis"]["champion"] == 1
    assert summary["scoring_profile"] == "mainline"
