#!/usr/bin/env python3
"""2026-08-01「令 60 真係中性」修正嘅回歸測試。

用戶投訴：檔位形勢／級數與負重／Rating／級數／負磅 好似永遠停喺 60，而 段速分
永遠 ~40 —— 明明 段速實速分 顯示「近3場快過基準 1.54 秒」。710 場實測拆解：

  檔位形勢  範圍 46.3–**59.75** —— 60 係天花板，唔係中性（0.0% 曾高過 60）
  段速分    38.1% 卡喺 base **35.8** —— 「冇 PI 數據」同「PI 顯示冇後勁」同分，
            而「冇數據」嗰批 top-3 率 30.1% *高過*樣本平均
  負磅分    84.9% 恰好 60、within-race AUC 0.480 —— 真噪音，已退出排名

呢個檔鎖住修正之後嘅不變量，唔係鎖住具體分值。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))

import pytest  # noqa: E402

import engine_core  # noqa: E402
from engine_core import RacingEngine, backfill_pf_metrics  # noqa: E402
from matrix_mapper import (  # noqa: E402
    MATRIX_DISPLAY_GAINS,
    MATRIX_FORMULAS,
    map_features_to_matrix_scores,
)
from scoring import (  # noqa: E402
    MATRIX_WEIGHTS,
    PACE_MICRO_WEIGHTS,
    SECTIONAL_MICRO_WEIGHTS,
    WET_FORM_FEATURE_SCALE,
    WET_FORM_MAX_ABS,
)

HEADER = (
    "| # | 類型 | 日期 | 場地 | 路程 | 場地狀況 | 檔位 | 名次 | 班次 | 跑位軌跡 "
    "| PI | 段速 | 早段步速 | L600/RT | 走位跑法 | 走位消耗 | 備註 | 寬恕認定 | 獎金 |\n"
    "|---|------|------|------|------|---------|------|------|------|---------"
    "|-----|------|---------|---------|---------|---------|------|----------|------|\n"
)


def facts(rows):
    body = ""
    for index, (placing, pi) in enumerate(rows, 1):
        body += (
            f"| {index} | Maiden/SW | 2026-0{min(index, 9)}-01 | Track{index} R1 "
            f"| 1400m | 5 | 5 | {placing} | - | S5→F{placing} | {pi} | - | - | - "
            f"| 守中 | 中低 | - | [需判定] | $40,000 |\n"
        )
    return "### 馬匹 #1 Test\n" + HEADER + body


def engine(rows=(), *, race_context=None, horse_extra=None):
    block = facts(rows) if rows else "### 馬匹 #1 Test\n" + HEADER
    horse = {
        "horse_name": "Test",
        "horse_number": "1",
        "barrier": 5,
        "weight": 58.0,
        "_data": {"facts_section": block, "career_record_line": "10:1-1-2"},
    }
    horse.update(horse_extra or {})
    context = {"race_class": "BM62, Handicap", "distance": "1400m"}
    context.update(race_context or {})
    return RacingEngine(horse, context, facts_section=block)


class TestSectionalNeutralBase:
    """段速分：冇證據 = 中性，唔係最差。"""

    def test_base_is_neutral_sixty(self):
        assert SECTIONAL_MICRO_WEIGHTS["base"] == 60.0

    def test_no_pi_data_scores_exactly_neutral(self):
        breakdown = engine()._sectional_breakdown()
        assert breakdown["has_pi"] is False
        assert breakdown["score"] == pytest.approx(60.0)

    def test_ladder_tops_out_at_one_hundred_without_clipping(self):
        """最高路徑要剛好用盡 0-100 尺 —— 撞 clip 會製造假平手。"""
        best = (
            SECTIONAL_MICRO_WEIGHTS["base"]
            + SECTIONAL_MICRO_WEIGHTS["pi_extreme_bonus"]
            + SECTIONAL_MICRO_WEIGHTS["l600_extreme_bonus"]
            + max(
                SECTIONAL_MICRO_WEIGHTS["realization_bonus"],
                SECTIONAL_MICRO_WEIGHTS["forgiveness_bonus"],
            )
        )
        assert best == pytest.approx(100.0, abs=0.01)

    def test_positive_pi_reads_above_neutral(self):
        breakdown = engine([("3", "+3"), ("2", "+3"), ("3", "+3")])._sectional_breakdown()
        assert breakdown["has_pi"] is True
        assert breakdown["score"] > 60.0


class TestPaceMapNeutralBase:
    """檔位形勢：好檔位一定要讀得出「高過中性」。"""

    def test_base_is_neutral_sixty(self):
        assert PACE_MICRO_WEIGHTS["base"] == 60.0

    def test_favourable_draw_can_exceed_neutral(self):
        """舊 base 55.7 ＋ 上限 +4.05 → 全庫最高 59.75，即係永遠出唔到「著數」。"""
        ceiling = PACE_MICRO_WEIGHTS["base"] + PACE_MICRO_WEIGHTS["modifier_cap_max"]
        assert ceiling > 60.0

    def test_race_shape_dimension_is_the_leaf_stretched_by_its_display_gain(self):
        """race_shape has one leaf, so the dimension IS pace_map on the shared ruler.

        Not 1:1 any more — the display gain (2026-08-01) puts every dimension on
        one scale so the bands mean the same thing across the matrix.
        """
        gain = MATRIX_DISPLAY_GAINS["race_shape"]
        scores = map_features_to_matrix_scores({"pace_map_score": 64.0})
        assert scores["race_shape"] == pytest.approx(60.0 + 4.0 * gain, abs=0.02)
        assert scores["race_shape"] > 70.0, "a top draw must be able to read ✅"

    def test_every_dimension_can_reach_both_positive_bands(self):
        """Before normalisation, race_shape / jockey_trainer / class_weight could
        never show ✅ whatever the horse did — 3 of 6 scoring dimensions were mute."""
        for dim, gain in MATRIX_DISPLAY_GAINS.items():
            observed_max = OBSERVED_RAW_MAX[dim]
            stretched = 60.0 + (observed_max - 60.0) * gain
            assert stretched >= 70.0, f"{dim} still cannot reach ✅ (max {stretched:.1f})"
            assert stretched <= 100.0, f"{dim} overshoots the scale ({stretched:.1f})"


# Raw (pre-normalisation) dimension extremes over the 710-race archive. Used to
# check the gains stretch far enough to be useful but not so far that the 0/100
# clip starts manufacturing ties.
OBSERVED_RAW_MAX = {
    "stability": 100.0, "pace_perf": 98.1, "race_shape": 64.0,
    "jockey_trainer": 75.6, "class_weight": 69.5, "track": 85.7,
    "form_line": 98.1,
}
OBSERVED_RAW_MIN = {
    "stability": 41.6, "pace_perf": 15.8, "race_shape": 50.6,
    "jockey_trainer": 41.2, "class_weight": 50.9, "track": 42.9,
    "form_line": 51.7,
}


class TestDimensionScaleAndWeightsStayInLockstep:
    """尺同權重必須一齊改 —— 排名只食 weight × gain × deviation。"""

    # 2026-08-01 之前嘅權重（gain 全部 = 1 時使用）
    PRE_NORMALISATION_WEIGHTS = {
        "stability": 0.29928, "pace_perf": 0.18831, "race_shape": 0.14855,
        "jockey_trainer": 0.19408, "class_weight": 0.04535, "track": 0.12443,
        "form_line": 0.0,
    }

    # 2026-08-01 正規化配套嘅 rank-neutral 權重（= 舊權重 ÷ gain，歸一化）。
    # 已經**唔再係出廠值** —— 之後有一次刻意嘅重新配權（見下面）。
    RANK_NEUTRAL_WEIGHTS = {
        "stability": 0.43664, "pace_perf": 0.26149, "race_shape": 0.05136,
        "jockey_trainer": 0.11055, "class_weight": 0.02347, "track": 0.11650,
        "form_line": 0.0,
    }

    def test_the_normalisation_itself_was_rank_neutral(self):
        """歷史不變量：**尺正規化嗰一步**冇偷偷 re-weight 過。

        排名只食 weight × gain × deviation。正規化把每個維度嘅顯示尺 stretch 咗，
        所以配套權重必須 ÷ 返個 gain，令 weight × gain 相對舊權重係**同一個**
        常數（1.4225，逐個一模一樣，唔係「差唔多」）。

        呢個測試釘住嗰一步嘅正確性，用嘅係當時嗰組權重 —— **唔係**用現行
        `MATRIX_WEIGHTS`。現行嗰組係之後經 A/B 刻意改過排名嘅，見
        `test_current_weights_are_a_deliberate_refit_not_a_rescale`。
        """
        ratios = [
            self.RANK_NEUTRAL_WEIGHTS[dim] * MATRIX_DISPLAY_GAINS[dim] / old
            for dim, old in self.PRE_NORMALISATION_WEIGHTS.items()
            if old
        ]
        assert max(ratios) - min(ratios) < 1e-3, (
            f"influence ratios drifted apart: {ratios} — the scale change silently "
            "re-weighted the matrix"
        )

    def test_current_weights_are_a_deliberate_refit_not_a_rescale(self):
        """現行權重**唔應該**再係 rank-neutral —— 佢係一次經驗證嘅重新配權。

        2026-08-01（較後）：3,000 條隨機權重、dev 606 場、5 個時間 fold 閘、
        取閘後候選嘅逐維度中位數。713 場全樣本 11 個指標全部改善。

        呢個測試存在嘅意義係防止有人「修正」返去 rank-neutral 嗰組（睇落似
        一致，實際係倒退）。如果將來真係要回滾，連埋呢個測試一齊改，
        唔好淨係改 MATRIX_WEIGHTS。
        """
        assert MATRIX_WEIGHTS != self.RANK_NEUTRAL_WEIGHTS
        # 重新配權嘅方向：人騎／練馬師 ↑、狀態穩定性 ↓ —— 八次獨立搜索一致
        assert MATRIX_WEIGHTS["jockey_trainer"] > self.RANK_NEUTRAL_WEIGHTS["jockey_trainer"]
        assert MATRIX_WEIGHTS["stability"] < self.RANK_NEUTRAL_WEIGHTS["stability"]

    def test_weights_sum_to_one(self):
        """Σw ≠ 1 會令 ability 唔再係 0-100 尺（每個維度都 60-centred）。"""
        assert sum(MATRIX_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-4)

    def test_wet_overlay_tracks_the_ability_spread(self):
        """濕地 overlay 直接加落 ability 分，唔經矩陣 —— ability spread 一變，
        overlay 唔跟就會靜靜雞縮水／發脹。實測唔跟 → 71 場排名有變，其中 70 場係濕地。

        累積係數 = 1.4225（維度尺正規化令 spread 放大）
                 × 0.9315（2026-08-01 重配權，場內 pure_7d SD 5.1211→4.7702）
                 × 0.8471（2026-08-03 Sportsbet 重配權，SD 4.4085→3.7344）
        全部都係**量度出嚟**嘅比例，唔係搵返嚟嘅參數。每次動 MATRIX_WEIGHTS
        都要重新量 SD 再乘上去 —— 呢個測試就係逼你唔好漏。
        """
        cumulative = 1.4225 * 0.9315 * 0.8471
        assert WET_FORM_FEATURE_SCALE == pytest.approx(12.0 * cumulative, rel=0.01)
        assert WET_FORM_MAX_ABS == pytest.approx(5.0 * cumulative, rel=0.01)

    def test_overlay_scale_and_clamp_moved_together(self):
        """scale 同 clamp 一定要同一個係數 —— 淨係郁一邊會改變 overlay 嘅形狀，
        而唔係佢嘅大細，咁就唔再係原本校準過嗰個 feature。"""
        assert WET_FORM_FEATURE_SCALE / 12.0 == pytest.approx(
            WET_FORM_MAX_ABS / 5.0, rel=0.005)

    def test_gains_never_drive_dimensions_into_the_clip(self):
        """撞 0/100 會製造假平手。實測正規化後 0/52,710 個維度值撞 clip。"""
        for dim, gain in MATRIX_DISPLAY_GAINS.items():
            hi = 60.0 + (OBSERVED_RAW_MAX[dim] - 60.0) * gain
            lo = 60.0 + (OBSERVED_RAW_MIN[dim] - 60.0) * gain
            assert hi <= 99.5, f"{dim} top {hi:.1f} is at the ceiling"
            assert lo >= 0.5, f"{dim} bottom {lo:.1f} is at the floor"


class TestWeightLeafRetired:
    """負磅分：AUC 0.480，退出排名但保留報告內容。"""

    def test_not_a_class_weight_scoring_leaf(self):
        leaves = {name for name, _weight in MATRIX_FORMULAS["class_weight"]}
        assert "weight_score" not in leaves

    def test_still_computed_for_the_report(self):
        score, note, source = engine()._weight_score()
        assert note
        assert source

    def test_components_flag_zero_weight_entries(self):
        auto = engine([("3", "+1")]).analyze_horse()
        components = auto["matrix_reasoning"]["class_weight"]["components"]
        by_key = {component["key"]: component for component in components}
        assert by_key["rating_score"]["in_ranking"] is True
        assert by_key["weight_score"]["in_ranking"] is False
        assert by_key["class_score"]["in_ranking"] is False


class TestHandicapWeightProxy:
    """負磅喺 rating 缺失嗰度唔重複 —— 呢度先係佢應該出力嘅位。"""

    FIELD = {
        "count": 10,
        "weighted_count": 10,
        "avg_weight": 56.0,
        "weight_stdev": 1.5,
        "min_weight": 54.0,
        "max_weight": 59.0,
        "rated_count": 0,
    }

    def test_topweight_proxies_above_neutral(self):
        eng = engine(race_context={"field_summary": self.FIELD})
        score, line = eng._handicap_weight_proxy()
        assert score > 60.0            # 58.0kg vs 場均 56.0 → 讓磅官評為較高能力
        assert "讓磅" in line

    def test_refused_in_set_weights_races(self):
        """定磅/WFA 賽負磅由年齡性別決定，冇能力訊號。"""
        eng = engine(
            race_context={
                "field_summary": self.FIELD,
                "race_class": "3-Y-O, Set Weights",
            }
        )
        assert eng._handicap_weight_proxy() == (None, "")

    def test_refused_when_field_barely_separated(self):
        field = dict(self.FIELD, weight_stdev=0.1)
        eng = engine(race_context={"field_summary": field})
        assert eng._handicap_weight_proxy() == (None, "")

    def test_rating_fallback_blends_class_and_weight(self):
        eng = engine(race_context={"field_summary": self.FIELD})
        score, note, source = eng._rating_score()
        assert source == "class_weight_proxy"
        class_proxy = eng._class_score()[0]
        weight_proxy, _ = eng._handicap_weight_proxy()
        assert score == pytest.approx(0.5 * class_proxy + 0.5 * weight_proxy, abs=0.05)

    def test_rating_fallback_stays_class_only_without_usable_weight(self):
        eng = engine(
            race_context={
                "field_summary": dict(self.FIELD, weight_stdev=0.0),
            }
        )
        _score, _note, source = eng._rating_score()
        assert source == "class_proxy"


class TestPfBackfillIsOptIn:
    """PF 歷史回填：已接通但**預設 OFF**（opt in: WC_PF_BACKFILL=1）。

    2026-08-01 喺合併後配置下覆核過，維持 OFF：dev champ −1.65、good_any2 −0.82
    （gold +1、good_pos +0.66、blowout −0.99 係得益嗰邊），holdout 全部 0.00。
    中途一度以為結論反轉，係因為量度時漏咗 `MATRIX_DISPLAY_GAINS`。

    ⚠️ 呢啲測試要分得清「因為 gate 擋咗而回 0」同「因為冇 cache 而回 0」——
    原版靠 tmp_path 冇 cache 嚟得出 0，所以就算 default 翻轉咗都照樣通過，
    即係守唔到嘢。
    """

    @staticmethod
    def _logic():
        return {"race_analysis": {"race_number": 1}, "horses": {"1": {"_data": {}}}}

    def test_gated_off_by_default(self, tmp_path, monkeypatch):
        """冇設環境變數 → 要喺 cache lookup **之前**短路。"""
        monkeypatch.delenv("WC_PF_BACKFILL", raising=False)

        def explode(*a, **k):
            raise AssertionError("預設 OFF，唔應該去到 cache lookup")

        monkeypatch.setattr(engine_core, "_pf_backfill_for_race", explode)
        assert backfill_pf_metrics(self._logic(), tmp_path / "Race_1_Logic.json") == 0

    def test_opt_in_reaches_the_cache_lookup(self, tmp_path, monkeypatch):
        """`WC_PF_BACKFILL=1` → gate 唔應該擋，要真係行到 lookup。"""
        monkeypatch.setenv("WC_PF_BACKFILL", "1")
        reached = []
        monkeypatch.setattr(engine_core, "_pf_backfill_for_race",
                            lambda *a, **k: reached.append(a) or {})
        backfill_pf_metrics(self._logic(), tmp_path / "Race_1_Logic.json")
        assert reached, "開咗 flag 就應該行到 cache lookup"

    def test_no_op_without_a_path(self, monkeypatch):
        """冇 facts_path 就搵唔到 meeting key —— 呢個短路同 flag 無關。"""
        monkeypatch.setenv("WC_PF_BACKFILL", "1")
        assert backfill_pf_metrics(self._logic(), None) == 0

    def test_missing_cache_is_safe(self, tmp_path, monkeypatch):
        """開咗 flag 但附近冇 cache → 安全回 0，唔會拋錯。"""
        monkeypatch.setenv("WC_PF_BACKFILL", "1")
        meeting = tmp_path / "2026-01-01 Nowhere Race 1-8"
        meeting.mkdir()
        assert backfill_pf_metrics(self._logic(), meeting / "Race_1_Logic.json") == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
