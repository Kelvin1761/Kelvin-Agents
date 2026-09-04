"""七個維度要企喺同一把尺上面，而且唔准影響排名。

原始尺上面七個維度嘅全距由 18.5 分（`馬匹健康` 55.2–73.7）到 58.8 分
（`狀態與穩定性` 37.2–96.0），SD 由 3.47 到 12.26 —— 相差 3.5 倍。但報告一路
將佢哋並排印成 0–100，再套同一套 band 門檻（✅✅ 85 / ✅ 70 / ➖ 55 / ❌ 40）。
後果（3,438 匹實測）：

  * **七個維度有五個永遠出唔到 ✅✅**
  * `馬匹健康` 整個詞彙只有 {✅, ➖} —— 連真係有醫療問題嘅馬都印唔出 ❌
  * `賽績線` 反過來永遠出唔到 ❌
  * 「60 = 中性／冇證據」喺 leaf 層本身唔成立（`馬匹健康` 中位 66.9、
    `賽績線` 中位 80.0），所以只拉伸唔夠，要連中心一齊校返

觸發個案 2026-09-06 R3 嘉應高昇：`檔位與走位` 69.4 分係全體**第 75 百分位**，
但印住「➖ 中性」，差 0.6 分就 ✅。

`matrix_scores` 保持原始值（餵綜合分同所有權重／消融工具），顯示值另存
`matrix_scores_display`。呢個檔守住三件事：單調、排名唔變、band 真係到得。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi_auto" / "scripts"))

from hkjc_racing_engine.engine_core import RacingEngine, scoring_run_contract
from hkjc_racing_engine.scoring import (
    MATRIX_DISPLAY_CENTRES,
    MATRIX_DISPLAY_GAINS,
    MATRIX_DISPLAY_TARGET_SD,
    MATRIX_WEIGHTS,
    dimension_display_manifest,
    score_band,
    to_dimension_display,
)

# 每個維度嘅原始全距（3,438 匹實測，2026-09-04）
OBSERVED = {
    "race_shape": (39.1, 82.0),
    "trainer_signal": (51.0, 79.0),
    "class_advantage": (52.8, 76.6),
    "sectional": (33.6, 85.5),
    "stability": (37.2, 96.0),
    "form_line": (58.0, 96.0),
    "horse_health": (55.2, 73.7),
}


def _horse(name, weight, barrier, form):
    return {
        "horse_name": name, "jockey": "潘頓", "trainer": "蔡約翰",
        "weight": weight, "barrier": barrier, "last_6_finishes": form,
        "days_since_last": "21",
        "season_stats": "季內 (2-1-1-4) | 同程 (1-1-0-2) | 同場同程 (1-0-0-1)",
        "career_tag": "ESTABLISHED", "career_race_starts": 22,
        "best_distance": "1200m | 今仗 1200m = 4場 (1-1-2)",
        "_data": {"recent_6_detail": "第1仗(01/06/2026 第三班): 1名 1-1/4",
                  "medical_flags": "✅ 無醫療事故記錄",
                  "weight_trend": "1100 1100 1100"},
    }


def _scored_field():
    logic = {
        "race_analysis": {"race_number": 1, "race_class": "第三班", "distance": "1200",
                          "venue": "沙田", "race_date": "2026-06-21"},
        "horses": {
            "1": _horse("甲", "133", "1", "1-1-1-1-1-1"),
            "2": _horse("乙", "126", "3", "1-2-1-3-2-1"),
            "3": _horse("丙", "120", "5", "5-6-7-8-9-10"),
            "4": _horse("丁", "115", "12", "8-9-10-11-12-13"),
            "5": _horse("戊", "126", "4", "1-2-1-3-2-1"),
        },
    }
    for h in logic["horses"].values():
        h["python_auto"] = RacingEngine(h, logic["race_analysis"]).analyze_horse()
    return logic


class RulerIsMonotone(unittest.TestCase):
    def test_every_scoring_dimension_has_a_centre_and_a_gain(self):
        for dim in MATRIX_WEIGHTS:
            self.assertIn(dim, MATRIX_DISPLAY_CENTRES, dim)
            self.assertIn(dim, MATRIX_DISPLAY_GAINS, dim)

    def test_gains_are_positive(self):
        """gain ≤ 0 會令維度分倒轉，band 就會講反話。"""
        for dim, gain in MATRIX_DISPLAY_GAINS.items():
            self.assertGreater(gain, 0, dim)

    def test_strictly_increasing_inside_each_observed_range(self):
        for dim, (lo, hi) in OBSERVED.items():
            xs = [lo + (hi - lo) * i / 60 for i in range(61)]
            ys = [to_dimension_display(dim, x) for x in xs]
            for a, b in zip(ys, ys[1:]):
                self.assertLess(a, b, dim)

    def test_the_centre_reads_as_sixty(self):
        for dim, centre in MATRIX_DISPLAY_CENTRES.items():
            self.assertAlmostEqual(to_dimension_display(dim, centre), 60.0, places=6, msg=dim)

    def test_an_unknown_dimension_passes_through(self):
        self.assertEqual(to_dimension_display("not_a_dimension", 71.5), 71.5)

    def test_none_passes_through(self):
        self.assertIsNone(to_dimension_display("race_shape", None))


class BandsBecomeReachable(unittest.TestCase):
    def test_neutral_and_both_edges_are_reachable_everywhere(self):
        """原始尺上面 `馬匹健康` 只出得 {✅,➖}、`賽績線` 出唔到 ❌。新尺唔准再係咁。"""
        for dim, (lo, hi) in OBSERVED.items():
            bands = {score_band(to_dimension_display(dim, lo)),
                     score_band(to_dimension_display(dim, MATRIX_DISPLAY_CENTRES[dim])),
                     score_band(to_dimension_display(dim, hi))}
            self.assertIn("➖", bands, dim)
            self.assertTrue({"❌", "❌❌"} & bands, f"{dim} 出唔到 ❌")
            self.assertTrue({"✅", "✅✅"} & bands, f"{dim} 出唔到 ✅")

    def test_the_raw_ruler_really_was_broken(self):
        """記錄住個原因：舊尺 `馬匹健康` 由 55.2 到 73.7 全部落喺 {✅,➖}。"""
        lo, hi = OBSERVED["horse_health"]
        self.assertEqual({score_band(lo), score_band(hi)}, {"➖", "✅"})
        self.assertEqual(score_band(OBSERVED["form_line"][0]), "➖")   # 58.0 → 從來到唔到 ❌

    def test_target_sd_is_the_documented_one(self):
        self.assertEqual(MATRIX_DISPLAY_TARGET_SD, 10.0)


class RankingIsUntouched(unittest.TestCase):
    def test_raw_matrix_scores_are_preserved_for_the_composite(self):
        logic = _scored_field()
        for h in logic["horses"].values():
            auto = h["python_auto"]
            self.assertIn("matrix_scores", auto)
            self.assertIn("matrix_scores_display", auto)
            # 綜合分一定要由原始尺加出嚟
            expected = sum(auto["matrix_scores"][k] * w for k, w in MATRIX_WEIGHTS.items())
            self.assertAlmostEqual(auto["ability_score_raw"], expected, delta=0.02)

    def test_display_scores_are_the_transform_of_the_raw_ones(self):
        logic = _scored_field()
        for h in logic["horses"].values():
            auto = h["python_auto"]
            for dim, raw in auto["matrix_scores"].items():
                self.assertAlmostEqual(auto["matrix_scores_display"][dim],
                                       to_dimension_display(dim, raw), delta=0.02, msg=dim)

    def test_bands_come_from_the_display_scale(self):
        logic = _scored_field()
        for h in logic["horses"].values():
            auto = h["python_auto"]
            for dim, symbol in auto["matrix"].items():
                self.assertEqual(symbol, score_band(auto["matrix_scores_display"][dim]), dim)

    def test_reasoning_carries_both_rulers(self):
        """「評分構成」加出嚟嘅係原始尺；header 印嘅係顯示尺。兩個都要寫。"""
        logic = _scored_field()
        for h in logic["horses"].values():
            reasoning = h["python_auto"]["matrix_reasoning"]
            for dim, row in reasoning.items():
                self.assertIn("score_raw", row, dim)
                self.assertAlmostEqual(row["score_raw"], h["python_auto"]["matrix_scores"][dim],
                                       delta=0.02, msg=dim)
                self.assertAlmostEqual(row["score"], h["python_auto"]["matrix_scores_display"][dim],
                                       delta=0.02, msg=dim)

    def test_dimension_ruler_is_in_the_run_contract(self):
        self.assertEqual(scoring_run_contract().get("dimension_display_scale"),
                         dimension_display_manifest())


if __name__ == "__main__":
    unittest.main()
