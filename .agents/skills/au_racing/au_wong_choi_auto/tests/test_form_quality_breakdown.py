"""近績質素分逐仗拆解（用戶 2026-10-28：狀態與穩定性要睇到每仗點計、點加權）。

只係顯示：引擎已計好嘅數攤開，唔准喺 renderer 再計一次分。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ENGINE_DIR = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "au_racing_engine"
sys.path.insert(0, str(ENGINE_DIR.parent))

from au_racing_engine.engine_core import FORM_QUALITY_RECENCY_WEIGHTS, _form_quality_digest
from au_racing_engine.renderer import _stability_detail_lines


def _entries():
    # 兩場完整正式賽，最近一場排先
    return [
        {"date": "2026-09-30", "finish_pos": 3, "starters": 6, "prize": 60000.0, "distance": 1200,
         "margin": 1.14, "margin_source": "header"},
        {"date": "2026-05-30", "finish_pos": 12, "starters": 16, "prize": 1000000.0, "distance": 1400,
         "margin": 6.84, "margin_source": "header"},
    ]


class FormQualityBreakdownTests(unittest.TestCase):
    def test_digest_runs_carry_components_that_rebuild_value_and_raw(self):
        digest = _form_quality_digest(_entries(), meeting_date="2026-10-28")
        self.assertEqual(digest["run_count"], 2)
        runs = digest["runs"]
        for run, weight in zip(runs, FORM_QUALITY_RECENCY_WEIGHTS):
            self.assertAlmostEqual(run["value"], (run["z_place"] + run["z_prize"]) / 2, places=3)
            self.assertEqual(run["weight"], weight)
        rebuilt = sum(r["value"] * r["weight"] for r in runs) / sum(r["weight"] for r in runs)
        self.assertAlmostEqual(rebuilt, digest["raw"], places=4)

    def test_lines_show_each_run_weight_and_field_standardisation(self):
        auto = {"stability_detail": {"form_quality": {
            "raw": 1.018, "run_count": 2, "field_count": 10, "field_mean": 0.501, "field_stdev": 0.319,
            "z": 1.62, "final": 92.45,
            "runs": [
                {"date": "2026-09-30", "finish_pos": 3, "starters": 6, "prize": 60000.0, "distance": 1200,
                 "value": 0.43, "z_place": 0.31, "z_prize": 0.54, "weight": 1.0},
                {"date": "2026-05-30", "finish_pos": 12, "starters": 16, "prize": 1000000.0, "distance": 1400,
                 "value": 1.63, "z_place": -0.73, "z_prize": 3.99, "weight": 0.8},
            ]}}}
        text = "\n".join(_stability_detail_lines(auto, "form_quality_score"))
        self.assertIn("第1仗（最近） 2026-09-30 1200m：第3名／6匹，$60,000", text)
        self.assertIn("名次 z -0.73、獎金級別 z +3.99 → 本仗值 +1.63 × 近期權重 0.8", text)
        self.assertIn("同場 10 匹有值", text)
        self.assertIn("60 ＋ 20z ＝ 92.5", text)

    def test_trip_change_shows_final_after_penalty(self):
        auto = {"stability_detail": {"form_quality": {
            "raw": 0.5, "run_count": 2, "field_count": 8, "field_mean": 0.4, "field_stdev": 0.3,
            "z": 0.33, "final": 66.6, "runs": [],
            "trip_change": {"today": 2000.0, "last": 1200.0, "delta": -5.0}}}}
        lines = _stability_detail_lines(auto, "form_quality_score")
        self.assertTrue(any("大幅轉程" in ln and "-5" in ln for ln in lines))
        self.assertEqual(lines[-1], "最終近績質素分 ＝ 61.6")

    def test_fallback_and_old_logic_without_detail(self):
        fallback = {"stability_detail": {"form_quality": {"fallback": "form_and_quality_composite", "final": 63.2}}}
        self.assertEqual(len(_stability_detail_lines(fallback, "form_quality_score")), 1)
        self.assertEqual(_stability_detail_lines({"stability_detail": {}}, "form_quality_score"), [])


if __name__ == "__main__":
    unittest.main()
