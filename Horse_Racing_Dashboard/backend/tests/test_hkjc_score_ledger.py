import csv
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.parser_hkjc import parse_hkjc_analysis


def test_hkjc_parser_carries_full_score_ledger(tmp_path: Path) -> None:
    analysis = tmp_path / "Race_1_Auto_Analysis.md"
    analysis.write_text(
        """## 第1場

**【No.1】 馬甲** | 騎師:潘頓 | 練馬師:蔡約翰 | 負磅:126 | 檔位:2

#### 🧮 7D 評分矩陣逐項拆解

內容。

---

**【No.2】 馬乙** | 騎師:田泰安 | 練馬師:告東尼 | 負磅:124 | 檔位:5

#### 🧮 7D 評分矩陣逐項拆解

內容。
""",
        encoding="utf-8",
    )
    scoring = tmp_path / "Race_1_Auto_Scoring.csv"
    fields = [
        "race_number", "horse_number", "horse_name", "rank", "ability_score",
        "official_ranking_score", "ability_percentile", "distance_suitability_adjustment",
        "distance_suitability_signal", "same_distance_starts", "same_distance_places",
        "distance_score", "form_score", "matrix_stability", "matrixdisp_stability",
        "confidence_score", "risk_score", "grade", "model_pick_status",
    ]
    with scoring.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow({
            "race_number": 1, "horse_number": 1, "horse_name": "馬甲", "rank": 1,
            "ability_score": 72.4, "official_ranking_score": 72.4,
            "ability_percentile": 100,
            "distance_suitability_adjustment": 0.43,
            "distance_suitability_signal": "same_distance_placed",
            "same_distance_starts": 6, "same_distance_places": 2,
            "distance_score": 72, "form_score": 68,
            "matrix_stability": 65, "matrixdisp_stability": 70,
            "confidence_score": 83, "risk_score": 70, "grade": "B+",
            "model_pick_status": "MODEL_TOP_PICK",
        })
        writer.writerow({
            "race_number": 1, "horse_number": 2, "horse_name": "馬乙", "rank": 2,
            "ability_score": 65, "confidence_score": 83, "risk_score": 60, "grade": "B",
        })

    logic = {
        "race_analysis": {"race_number": 1, "venue": "沙田"},
        "horses": {
            "1": {"horse_name": "馬甲", "python_auto": {
                "rank": 1, "ability_score": 72.4, "ability_score_raw": 66.2,
                "official_ranking_score": 72.4, "ability_percentile": 100,
                "feature_scores": {"form_score": 68, "distance_score": 72},
                "derived_feature_scores": {"same_distance_signal_score": 72},
                "matrix_scores": {"stability": 65},
                "matrix_scores_display": {"stability": 70},
                "distance_suitability_adjustment": {
                    "raw_adjustment": 0.43, "signal": "same_distance_placed",
                    "same_distance_starts": 6, "same_distance_places": 2,
                },
            }},
            "2": {"horse_name": "馬乙", "python_auto": {"rank": 2, "ability_score": 65}},
        },
    }
    (tmp_path / "Race_1_Logic.json").write_text(json.dumps(logic, ensure_ascii=False), encoding="utf-8")

    race = parse_hkjc_analysis(str(analysis))
    horse = next(item for item in race.horses if item.horse_number == 1)
    assert horse.ability_score == 72.4
    assert horse.official_ranking_score == 72.4
    assert horse.ability_percentile == 100
    assert horse.distance_score == 72
    assert horse.distance_suitability_adjustment == 0.43
    assert horse.same_distance_starts == 6
    assert horse.scoring_breakdown["matrix_display"]["stability"] == 70
    assert "complete_strength" not in horse.scoring_breakdown
