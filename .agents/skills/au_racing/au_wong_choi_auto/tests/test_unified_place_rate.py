#!/usr/bin/env python3
"""統一上名率取代 jockey/trainer 分嘅回歸測試（2026-08-01，2026-08-04 改寫）。

舊做法：jockey_score 優先用薄 DB tier、LY 只做 fallback；trainer_ly 完全冇入分。
新做法：一把標尺 —— 同一個 prior、同一條收縮公式，100% 覆蓋。

**2026-08-04：來源只剩一個。** 呢度以前有一條「Racenet 全庫生涯 place% 優先」
嘅分支排喺去年官方前面。實測佢**從來冇行到**：`AU_Profile_Stats_Cache.json`
152 個人物冇一個夠 `_PLACE_RATE_MIN_RUNS`，604 場分析檔「Racenet 生涯」出現
0 次、「去年官方」34,766 次。Racenet 亦已全封，個 cache 永遠 refresh 唔到，
所以整條分支同 `au_profile_stats.py` 一併剷走。

呢個檔測嘅係剩返嗰條路 —— Sportsbet 個人頁嘅 12 個月記錄。要守住嘅性質同
以前一樣：**薄樣本要拒絕、唔可以重複計、講數字嗰陣要講真來源。**
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

from au_racing_engine import jockey_trainer as jt  # noqa: E402
from au_racing_engine.engine_core import RacingEngine  # noqa: E402

CTX = {"distance": "1400m", "field_summary": {"count": 10},
       "meeting_intelligence": {"venue": "Randwick", "going": "Good 4"}}


def engine(*, jockey="Nobody", trainer="Nobody", jockey_ly=None, trainer_ly=None):
    data = {}
    if jockey_ly is not None:
        data["jockey_ly"] = jockey_ly
    if trainer_ly is not None:
        data["trainer_ly"] = trainer_ly
    horse = {"horse_name": "T", "horse_number": "1", "barrier": 5,
             "jockey": jockey, "trainer": trainer, "_data": data}
    return RacingEngine(horse, dict(CTX))


class TestSingleSource:
    def test_last_year_official_is_the_only_source(self):
        """一把尺，一個來源。註腳要寫「去年官方」，唔可以再出現 Racenet。"""
        eng = engine(jockey="Star Rider", jockey_ly={"rides": 800, "places": 400})
        score, note, src = eng._jockey_score()
        assert src == "unified_place_rate"
        assert "去年官方" in note
        assert "Racenet" not in note
        assert score > 60          # 50% 上名率遠高過 36% 基準

    def test_weak_record_scores_below_neutral(self):
        eng = engine(jockey="Weak Rider", jockey_ly={"rides": 800, "places": 200})
        score, note, src = eng._jockey_score()
        assert src == "unified_place_rate"
        assert score < 60          # 25% 遠低過 36% 基準

    def test_stronger_record_scores_higher(self):
        strong = engine(jockey="A", jockey_ly={"rides": 800, "places": 400})
        weak = engine(jockey="B", jockey_ly={"rides": 800, "places": 200})
        assert strong._jockey_score()[0] > weak._jockey_score()[0]

    def test_no_record_leaves_the_unified_path_alone(self):
        """冇記錄唔可以砌一個分出嚟 —— 呢個係 `_PLACE_RATE_PRIOR` 之外嘅事。"""
        assert jt.rate_score("jockey", {}) is None


class TestThinSampleGuard:
    def test_thin_last_year_is_neutral(self):
        """5 騎太薄：同練馬師一樣中性 60（EXP-20261103-06；以前跌落另一把尺，5 騎 1 上名 → 56.7）。"""
        eng = engine(jockey="Zzz Nobody", jockey_ly={"rides": 5, "places": 1})
        assert jt.rate_score("jockey", {"rides": 5, "places": 1}) is None
        score, _note, src = eng._jockey_score()
        assert score == 60 and src == "jockey_missing_neutral"
        assert "未達 10 場" in eng.jockey_detail["lines"][0]
        assert eng._feature_evidence_state("jockey_score", src) == "fallback"

    def test_trainer_without_record_is_not_evidence(self):
        """練馬師冇統一率又冇 tier → fallback（以前永遠 observed）。"""
        eng = engine(trainer="Zzz Unlisted Stable", trainer_ly={"rides": 4, "places": 1})
        _s, _n, src = eng._trainer_score()
        assert eng._feature_evidence_state("trainer_score", src) == "fallback"
        big = engine(trainer="Big Stable", trainer_ly={"rides": 900, "places": 450})
        _s, _n, src = big._trainer_score()
        assert big._feature_evidence_state("trainer_score", src) == "observed"

    def test_thin_sample_cannot_masquerade_as_elite(self):
        """4 場 100% 上名係噪音。以前呢個 case 由 Racenet profile 餵入，
        而家由 LY 餵入 —— 門檻要照樣擋住佢。"""
        assert jt.rate_score("jockey", {"rides": 4, "places": 4}) is None


class TestTrainerIntegration:
    def test_unified_becomes_the_base(self):
        eng = engine(trainer="Big Stable", trainer_ly={"rides": 900, "places": 450})
        eng._trainer_score()
        assert eng.trainer_detail["base_label"] == "統一上名率"
        assert "去年官方" in eng.trainer_detail["base_evidence"]

    def test_no_second_last_year_term(self):
        """統一上名率已經食咗 LY；唔可以再有第二條 LY 加減分（舊 empirical fill 已剷）。"""
        eng = engine(trainer="Zzz Unlisted Stable",
                     trainer_ly={"rides": 60, "wins": 10, "places": 24})
        eng._trainer_score()
        assert all(a["delta"] == 0.0 for a in eng.trainer_detail["adjustments"])


class TestNarrativeTruth:
    def test_base_label_reports_the_real_source(self):
        """base 由統一上名率嚟就唔可以寫「Tier 1 精英馬房」—— 數字點嚟就寫點嚟。"""
        eng = engine(trainer="Big Stable", trainer_ly={"rides": 900, "places": 450})
        eng._trainer_score()
        assert eng.trainer_detail["base_label"] == "統一上名率"

    def test_evidence_states_sample_and_baseline(self):
        eng = engine(jockey="Star Rider", jockey_ly={"rides": 800, "places": 400})
        _score, note, src = eng._jockey_score()
        assert "800 場" in note and "全國基準" in note
        assert eng._feature_evidence_state("jockey_score", src) == "observed"
