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
sys.path.insert(0, str(SCRIPTS / "racing_engine"))

import pytest  # noqa: E402

from engine_core import RacingEngine  # noqa: E402

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
        assert engine(jockey="Zzz Nobody")._place_rate_score("jockey") is None


class TestThinSampleGuard:
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

    def test_thin_sample_cannot_masquerade_as_elite(self):
        """4 場 100% 上名係噪音。以前呢個 case 由 Racenet profile 餵入，
        而家由 LY 餵入 —— 門檻要照樣擋住佢。"""
        eng = engine(jockey="Thin Rider", jockey_ly={"rides": 4, "places": 4})
        assert eng._place_rate_score("jockey") is None


class TestTrainerIntegration:
    def test_unified_becomes_the_base(self):
        eng = engine(trainer="Big Stable", trainer_ly={"rides": 900, "places": 450})
        eng._trainer_score()
        assert eng.trainer_detail["base_label"] == "統一上名率"
        assert "去年官方" in eng.trainer_detail["base_evidence"]

    def test_empirical_fill_does_not_double_count(self):
        """統一上名率已經食咗 LY，`_trainer_empirical_base` 唔可以再加一次。"""
        eng = engine(trainer="Zzz Unlisted Stable",
                     trainer_ly={"rides": 60, "wins": 10, "places": 24})
        eng._trainer_score()
        factors = [a["factor"] for a in eng.trainer_detail["adjustments"]]
        assert "去年實證班底水準" not in factors

    def test_ly_off_switch_still_works(self):
        """`_TRAINER_LY_MAGNITUDE = 0` 一直係「關掉去年記錄影響」嘅 A/B 開關。

        ⚠️ 剷走 Racenet 分支之後呢個開關嘅覆蓋面**闊咗** —— 以前 profile
        來源唔受它管，而家冇 profile 來源，所以佢等於關掉整個騎練基準。
        呢個係剷分支嘅直接後果，記住咗，唔係 bug。
        """
        class Off(RacingEngine):
            _TRAINER_LY_MAGNITUDE = 0.0

        horse = {"horse_name": "T", "horse_number": "1", "barrier": 5,
                 "jockey": "Nobody", "trainer": "Zzz Unlisted Stable",
                 "_data": {"trainer_ly": {"rides": 60, "wins": 10, "places": 24}}}
        assert Off(horse, dict(CTX))._trainer_score()[0] == pytest.approx(60.0, abs=0.1)


class TestNarrativeTruth:
    def test_base_label_reports_the_real_source(self):
        """base 由統一上名率嚟就唔可以寫「Tier 1 精英馬房」—— 數字點嚟就寫點嚟。"""
        eng = engine(trainer="Big Stable", trainer_ly={"rides": 900, "places": 450})
        eng._trainer_score()
        assert eng.trainer_detail["base_label"] == "統一上名率"

    def test_evidence_states_sample_and_baseline(self):
        eng = engine(jockey="Star Rider", jockey_ly={"rides": 800, "places": 400})
        _score, note, _src = eng._jockey_score()
        assert "800 場" in note and "全國基準" in note
