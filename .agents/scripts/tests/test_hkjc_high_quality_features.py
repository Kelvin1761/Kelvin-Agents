from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = ROOT / ".agents" / "scripts"
SKELETON_PATH = (
    ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi"
    / "scripts" / "create_hkjc_logic_skeleton.py"
)
sys.path.insert(0, str(SCRIPTS_DIR))

from inject_hkjc_fact_anchors import (
    extract_race_context,
    filter_profile_as_of,
    get_reference_sections,
)

spec = importlib.util.spec_from_file_location("hkjc_logic_skeleton_for_test", SKELETON_PATH)
skeleton = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(skeleton)


class HighQualityFeatureTests(unittest.TestCase):
    def test_profile_filter_is_strictly_pre_race(self) -> None:
        profile = {
            "trainer": "現時練馬師",
            "entries": [
                {"date": "20/07/26", "trainer": "未來練馬師"},
                {"race_date_full": "2026/07/15", "trainer": "同日練馬師"},
                {"date": "01/07/26", "trainer": "賽前練馬師"},
            ],
        }
        filtered = filter_profile_as_of(profile, "2026-07-15")
        self.assertEqual(len(filtered["entries"]), 1)
        self.assertEqual(filtered["trainer"], "賽前練馬師")
        self.assertEqual(len(profile["entries"]), 3)

    def test_normalized_sectionals_are_recency_weighted_and_retain_samples(self) -> None:
        block = """
📊 **全段速剖面 (Full Sectional Profile — 近 2 仗):**
| # | 日期 | 距離 | S1 | S2 | S3 | Δ1 | Δ2 | Δ3 | 形態 |
|---|------|------|---|---|---|---|---|---|------|
| 1 | 01/07/26 | 1200 | 23.50 | 22.10 | 22.60 | -0.20 | -0.35 | -0.55 | 漸進加速 |
| 2 | 01/06/26 | 1200 | 23.80 | 22.50 | 23.30 | +0.05 | +0.05 | +0.15 | 均速 |

其他資料
"""
        parsed = skeleton.parse_normalized_sectionals(block)
        self.assertEqual(parsed["sectional_normalized_samples"], 2)
        self.assertEqual(parsed["sectional_normalized_series"][0]["l400_delta"], -0.55)
        self.assertLess(parsed["sectional_normalized_l400_delta"], -0.2)
        self.assertLess(parsed["sectional_normalized_total_delta"], -0.3)

    def test_reference_sectional_never_falls_back_to_wrong_class(self) -> None:
        self.assertTrue(get_reference_sections("跑馬地", 1200, "Class 4"))
        self.assertEqual(get_reference_sections("跑馬地", 1200, "不明班次"), {})

    def test_rating_trend_retains_numeric_history_for_scoring(self) -> None:
        parsed = skeleton.parse_trends(
            "📈 **評分變動:** 43→46→48 → 降班中\n"
        )
        self.assertEqual(parsed["rating_series"], [43.0, 46.0, 48.0])

    def test_race_context_retains_surface_and_course(self) -> None:
        text = (
            "- 賽事日期 / 場次 / 跑道及場地狀況: "
            "2026-07-15 / 第3場 / 沙田 全天候跑道 AWT 1650米 第三班\n"
        )
        context = extract_race_context(text)
        self.assertEqual(context["venue"], "沙田AWT")
        self.assertEqual(context["surface"], "AWT")
        self.assertEqual(context["distance"], 1650)

        turf = extract_race_context(
            "- 賽事日期 / 場次 / 跑道及場地狀況: "
            "2026-07-15 / 第5場 / 跑馬地 草地 C+3 賽道 1200米 第四班\n"
        )
        self.assertEqual(turf["surface"], "Turf")
        self.assertEqual(turf["course"], "C+3")

    def test_logic_header_propagates_surface_and_course(self) -> None:
        header = skeleton.extract_race_header(
            "場地: 跑馬地 | 跑道: Turf | 賽道: C+3 | "
            "距離: 1200m | 班次: C4\n"
        )
        self.assertEqual(header["track"], "Turf")
        self.assertEqual(header["course"], "C+3")


if __name__ == "__main__":
    unittest.main()
