#!/usr/bin/env python3
"""AU 標籤審計 2026-11-13（docs/audits/au-label-audit-20261113/）嘅顯示修正。

全部係純顯示：排名同入分 leaf 唔變（golden bit-identical）。每個測試對住一個
「標籤講嘅同計嘅唔一樣」嘅實例。
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

from au_racing_engine.engine_core import RacingEngine, formline_headline  # noqa: E402
from au_racing_engine.matrix_mapper import MATRIX_FORMULAS  # noqa: E402
from au_racing_engine.dimensions import FEATURE_LABELS  # noqa: E402
from au_racing_engine import renderer  # noqa: E402

CTX = {"race_class": "BM70, Handicap", "distance": "1400m",
       "field_summary": {"count": 10},
       "meeting_intelligence": {"venue": "Flemington", "going": "Good 4"}}


def engine(**data):
    horse = {"horse_name": "T", "horse_number": "1", "barrier": 4, "weight": 57.0,
             "jockey": "A Rider", "trainer": "A Stable", "_data": dict(data)}
    return RacingEngine(horse, dict(CTX), facts_section="")


class TestFormlineHeadline:
    """#1：「❌ 弱 (強組比例: 0/3)」入面嘅「強」字唔係級別。11 月 93% 弱賽績線被讀成強。"""

    @pytest.mark.parametrize("text, expected", [
        ("❌ 弱 (強組比例: 0/3)", "weak"),
        ("中弱 (強組比例: 0.5/3)", "medium_weak"),
        ("✅ 強 (強組比例: 2/3)", "strong"),
        ("✅✅ 極強 (強組比例: 6/6)", "elite"),
        ("中強 (強組比例: 1/3)", "medium_strong"),
        ("賽績線: 弱 | 強組比例: 0/2", "weak"),
    ])
    def test_signal_reads_only_the_headline(self, text, expected):
        assert engine(formline_line=text)._formline_signal() == expected

    def test_headline_strip(self):
        assert formline_headline("❌ 弱 (強組比例: 0/3)") == "❌ 弱"
        assert "強" not in formline_headline("❌ 弱（強組比例: 0/3）")


def test_jockey_trainer_weights_text_matches_formula():
    """#3：維度內部權重由公式生成，唔可以再寫死 28/20/52。"""
    text = engine()._jockey_trainer_weights_text()
    parts = MATRIX_FORMULAS["jockey_trainer"]
    total = sum(w for _, w in parts)
    for _, w in parts:
        assert f"{w / total:.1%}" in text
    assert "52%" not in text


def test_form_flattered_has_a_description():
    """#9：風險標記唔可以印英文 key。"""
    desc = engine()._au_risk_flag_description("form_flattered")
    assert desc != "form_flattered" and "不入分" in desc


def test_reference_leaf_labels_say_what_they_measure():
    """#10／#11：health_score 只計距上仗日數；confidence_score 只數資料錨點。"""
    assert FEATURE_LABELS["health_score"] == "出賽間隔分"
    assert FEATURE_LABELS["confidence_score"] == "資料覆蓋分"


def test_race_shape_tag_admits_the_draw_overlay():
    """#5：檔位形勢冇六維係數，但檔位分經大場次檔位入綜合分。"""
    tag = renderer._reference_tag("race_shape")
    assert tag.startswith("（參考") and "入綜合分" in tag
    assert renderer._reference_tag("form_line") == "（參考·不入排名）"


def test_dashboard_still_recognises_both_tags():
    import re
    pat = r'^\*\*(.+?)[：:]\s*([\d.]+)\s*分\s*([✅➖⚠️❌]+)\s*(.*?)\*\*\s*(（參考[^）]*）)?$'
    for tag in ("（參考·不入排名）", renderer._reference_tag("race_shape")):
        m = re.match(pat, f"**檔位形勢：60.0 分　➖ 中性**　{tag}")
        assert m and m.group(5) == tag
