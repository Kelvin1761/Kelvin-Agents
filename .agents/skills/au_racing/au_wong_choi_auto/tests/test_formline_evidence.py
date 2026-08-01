#!/usr/bin/env python3
"""賽績線（`formline_score`）唔可以喺冇對手線嘅情況下講「強」（2026-08-02）。

舊行為：冇任何對手線嘅時候，級別由 `formline_line` 個**文字標題**推導。
713 場 / 7,547 匹實測：

    valid=0（冇任何對手強度證據）  6,682 匹 **88.5%**
        分數 平均 75.76 中位 78.0 範圍 57.0–89.5
        場內超額前三率 **+0.0**  ← 完全等於隨機
    valid>=1（有對手線）             865 匹  11.5%

即係八成半嘅馬帶住一個 32 分闊嘅純噪音分佈，全樣本 **79.9%** 係
「冇證據但攞到 >70 分」。個 leaf 場內 ρ = 0.011，12 個 leaf 最差。

⚠️ 呢個唔淨止係排名問題（form_line 維度權重 = 0，唔入排名）。報告會照樣同
用戶講「賽績線強」，而背後乜證據都冇 —— 所以就算永遠唔畀權重都要修。
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))

import pytest  # noqa: E402

from engine_core import RacingEngine  # noqa: E402
from scoring import MATRIX_WEIGHTS  # noqa: E402

CTX = {"race_class": "BM70, Handicap", "distance": "1400m",
       "field_summary": {"count": 10},
       "meeting_intelligence": {"venue": "Flemington", "going": "Good 4"}}


def engine(facts="", **data):
    horse = {"horse_name": "T", "horse_number": "1", "barrier": 4, "weight": 57.0,
             "jockey": "A Rider", "trainer": "A Stable", "_data": dict(data)}
    return RacingEngine(horse, dict(CTX), facts_section=facts)


def facts_with_opponents(*strengths):
    """`_formline_rows` 係由 Facts markdown 解析（唔係 `_data`），所以 fixture
    要砌返張真表：捕捉由「- **🔗 賽績線」開始，每行 7 欄。"""
    lines = ["- **🔗 賽績線**"]
    for i, strength in enumerate(strengths):
        lines.append(f"| 2026-0{i + 1}-01 | R{i + 1} | 3rd | Rival {i} | BM78 | 4th | {strength} |")
    lines.append("- **🔧 引擎與距離**")
    return "\n".join(lines)


class TestHeadlineTextCannotManufactureAStrongFormLine:
    """冇對手線 → 唔准讀文字標題去派級別。"""

    @pytest.mark.parametrize("headline", [
        "賽績線: 極強 | 強組比例: 2/2",
        "賽績線: 強",
        "✅ 賽績線極強，對手成色高",
        "賽績線: 中強",
    ])
    def test_no_opponent_rows_never_reads_the_headline(self, headline):
        eng = engine(formline_line=headline)
        assert eng._formline_support_summary()[1] == 0, "呢個 fixture 應該冇對手線"
        score, *_ = eng._formline_score()
        assert score == pytest.approx(60.0), (
            f"「{headline}」冇任何對手線證據，唔應該高過中性 60（實得 {score}）")

    def test_bare_horse_sits_at_neutral(self):
        score, *_ = engine()._formline_score()
        assert score == pytest.approx(60.0)

    def test_note_says_data_is_insufficient_not_strong(self):
        _score, note, *_ = engine(formline_line="賽績線: 極強")._formline_score()
        assert "資料不足" in note
        assert "頂級" not in note and "級別強" not in note


class TestEvidenceStillSpeaks:
    """有真對手線嗰 11.5% 要照舊講嘢 —— 修法係剪噪音，唔係熄咗個 leaf。"""

    def test_fixture_really_produces_opponent_rows(self):
        """守住呢組 fixture 本身 —— 表格格式一變，下面兩個測試就會靜靜咁
        變成「冇證據」而照樣通過，等於冇測試過。"""
        eng = engine(facts=facts_with_opponents("強組", "強組"))
        assert len(eng._formline_rows()) == 2
        assert eng._formline_support_summary() == (2.0, 2)

    def test_strong_opponent_rows_lift_above_neutral(self):
        score, *_ = engine(facts=facts_with_opponents("強組", "強組"),
                           formline_line="賽績線: 強")._formline_score()
        assert score > 60.0

    def test_weak_opponent_rows_drop_below_neutral(self):
        score, *_ = engine(facts=facts_with_opponents("弱組", "弱組"),
                           formline_line="賽績線: 弱")._formline_score()
        assert score < 60.0

    def test_strong_beats_weak(self):
        strong, *_ = engine(facts=facts_with_opponents("強組", "強組"))._formline_score()
        weak, *_ = engine(facts=facts_with_opponents("弱組", "弱組"))._formline_score()
        assert strong > weak


class TestStillOutOfTheRanking:
    def test_form_line_dimension_weight_stays_zero(self):
        """重建咗都唔代表要畀權重。3,000 條隨機 7 維權重向量，共識仍然係 0.0
        —— 因為 82.3% 嘅馬而家喺中性打平手，場內冇 gradient。
        真係想佢有用，要嘅係**更多對手線數據**，唔係再改分數映射。"""
        assert MATRIX_WEIGHTS.get("form_line", 0.0) == 0.0
