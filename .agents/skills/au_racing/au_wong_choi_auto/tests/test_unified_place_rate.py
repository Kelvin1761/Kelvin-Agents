#!/usr/bin/env python3
"""統一上名率取代 jockey/trainer 分嘅回歸測試（2026-08-01）。

舊做法：jockey_score 優先用薄 DB tier、LY 只做 fallback；trainer_ly 完全冇入分。
新做法：Racenet 全庫生涯 place% 優先，冇就用去年官方 —— 兩者同一個 prior、
同一條收縮公式，所以係**同一把標尺、100% 覆蓋**。

⚠️ 統一標尺唔可以慳：只用 profile 覆蓋得 64%/57%，同場撈亂兩把標尺，
實測 dev Gold −3。
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))

import pytest  # noqa: E402

import engine_core  # noqa: E402
from engine_core import RacingEngine  # noqa: E402

CTX = {"distance": "1400m", "field_summary": {"count": 10},
       "meeting_intelligence": {"venue": "Randwick", "going": "Good 4"}}


@pytest.fixture(autouse=True)
def fake_profiles(monkeypatch):
    """固定一份 profile cache，令測試唔依賴真實抓取結果。"""
    table = {
        "jockey|star-rider": {"name": "Star Rider", "stats":
                              {"totalRuns": 8000, "placePercentage": 50}},
        "jockey|weak-rider": {"name": "Weak Rider", "stats":
                              {"totalRuns": 8000, "placePercentage": 25}},
        "trainer|big-stable": {"name": "Big Stable", "stats":
                               {"totalRuns": 9000, "placePercentage": 50}},
        "jockey|thin-rider": {"name": "Thin Rider", "stats":
                              {"totalRuns": 4, "placePercentage": 100}},
    }
    monkeypatch.setattr(engine_core, "_PROFILE_STATS_CACHE", table)
    return table


def engine(*, jockey="Nobody", trainer="Nobody", jockey_ly=None, trainer_ly=None):
    data = {}
    if jockey_ly is not None:
        data["jockey_ly"] = jockey_ly
    if trainer_ly is not None:
        data["trainer_ly"] = trainer_ly
    horse = {"horse_name": "T", "horse_number": "1", "barrier": 5,
             "jockey": jockey, "trainer": trainer, "_data": data}
    return RacingEngine(horse, dict(CTX))


class TestSourcePriority:
    def test_profile_career_beats_last_year(self):
        """有 Racenet 生涯數字就用佢，唔用 LY。"""
        eng = engine(jockey="Star Rider", jockey_ly={"rides": 100, "places": 20})
        score, note, src = eng._jockey_score()
        assert src == "unified_place_rate"
        assert "Racenet 生涯" in note
        assert score > 60          # 50% 上名率遠高過 36% 基準

    def test_falls_back_to_last_year_without_profile(self):
        eng = engine(jockey="Zzz Nobody Special", jockey_ly={"rides": 120, "places": 30})
        score, note, src = eng._jockey_score()
        assert src == "unified_place_rate"
        assert "去年官方" in note
        assert score < 60          # 25% 遠低過 36% 基準

    def test_stronger_record_scores_higher(self):
        strong = engine(jockey="Star Rider")._jockey_score()[0]
        weak = engine(jockey="Weak Rider")._jockey_score()[0]
        assert strong > weak


class TestThinSampleGuard:
    def test_thin_profile_is_ignored(self):
        """4 場 100% 上名係噪音，唔可以當訊號 —— 同 _trainer_empirical_base
        嘅 10 場門檻一致。"""
        eng = engine(jockey="Thin Rider")
        score, _note, src = eng._jockey_score()
        assert src != "unified_place_rate"
        assert score == pytest.approx(60.0)

    def test_thin_last_year_declines_the_unified_path(self):
        """5 騎太薄，統一上名率唔接。

        ⚠️ 已知不一致：跌落去嘅舊 `_jockey_ly_score` fallback **冇**最低場數
        guard，所以最終仍然會由 5 騎推出一個非中性分（實測 56.7）。
        嗰條路徑係之前 A/B 調校過（prior .365 / spread 100），冇新證據之前
        唔改佢；呢個測試只鎖住「統一路徑會拒絕薄樣本」。
        """
        eng = engine(jockey="Zzz Nobody", jockey_ly={"rides": 5, "places": 1})
        assert eng._place_rate_score("jockey") is None
        _score, _note, src = eng._jockey_score()
        assert src == "jockey_ly_stats"


class TestTrainerIntegration:
    def test_unified_becomes_the_base(self):
        eng = engine(trainer="Big Stable")
        eng._trainer_score()
        assert eng.trainer_detail["base_label"] == "統一上名率"
        assert "Racenet 生涯" in eng.trainer_detail["base_evidence"]

    def test_empirical_fill_does_not_double_count(self):
        """統一上名率已經食咗 LY，`_trainer_empirical_base` 唔可以再加一次。"""
        eng = engine(trainer="Zzz Unlisted Stable",
                     trainer_ly={"rides": 60, "wins": 10, "places": 24})
        eng._trainer_score()
        factors = [a["factor"] for a in eng.trainer_detail["adjustments"]]
        assert "去年實證班底水準" not in factors

    def test_ly_off_switch_still_works(self):
        """`_TRAINER_LY_MAGNITUDE = 0` 一直係「關掉去年記錄影響」嘅 A/B 開關；
        統一上名率唔可以令佢失效（Racenet 生涯係另一個源，唔受此開關管）。"""
        class Off(RacingEngine):
            _TRAINER_LY_MAGNITUDE = 0.0

        horse = {"horse_name": "T", "horse_number": "1", "barrier": 5,
                 "jockey": "Nobody", "trainer": "Zzz Unlisted Stable",
                 "_data": {"trainer_ly": {"rides": 60, "wins": 10, "places": 24}}}
        assert Off(horse, dict(CTX))._trainer_score()[0] == pytest.approx(60.0, abs=0.1)

    def test_profile_source_ignores_the_ly_off_switch(self):
        class Off(RacingEngine):
            _TRAINER_LY_MAGNITUDE = 0.0

        horse = {"horse_name": "T", "horse_number": "1", "barrier": 5,
                 "jockey": "Nobody", "trainer": "Big Stable", "_data": {}}
        eng = Off(horse, dict(CTX))
        eng._trainer_score()
        assert eng.trainer_detail["base_label"] == "統一上名率"


class TestNarrativeTruth:
    def test_base_label_reports_the_real_source(self):
        """base 由統一上名率嚟就唔可以寫「Tier 1 精英馬房」—— 數字點嚟就寫點嚟。"""
        eng = engine(trainer="Big Stable")
        eng._trainer_score()
        assert eng.trainer_detail["base_label"] == "統一上名率"

    def test_evidence_states_sample_and_baseline(self):
        eng = engine(jockey="Star Rider")
        _score, note, _src = eng._jockey_score()
        assert "8000 場" in note and "全國基準" in note
