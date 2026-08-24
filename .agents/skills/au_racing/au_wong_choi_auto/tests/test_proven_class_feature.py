from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))

from au_auto_orchestrator import _build_field_summary  # noqa: E402
from au_eval import configured_scorer, default_scorer  # noqa: E402
from au_racing_engine.engine_core import (  # noqa: E402
    RacingEngine,
    exact_race_class_level,
    horse_proven_class_level,
)
from au_racing_engine.scoring import PROVEN_CLASS_Z_WEIGHT  # noqa: E402


def _facts(*runs: tuple[str, str]) -> str:
    lines = [
        "| # | 類型／歷史HC | 日期 | 場地 | 路程 | 場地狀況 | 檔位 | 名次 | "
        "班次 | 跑位軌跡 | PI | 段速 | 早段步速 | L600/RT | 走位跑法 | "
        "走位消耗 | 備註 | 寬恕認定 | 獎金 | Sportsbet原始班次 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for index, (placing, race_class) in enumerate(runs, 1):
        lines.append(
            f"| {index} | 正式 | 2026-08-{10-index:02d} | Randwick R1 | 1200m | Good | "
            f"1 | {placing} | = | - | - | - | - | - | - | - | - | - | 60000 | {race_class} |"
        )
    return "\n".join(lines)


def _horse(name: str, race_class: str) -> dict:
    return {
        "horse_name": name,
        "horse_number": name,
        "barrier": 1,
        "weight": 56.0,
        "rating": 60.0,
        "_data": {"facts_section": _facts(("1/10 (0L)", race_class))},
    }


class ProvenClassFeatureTests(unittest.TestCase):
    def test_exact_class_semantics(self) -> None:
        self.assertEqual(exact_race_class_level("F&M CL3-SW"), 66.0)
        self.assertEqual(exact_race_class_level("HIGHWAY-C2"), 64.0)
        self.assertEqual(exact_race_class_level("CG&E BM64"), 64.0)
        self.assertEqual(exact_race_class_level("MDN HCP"), 56.0)
        self.assertEqual(exact_race_class_level("Group 1"), 100.0)
        self.assertIsNone(exact_race_class_level("OPEN-BT Barrier Trial"))

    def test_high_class_only_counts_when_performed(self) -> None:
        winner = horse_proven_class_level(_facts(("1/10 (0L)", "BM78")))
        last = horse_proven_class_level(_facts(("10/10 (-12L)", "BM78")))
        maiden = horse_proven_class_level(_facts(("1/10 (0L)", "MDN-SW")))
        self.assertEqual(winner, 22.0)
        self.assertEqual(last, 0.0)
        self.assertEqual(maiden, 0.0)

    def test_field_relative_overlay_is_applied_and_missing_is_neutral(self) -> None:
        horses = {
            "1": _horse("1", "BM78"),
            "2": _horse("2", "CL2"),
            "3": _horse("3", "MDN-SW"),
            "4": {
                "horse_name": "4",
                "horse_number": "4",
                "barrier": 1,
                "weight": 56.0,
                "rating": 60.0,
                "_data": {"facts_section": _facts(("1/10 (0L)", "UNKNOWN"))},
            },
        }
        summary = _build_field_summary(horses)
        self.assertEqual(summary["proven_class_field_count"], 3)
        adjustments = []
        for number, horse in horses.items():
            auto = RacingEngine(
                horse,
                {"distance": "1200m", "field_summary": summary},
                facts_section=horse["_data"]["facts_section"],
            ).analyze_horse()
            if number == "4":
                self.assertEqual(auto["proven_class_feature"], 0.0)
                self.assertEqual(auto["proven_class_detail"]["state"], "missing_neutral")
            else:
                z_score = auto["proven_class_detail"]["z_score"]
                self.assertAlmostEqual(
                    auto["proven_class_feature"],
                    PROVEN_CLASS_Z_WEIGHT * z_score,
                    places=3,
                )
                adjustments.append(auto["proven_class_feature"])
        self.assertAlmostEqual(sum(adjustments), 0.0, places=3)

    def test_fewer_than_three_comparable_horses_is_neutral(self) -> None:
        horses = {"1": _horse("1", "BM78"), "2": _horse("2", "CL2")}
        summary = _build_field_summary(horses)
        auto = RacingEngine(
            horses["1"],
            {"distance": "1200m", "field_summary": summary},
            facts_section=horses["1"]["_data"]["facts_section"],
        ).analyze_horse()
        self.assertEqual(auto["proven_class_feature"], 0.0)

    def test_canonical_evaluators_keep_the_live_overlay(self) -> None:
        base_row = {
            "features": {},
            "wet": 0.0,
            "proven_class": 0.0,
        }
        overlay_row = {**base_row, "proven_class": 1.25}
        self.assertAlmostEqual(
            default_scorer(overlay_row) - default_scorer(base_row), 1.25
        )
        self.assertAlmostEqual(
            configured_scorer()(overlay_row) - configured_scorer()(base_row), 1.25
        )


if __name__ == "__main__":
    unittest.main()
