"""顯示尺唔准改排名。

`ability_score` 由 2026-09-04 起係**顯示尺**（`scoring.to_display_scale` 嘅仿射
變換），原始加權總分留喺 `ability_score_raw`。個變換單調遞增，所以場內排序理應
bit-identical —— 但呢個「理應」試過破功：兩個數各自 `round(..., 2)` 之後，原始差
0.004 嘅兩匹馬會喺顯示尺撞成同分、跌落馬號 tiebreak（實測 274 場有 2 場中招）。
所以排序改為讀 `ability_score_raw`，而呢個檔就係守住呢件事嘅閘。

順手守住另外三樣一改就會靜靜咁改排名／改報告嘅嘢：
  * 顯示尺常數（`DISPLAY_SCALE`）—— 改咗即係改每份報告嘅數字同評級。
  * SIP-C 嘅觸發窗要用原始尺，唔可以用 grade 字串（`GRADE_THRESHOLDS` 一改就
    會觸發另一批馬）。
  * 評級階梯要真係搭得上實測分佈（舊尺 A 到 S+ 六級係空嘅）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SKILL_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi_auto"
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from hkjc_auto_orchestrator import _apply_sip_enhancements
from hkjc_racing_engine.engine_core import RacingEngine, scoring_run_contract
from hkjc_racing_engine.renderer import _raw_score
from hkjc_racing_engine.scoring import (
    DISPLAY_SCALE,
    DISPLAY_SLOPE,
    GRADE_THRESHOLDS,
    compute_grade,
    from_display_scale,
    to_display_scale,
)


def _horse(name: str, weight: str, barrier: str, form: str, days: str = "21") -> dict:
    return {
        "horse_name": name,
        "jockey": "潘頓",
        "trainer": "蔡約翰",
        "weight": weight,
        "barrier": barrier,
        "last_6_finishes": form,
        "days_since_last": days,
        "season_stats": "季內 (2-1-1-4) | 同程 (1-1-0-2) | 同場同程 (1-0-0-1)",
        "career_tag": "ESTABLISHED",
        "career_race_starts": 22,
        "best_distance": "1200m | 今仗 1200m = 4場 (1-1-2)",
        "_data": {
            "recent_6_detail": "第1仗(01/06/2026 第三班): 1名 1-1/4",
            "medical_flags": "✅ 無醫療事故記錄",
            "weight_trend": "1100 1100 1100",
        },
    }


def _field() -> dict:
    """一場馬，故意造出唔同分數，包括兩個好接近嘅分。"""
    return {
        "race_analysis": {
            "race_number": 1,
            "race_class": "第三班",
            "distance": "1200",
            "venue": "沙田",
            "race_date": "2026-06-21",
        },
        "horses": {
            "1": _horse("甲", "133", "1", "1-1-1-1-1-1"),
            "2": _horse("乙", "126", "3", "1-2-1-3-2-1"),
            "3": _horse("丙", "120", "5", "5-6-7-8-9-10"),
            "4": _horse("丁", "115", "12", "8-9-10-11-12-13"),
            "5": _horse("戊", "126", "4", "1-2-1-3-2-1"),
        },
    }


def _score(logic: dict) -> dict:
    context = logic["race_analysis"]
    for horse in logic["horses"].values():
        horse["python_auto"] = RacingEngine(horse, context).analyze_horse()
    return logic


class DisplayScaleIsMonotone(unittest.TestCase):
    def test_slope_is_positive(self):
        """slope ≤ 0 會令個尺倒轉排名。"""
        self.assertGreater(DISPLAY_SLOPE, 0)

    def test_strictly_increasing_over_the_observed_range(self):
        """實測全距 49.99–76.59，個尺喺呢個範圍內要嚴格遞增。"""
        raws = [x / 4 for x in range(4 * 45, 4 * 79)]
        displayed = [to_display_scale(r) for r in raws]
        for earlier, later in zip(displayed, displayed[1:]):
            self.assertLess(earlier, later)

    def test_clipping_above_100_cannot_reorder_a_field(self):
        """raw ≳ 80 會 clip 到 100，兩匹都 clip 就會撞成同分。

        實測最高 76.59，所以今日撞唔到；但呢個正係排序唔用顯示尺、改用
        `ability_score_raw` 嘅第二個原因（第一個係 2dp rounding）。
        """
        self.assertEqual(to_display_scale(82.0), to_display_scale(95.0))
        self.assertGreater(from_display_scale(100.0), 76.59)

    def test_roundtrip(self):
        for raw in (50.0, 57.39, 63.16, 68.85, 74.99, 76.59):
            self.assertAlmostEqual(from_display_scale(to_display_scale(raw)), raw, places=4)

    def test_median_runner_reads_as_the_anchor_grade(self):
        """實測中位（63.16 原始）應該讀到 anchor，即 B-。"""
        self.assertAlmostEqual(to_display_scale(DISPLAY_SCALE["centre"]),
                               DISPLAY_SCALE["anchor"], places=6)
        self.assertEqual(compute_grade(DISPLAY_SCALE["anchor"]), "B-")

    def test_none_passes_through(self):
        self.assertIsNone(to_display_scale(None))
        self.assertIsNone(from_display_scale(None))


class RankingIgnoresTheDisplayScale(unittest.TestCase):
    def test_raw_and_display_order_agree(self):
        logic = _score(_field())
        autos = [(num, h["python_auto"]) for num, h in logic["horses"].items()]
        by_display = [n for n, a in sorted(autos, key=lambda kv: (-kv[1]["ability_score"], int(kv[0])))]
        by_raw = [n for n, a in sorted(autos, key=lambda kv: (-kv[1]["ability_score_raw"], int(kv[0])))]
        self.assertEqual(by_display, by_raw)

    def test_raw_score_is_exposed_and_is_the_weighted_sum(self):
        logic = _score(_field())
        for horse in logic["horses"].values():
            auto = horse["python_auto"]
            self.assertIn("ability_score_raw", auto)
            # `weighted_sum` 係逐行已 round 嘅貢獻相加，所以同 ability_score_raw
            # 可以差一個 0.01 嘅 rounding；差過 0.05 就係真嘅唔對盤。
            self.assertAlmostEqual(
                auto["ability_score_raw"],
                auto["grade_transparency"]["weighted_sum"],
                delta=0.05,
            )

    def test_raw_score_helper_falls_back_for_pre_rescale_logic(self):
        """顯示尺之前嘅 Logic 冇 ability_score_raw，`ability_score` 本身就係原始尺。"""
        self.assertEqual(_raw_score({"ability_score": 71.5}), 71.5)
        self.assertEqual(_raw_score({"ability_score": 71.5, "ability_score_raw": 66.0}), 66.0)
        self.assertEqual(_raw_score({}), 0.0)


class SipStaysOnTheRawScale(unittest.TestCase):
    """SIP-C 觸發窗一改用 grade 字串，「純顯示」嘅階梯改動就會靜靜咁改排名。"""

    def _sip_horse(self, raw: float) -> dict:
        return {
            "weight": 115,
            "barrier": 3,
            "python_auto": {
                "grade": compute_grade(to_display_scale(raw)),
                "ability_score": round(to_display_scale(raw), 2),
                "ability_score_raw": raw,
                "feature_scores": {"speed_score": 72.0, "form_score": 60.0,
                                   "consistency_score": 60.0},
            },
        }

    def test_fires_inside_the_old_b_minus_window(self):
        horses = {"1": self._sip_horse(66.0), "2": self._sip_horse(66.0)}
        horses["2"]["weight"] = 133
        _apply_sip_enhancements(horses)
        self.assertTrue(horses["1"]["python_auto"].get("sip_flags"))
        self.assertAlmostEqual(horses["1"]["python_auto"]["ability_score_raw"], 67.0, places=4)

    def test_does_not_fire_outside_it(self):
        for raw in (63.9, 68.1):
            horses = {"1": self._sip_horse(raw), "2": self._sip_horse(raw)}
            horses["2"]["weight"] = 133
            _apply_sip_enhancements(horses)
            self.assertFalse(horses["1"]["python_auto"].get("sip_flags"), raw)

    def test_boost_is_applied_on_the_raw_scale(self):
        """+1.0 係原始尺，換算落顯示尺應該係 1.0 × slope。"""
        horses = {"1": self._sip_horse(66.0), "2": self._sip_horse(66.0)}
        horses["2"]["weight"] = 133
        before = horses["1"]["python_auto"]["ability_score"]
        _apply_sip_enhancements(horses)
        after = horses["1"]["python_auto"]["ability_score"]
        self.assertAlmostEqual(after - before, DISPLAY_SLOPE, places=1)


class GradeLadderMatchesTheDistribution(unittest.TestCase):
    def test_every_grade_is_reachable(self):
        """舊尺（實測 50–77）由 A(80) 到 S+(96) 六級係空嘅。新尺唔准再係咁。

        用實測 min/max 嘅原始分做界，逐級問一句「有冇原始分打得中」。
        """
        lo, hi = to_display_scale(49.99), to_display_scale(76.59)
        for minimum, grade in GRADE_THRESHOLDS:
            if grade == "S+":
                continue  # 兩季未出現過，保留做上限
            self.assertLessEqual(minimum, hi + 4, f"{grade} 到唔到")
        self.assertLess(lo, 48, "最低分應該落到 E/D 區")

    def test_display_scale_is_in_the_run_contract(self):
        self.assertEqual(scoring_run_contract().get("display_scale"), dict(DISPLAY_SCALE))


if __name__ == "__main__":
    unittest.main()
