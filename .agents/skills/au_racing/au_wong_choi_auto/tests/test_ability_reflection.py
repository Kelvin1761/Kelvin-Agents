#!/usr/bin/env python3
"""2026-07-31「令 狀態與穩定性 / 段速 真正反映實力」三個修正嘅回歸測試。

  S1  PI 競爭力封頂 —— 大敗/居後場次嘅「追前」唔予計功
  S2  L600 口徑由生涯最快改為平均
  F3  用獎金做真正嘅班次調整（原本 class_mult 係全場統一常數）
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))

import pytest  # noqa: E402

from engine_core import (  # noqa: E402
    CLASS_PRIZE_K,
    RacingEngine,
    _parse_prize,
    horse_prize_level,
)
from scoring import SECTIONAL_MICRO_WEIGHTS  # noqa: E402

HEADER = (
    "| # | 類型 | 日期 | 場地 | 路程 | 場地狀況 | 檔位 | 名次 | 班次 | 跑位軌跡 "
    "| PI | 段速 | 早段步速 | L600/RT | 走位跑法 | 走位消耗 | 備註 | 寬恕認定 | 獎金 |\n"
    "|---|------|------|------|------|---------|------|------|------|---------"
    "|-----|------|---------|---------|---------|---------|------|----------|------|\n"
)


def facts(rows):
    """rows = [(placing, pi, traj, prize)] —— 最新排最前。"""
    body = ""
    for i, (placing, pi, traj, prize) in enumerate(rows, 1):
        body += (
            f"| {i} | Maiden/SW | 2026-0{min(i,9)}-01 | Track{i} R1 | 1400m | 5 | 5 "
            f"| {placing} | - | {traj} | {pi} | - | - | - | 守中 | 中低 | - "
            f"| [需判定] | {prize} |\n"
        )
    return "### 馬匹 #1 Test\n" + HEADER + body


def engine_for(rows, *, field_summary=None, data_extra=None):
    block = facts(rows)
    data = {"facts_section": block, "career_record_line": "10:1-1-2"}
    data.update(data_extra or {})
    horse = {"horse_name": "Test", "barrier": 5, "weight": 58.0,
             "career_race_starts": 10, "career_tag": "ESTABLISHED", "_data": data}
    ctx = {"race_class": "BM62", "distance": "1400m"}
    if field_summary:
        ctx["field_summary"] = field_summary
    return RacingEngine(horse_data=horse, race_context=ctx, facts_section=block)


class TestParsePrize:
    @pytest.mark.parametrize("cell,expected", [
        ("$40,000", 40000), ("40000", 40000), ("$27,000", 27000),
        ("-", None), ("", None), (None, None),
        ("500", None),            # 低過 $1k = 污染
        ("99,000,000", None),     # 高過 $20M = 污染
    ])
    def test_parse(self, cell, expected):
        assert _parse_prize(cell) == expected


class TestHorsePrizeLevel:
    def test_decay_weighted_log10(self):
        """近仗權重高：同樣兩場但次序調換，水平必須唔同。"""
        rich_recent = horse_prize_level(facts([
            ("1", "+0", "S3→F1", "$500,000"), ("5", "+0", "S3→F5", "$30,000")]))
        poor_recent = horse_prize_level(facts([
            ("5", "+0", "S3→F5", "$30,000"), ("1", "+0", "S3→F1", "$500,000")]))
        assert rich_recent > poor_recent

    def test_none_without_prize_column(self):
        legacy = "| 1 | Maiden/SW | 2026-01-01 | T R1 | 1400m | 5 | 5 | 3 | - | S3→F3 | +0 | - | - | - | 守中 | 中低 | - | [需判定] |"
        assert horse_prize_level(legacy) is None

    def test_trials_excluded(self):
        assert horse_prize_level(
            "| 1 | 試閘 | 2026-01-01 | T R1 | 1400m | 5 | 5 | 2 | - | - | - | - | - | - | - | - | - | - | $99,000 |"
        ) is None


class TestSectionalCompetitiveCap:
    """S1：大敗場次嘅「追前」唔應該當後勁證據。"""

    def test_big_margin_gain_earns_nothing(self):
        """定位 11 → 終點 6（PI +5）但輸 9.05L：追前封到 0。"""
        eng = engine_for([("6/12 (-9.05L)", "+5", "S11→8th12→4th11→F6", "$27,000")])
        breakdown = eng._sectional_breakdown()
        pi_item = next(i for i in breakdown["items"] if "位置增益" in i["factor"])
        # 斷定「邊一級觸發」而唔係硬編碼分值 —— 中性化重新標定（2026-08-01）
        # 之後，級數選擇正確但數值變過，寫死常數會誤報。
        assert pi_item["delta"] == pytest.approx(
            SECTIONAL_MICRO_WEIGHTS["pi_pass_bonus"]
        )                                                   # 達標級，唔係優秀級
        assert "不予計功" in pi_item["evidence"]

    def test_competitive_gain_still_rewarded(self):
        """同樣 PI +5 但只輸 1.0L 而且場內前半 → 照樣拿優秀獎勵。"""
        eng = engine_for([("3/12 (-1.0L)", "+5", "S8→8th8→4th5→F3", "$27,000")])
        breakdown = eng._sectional_breakdown()
        pi_item = next(i for i in breakdown["items"] if "位置增益" in i["factor"])
        assert pi_item["delta"] == pytest.approx(
            SECTIONAL_MICRO_WEIGHTS["pi_extreme_bonus"]
        )
        assert "不予計功" not in pi_item["evidence"]

    def test_negative_pi_still_counts_when_capped(self):
        """封頂只封正值：失位（負 PI）呢種弱勢證據一定要保留。"""
        eng = engine_for([("9/10 (-15.0L)", "-4", "S5→8th7→4th9→F9", "$27,000")])
        breakdown = eng._sectional_breakdown()
        pi_item = next(i for i in breakdown["items"] if "位置增益" in i["factor"])
        assert pi_item["delta"] == 0.0
        assert "缺乏後勁" in pi_item["evidence"]

    def test_missing_field_and_margin_is_not_penalised(self):
        """兩樣都唔知 → 保守當有競爭力，行為同修改前一致。"""
        eng = engine_for([("6", "+5", "S11→8th12→4th11→F6", "$27,000")])
        breakdown = eng._sectional_breakdown()
        pi_item = next(i for i in breakdown["items"] if "位置增益" in i["factor"])
        assert pi_item["delta"] == pytest.approx(
            SECTIONAL_MICRO_WEIGHTS["pi_extreme_bonus"]
        )


class TestL600UsesAverage:
    """S2：生涯最快係四個口徑之中預測力最差（ρ 0.023 vs 平均 0.057）。"""

    ROWS = [("3/10 (-1.0L)", "+1", "S5→8th4→4th3→F3", "$40,000")]

    def test_average_not_best_drives_the_bonus(self):
        """best 高但 avg 慢 → 唔應該有「破標準」獎勵。"""
        eng = engine_for(self.ROWS, data_extra={
            "timing_600m_best_speed": 17.09,    # 35.11s，好快
            "timing_600m_avg_speed": 15.40,     # 38.96s，慢
        })
        item = next(i for i in eng._sectional_breakdown()["items"]
                    if "L600" in i["factor"])
        assert item["delta"] == 0.0
        assert "平均" in item["evidence"]

    def test_genuinely_fast_average_still_scores(self):
        eng = engine_for(self.ROWS, data_extra={
            "timing_600m_best_speed": 18.5,
            "timing_600m_avg_speed": 18.4,      # 32.6s，真係快
        })
        item = next(i for i in eng._sectional_breakdown()["items"]
                    if "L600" in i["factor"])
        assert item["delta"] > 0

    def test_no_longer_reads_best_speed(self):
        """只有 best、冇 avg → 唔應該再拿獎勵（口徑已經改）。"""
        eng = engine_for(self.ROWS, data_extra={"timing_600m_best_speed": 18.5})
        item = next(i for i in eng._sectional_breakdown()["items"]
                    if "L600" in i["factor"])
        assert item["delta"] == 0.0


class TestClassPrizeAdjustment:
    """F3：原本 class_mult 係全場統一常數，即係近績分完全冇班次調整。"""

    ROWS_RICH = [("3/10 (-1.0L)", "+1", "S5→F3", "$500,000"),
                 ("4/12 (-2.0L)", "+1", "S6→F4", "$400,000")]
    ROWS_POOR = [("3/10 (-1.0L)", "+1", "S5→F3", "$27,000"),
                 ("4/12 (-2.0L)", "+1", "S6→F4", "$27,000")]

    def test_stronger_class_scores_higher_than_identical_form(self):
        """名次/輸距/PI 完全一樣，只係班次唔同 → 分數必須唔同。"""
        median = horse_prize_level(facts(self.ROWS_POOR))
        summary = {"count": 10, "prize_level_field_count": 10,
                   "prize_level_field_median": median}
        rich = engine_for(self.ROWS_RICH, field_summary=summary)
        poor = engine_for(self.ROWS_POOR, field_summary=summary)
        rich._form_score()
        poor._form_score()
        assert rich.form_detail["final"] > poor.form_detail["final"]

    def test_adjustment_matches_k_times_log_gap(self):
        median = 4.6
        summary = {"count": 10, "prize_level_field_count": 10,
                   "prize_level_field_median": median}
        eng = engine_for(self.ROWS_RICH, field_summary=summary)
        eng._form_score()
        item = next(b for b in eng.form_detail["bonus"] if b["factor"] == "班次水平調整")
        own = horse_prize_level(facts(self.ROWS_RICH))
        assert item["delta"] == pytest.approx(CLASS_PRIZE_K * (own - median), abs=0.02)

    def test_applied_after_the_weak_form_regression(self):
        """次序釘死：班次調整必須喺「劣績中性回歸」之後。

        放喺回歸之前，偏弱分會連班次調整一齊被 ×n/(n+2) damp，
        咁就唔係 A/B 驗證過嘅公式。呢個測試用一匹偏弱近績（回歸會生效）嘅馬，
        驗證最終分 = 回歸後分數 + 完整班次調整。
        """
        weak = [("8/10 (-12.0L)", "-2", "S6→F8", "$500,000"),
                ("9/10 (-14.0L)", "-2", "S7→F9", "$500,000")]
        median = 4.60
        eng = engine_for(weak, field_summary={
            "count": 10, "prize_level_field_count": 10,
            "prize_level_field_median": median})
        eng._form_score()
        bonuses = {b["factor"]: b["delta"] for b in eng.form_detail["bonus"]}
        assert "劣績中性回歸" in bonuses, "呢個 case 應該觸發回歸"
        adj = bonuses["班次水平調整"]
        own = horse_prize_level(facts(weak))
        # 完整幅度（未被回歸 damp）
        assert adj == pytest.approx(CLASS_PRIZE_K * (own - median), abs=0.02)
        # 最終分 = avg + 回歸 + 班次調整（三者相加）
        expected = (eng.form_detail["avg"] + bonuses["劣績中性回歸"] + adj)
        assert eng.form_detail["final"] == pytest.approx(expected, abs=0.02)

    def test_no_field_median_means_no_adjustment(self):
        """場內少於 4 匹有數據 → orchestrator 唔提供中位數 → 唔做調整。"""
        eng = engine_for(self.ROWS_RICH, field_summary={"count": 10})
        eng._form_score()
        assert all(b["factor"] != "班次水平調整" for b in eng.form_detail["bonus"])

    def test_legacy_facts_without_prize_column_unaffected(self):
        """舊 Facts 冇獎金欄 → 完全冇班次調整，行為同修改前一致。"""
        legacy = ("### 馬匹 #1 Test\n"
                  "| # | 類型 | 日期 | 場地 | 路程 | 場地狀況 | 檔位 | 名次 | 班次 | 跑位軌跡 | PI | 段速 | 早段步速 | L600/RT | 走位跑法 | 走位消耗 | 備註 | 寬恕認定 |\n"
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
                  "| 1 | Maiden/SW | 2026-01-01 | T R1 | 1400m | 5 | 5 | 3 | - | S5→F3 | +1 | - | - | - | 守中 | 中低 | - | [需判定] |\n")
        horse = {"horse_name": "Test", "barrier": 5, "weight": 58.0,
                 "career_race_starts": 10, "career_tag": "ESTABLISHED",
                 "_data": {"facts_section": legacy, "career_record_line": "10:1-1-2"}}
        eng = RacingEngine(horse_data=horse, facts_section=legacy,
                           race_context={"race_class": "BM62", "distance": "1400m",
                                         "field_summary": {"count": 10,
                                                           "prize_level_field_median": 4.6}})
        eng._form_score()
        assert all(b["factor"] != "班次水平調整" for b in eng.form_detail["bonus"])
