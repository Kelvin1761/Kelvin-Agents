"""HKJC strip must reconcile to the real score: parser keeps raw score, impact,
post-matrix adjustments and the final raw total from grade_transparency."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import parser_hkjc  # noqa: E402


def test_raw_impact_and_adjustments_are_parsed(tmp_path):
    analysis = tmp_path / "Race_1_Auto_Analysis.md"
    analysis.write_text("x", encoding="utf-8")
    (tmp_path / "Race_1_Logic.json").write_text(json.dumps({"horses": {"3": {"python_auto": {
        "grade_transparency": {
            "rows": [{"key": "race_shape", "label": "檔位與走位", "score": 63.1, "score_raw": 66.13,
                      "weight": 0.2737, "contribution": 18.1, "impact": 1.6779, "band": "➖"}],
            "adjustments": [{"key": "sip_boost", "label": "SIP 輕磅好檔修正", "raw": 1.0}],
            "ability_score_raw": 69.96,
        }}}}}), encoding="utf-8")
    details = parser_hkjc._load_matrix_details(analysis)[3]
    assert details[0].score_raw == 66.13 and details[0].impact == 1.6779
    extras = parser_hkjc.matrix_extras(analysis, 3)
    assert extras["raw_total"] == 69.96
    assert extras["adjustments"][0]["raw"] == 1.0
