"""AU 綜合分 overlay（EXP-20261101-38）：報告帶過嚟嘅數原封到 horse，唔喺 UI 重算。"""
from pathlib import Path
import sys
import base64
import json
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.au_overlay_metadata import read_overlay_metadata
from services.parser_au import parse_au_analysis


def block(value):
    token = base64.b64encode(json.dumps(value).encode()).decode()
    return f"<!-- wc-au-overlays:v1:{token} -->"


HORSE = {
    "name": "Fast Horse", "pure_7d_score": 72.1, "ability_score": 73.0,
    "overlays": [
        {"key": "wet_form", "label": "濕地往績調整", "dimension": "場地與地況適性", "value": 0.4},
        {"key": "proven_class", "label": "班次證明", "dimension": "官方評分對位", "value": 0.5},
        {"key": "full_time_speed", "label": "逐駒全程速度", "dimension": "速度考驗背景", "value": 0.0},
    ],
    "trip_change": {"dimension": "狀態與穩定性", "today": 1600, "last": 1100.0, "delta": -5.0},
}


def test_overlays_reach_horse_and_marker_is_stripped(tmp_path):
    metadata = {"schema": "au/overlays-v1", "horses": {"1": HORSE}}
    text = (
        block(metadata)
        + "\nRACE 1 — 1200m\n### 【No.1】 Fast Horse | 騎師: J | 練馬師: T | 負重: 56 | 檔位: 1\n"
        "⭐ 最終評級: **B** | 綜合戰力分: **73.0** | 排名: **1**\n"
    )
    p = tmp_path / "Race_1_Auto_Analysis.md"
    p.write_text(text)
    race = parse_au_analysis(str(p))
    got = race.horses[0].score_overlays
    assert got["overlays"] == HORSE["overlays"]
    assert got["trip_change"] == HORSE["trip_change"]
    assert got["pure_7d_score"] == 72.1 and got["ability_score"] == 73.0
    assert "wc-au-overlays" not in race.horses[0].raw_text


def test_wrong_horse_name_is_not_attached(tmp_path):
    metadata = {"schema": "au/overlays-v1", "horses": {"1": {**HORSE, "name": "Other Horse"}}}
    p = tmp_path / "Race_1_Auto_Analysis.md"
    p.write_text(block(metadata) + "\nRACE 1 — 1200m\n### 【No.1】 Fast Horse | 騎師: J | 練馬師: T | 負重: 56 | 檔位: 1\n"
                 "⭐ 最終評級: **B** | 綜合戰力分: **73.0** | 排名: **1**\n")
    assert parse_au_analysis(str(p)).horses[0].score_overlays is None


def test_legacy_and_corrupt_metadata():
    assert read_overlay_metadata("legacy report") == (None, "legacy report")
    with pytest.raises(ValueError):
        read_overlay_metadata("<!-- wc-au-overlays:v1:!bad -->")
    value = {"schema": "au/overlays-v1", "horses": {}}
    with pytest.raises(ValueError):
        read_overlay_metadata(block(value) + block(value))
