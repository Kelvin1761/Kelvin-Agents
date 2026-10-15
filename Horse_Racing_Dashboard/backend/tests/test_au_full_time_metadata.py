from pathlib import Path
import sys
import base64
import json
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.au_full_time_metadata import read_time_metadata
from services.parser_au import parse_au_analysis


def block(value):
    token = base64.b64encode(json.dumps(value).encode()).decode()
    return f"<!-- wc-au-full-time:v1:{token} -->"


def test_captured_values_reach_horse_without_recalculating_score(tmp_path):
    detail = {
        "status": "observed",
        "context_index": 102.3,
        "latest_time": 70.12,
        "latest_kmh": 61.6,
        "contribution": 0.75,
    }
    metadata = {
        "schema": "au/full-time-v1",
        "race": {"model_version": "AU_CONTEXT_TOTAL_V1", "status": "ready", "covered": 1, "field_size": 1},
        "horses": {"1": {"name": "Fast Horse", "detail": detail}},
    }
    text = (
        block(metadata)
        + "\nRACE 1 — 1200m\n### 【No.1】 Fast Horse | 騎師: J | 練馬師: T | 負重: 56 | 檔位: 1\n⭐ 最終評級: **B** | 綜合戰力分: **73.0** | 排名: **1**\n#### ⏱️ 逐駒全程速度\n情境指數102.3\n"
    )
    p = tmp_path / "Race_1_Auto_Analysis.md"
    p.write_text(text)
    race = parse_au_analysis(str(p))
    assert race.full_time_speed == metadata["race"]
    assert race.horses[0].full_time_speed == detail
    assert race.horses[0].ability_score == 73
    assert race.horses[0].rank == 1
    assert "wc-au-full-time" not in race.horses[0].raw_text


def test_legacy_stays_unknown_and_corrupt_is_not_silently_missing():
    assert read_time_metadata("legacy report") == (None, "legacy report")
    with pytest.raises(ValueError):
        read_time_metadata("<!-- wc-au-full-time:v1:!bad -->")
    value = {"schema": "au/full-time-v1", "race": None, "horses": {}}
    with pytest.raises(ValueError):
        read_time_metadata(block(value) + block(value))
