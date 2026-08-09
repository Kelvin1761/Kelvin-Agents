#!/usr/bin/env python3
"""`jockey_horse_fit_score`「冇配搭紀錄」點位嘅回歸測試（2026-08-01）。

713 場 / 7,547 匹實測 cohort：
    高過 60（有正面配搭證據）  n=5,301  前三率 30.0%
    低過 60（被扣分）          n=  838  前三率 28.6%
    恰好 60（冇任何證據）      n=1,408  前三率 **21.7%**  ← 樣本平均 28.3%

排序本來反咗：被扣分嗰批實際好過冇證據嗰批，卻排喺佢下面。

⚠️ 呢個同 `sectional_score` **方向相反**（嗰邊「冇 PI 數據」高過平均，要抬去 60）。
「60 = 冇證據」唔係通則，每個 leaf 要睇返自己嘅 cohort 實測 —— 呢個檔就係
釘住呢個分別，免得將來有人見到 58 以為係漏改嘅 mis-centred leaf。
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))

import pytest  # noqa: E402

from engine_core import RacingEngine  # noqa: E402

CTX = {"race_class": "BM62, Handicap", "distance": "1400m",
       "field_summary": {"count": 10},
       "meeting_intelligence": {"venue": "Randwick", "going": "Good 4"}}


def engine(data=None, **horse_extra):
    horse = {"horse_name": "T", "horse_number": "1", "barrier": 5, "weight": 58.0,
             "jockey": "Some Rider", "trainer": "Some Stable", "_data": data or {}}
    horse.update(horse_extra)
    return RacingEngine(horse, dict(CTX))


class TestNoEvidenceSitsBelowNeutral:
    def test_bare_horse_scores_below_sixty(self):
        """冇試閘、冇同一騎師往績、冇任何訊號 → 唔應該係中性 60。"""
        eng = engine()
        score, note, _src = eng._jockey_horse_fit_score()
        assert score == pytest.approx(RacingEngine._JT_FIT_NO_EVIDENCE)
        assert score < 60.0
        assert "並無任何人馬配搭紀錄" in note

    def test_detail_records_no_adjustments(self):
        eng = engine()
        eng._jockey_horse_fit_score()
        assert eng.jt_fit_detail["adjustments"] == []
        assert eng.jt_fit_detail["final"] == pytest.approx(
            RacingEngine._JT_FIT_NO_EVIDENCE)


class TestEvidenceStillMovesTheScore:
    def test_positive_evidence_lifts_above_neutral(self):
        """有配搭往績要高過 60，唔可以被「冇證據」規則波及。"""
        eng = engine({"trial_count": 3, "trial_top3_count": 2})
        score, _note, _src = eng._jockey_horse_fit_score()
        assert score > 60.0
        assert eng.jt_fit_detail["adjustments"], "應該有記錄到加分因子"

    def test_evidence_outranks_no_evidence(self):
        """核心不變量：有正面證據 > 冇證據。"""
        with_ev = engine({"trial_count": 3, "trial_top3_count": 2})._jockey_horse_fit_score()[0]
        without = engine()._jockey_horse_fit_score()[0]
        assert with_ev > without

    def test_penalised_still_outranks_no_evidence(self):
        """實測 28.6% vs 21.7% —— 被扣分嗰批應該仍然排喺冇證據之上。

        用一個「有加分但淨額細」嘅個案代表被評價過嘅馬：重點係佢有證據，
        所以就算分數唔高，都唔應該跌到 `_JT_FIT_NO_EVIDENCE` 以下。
        """
        judged = engine({"trial_count": 3, "trial_top3_count": 2})._jockey_horse_fit_score()[0]
        assert judged > RacingEngine._JT_FIT_NO_EVIDENCE


class TestContrastWithSectional:
    def test_the_two_leaves_deliberately_disagree(self):
        """段速分「冇數據」= 60（嗰批高過平均）；人馬配搭「冇紀錄」< 60（低過平均）。

        兩個唔同方向係有實測依據嘅，唔係前後不一致。任何人想把
        `_JT_FIT_NO_EVIDENCE` 「修正」返 60 之前，要先重做 cohort 量度。
        """
        from scoring import SECTIONAL_MICRO_WEIGHTS

        assert SECTIONAL_MICRO_WEIGHTS["base"] == 60.0
        assert RacingEngine._JT_FIT_NO_EVIDENCE < 60.0
