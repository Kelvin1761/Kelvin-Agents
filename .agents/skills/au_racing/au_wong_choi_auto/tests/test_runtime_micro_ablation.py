import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ENGINE = SCRIPTS / "racing_engine"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ENGINE))

from au_runtime_micro_ablation import (
    MICRO_FAMILIES,
    discover_logic_files,
    neutral_value,
    patched_weights,
    score_diagnostics,
    variant_patches,
)


class RuntimeMicroAblationTests(unittest.TestCase):
    def test_neutral_value_distinguishes_base_from_adjustments(self):
        self.assertEqual(neutral_value("base"), 60.0)
        self.assertEqual(neutral_value("weak_base"), 60.0)
        self.assertEqual(neutral_value("elite_bonus"), 0.0)
        self.assertEqual(neutral_value("wide_barrier_pen"), 0.0)

    def test_patched_weights_restore_values_after_success(self):
        weights = {"base": 55.0, "bonus": 4.0}
        with patched_weights(
            [(weights, "base", 60.0), (weights, "bonus", 0.0)]
        ):
            self.assertEqual(weights, {"base": 60.0, "bonus": 0.0})
        self.assertEqual(weights, {"base": 55.0, "bonus": 4.0})

    def test_patched_weights_restore_values_after_exception(self):
        weights = {"bonus": 4.0}
        with self.assertRaisesRegex(RuntimeError, "stop"):
            with patched_weights([(weights, "bonus", 0.0)]):
                raise RuntimeError("stop")
        self.assertEqual(weights, {"bonus": 4.0})

    def test_family_filter_keeps_baseline_and_selected_micro_only(self):
        variants = variant_patches("individual", {"pace"})
        names = [name for name, _patches in variants]
        self.assertEqual(names[0], "revised_current")
        self.assertEqual(len(names), 1 + len(MICRO_FAMILIES["pace"]))
        self.assertTrue(
            all(
                name == "revised_current" or name.startswith("drop_micro:pace.")
                for name in names
            )
        )

    def test_micro_key_filter_builds_individual_and_combined_variants(self):
        variants = variant_patches(
            "all",
            {"pace"},
            {"pace.modifier_multiplier", "pace.modifier_cap_max"},
        )
        patches = {name: values for name, values in variants}
        self.assertEqual(len(patches["drop_group:pace"]), 2)
        self.assertEqual(len(patches["drop_group:all_micro"]), 2)
        self.assertIn("drop_micro:pace.modifier_multiplier", patches)
        self.assertIn("drop_micro:pace.modifier_cap_max", patches)

    def test_score_diagnostics_distinguish_score_and_rank_changes(self):
        baseline = [[
            {"horse_number": 1, "horse_name": "A", "score": 70.0},
            {"horse_number": 2, "horse_name": "B", "score": 60.0},
        ]]
        score_only = [[
            {"horse_number": 1, "horse_name": "A", "score": 69.0},
            {"horse_number": 2, "horse_name": "B", "score": 59.0},
        ]]
        swapped = [[
            {"horse_number": 1, "horse_name": "A", "score": 59.0},
            {"horse_number": 2, "horse_name": "B", "score": 69.0},
        ]]
        self.assertEqual(
            score_diagnostics(score_only, baseline)["ranking_changed_races"],
            0,
        )
        self.assertEqual(
            score_diagnostics(swapped, baseline)["ranking_changed_races"],
            1,
        )

    def test_discovery_separates_materialized_files_from_placeholders(self):
        # This validates the preflight contract without relying on Google Drive:
        # a sparse file has logical size but no physical blocks, just like a
        # cloud placeholder.
        import tempfile

        with tempfile.TemporaryDirectory() as root:
            meeting = Path(root) / "2026-01-01 Test Race 1"
            meeting.mkdir()
            materialized = meeting / "Race_1_Logic.json"
            placeholder = meeting / "Race_2_Logic.json"
            materialized.write_text('{"x": 1}', encoding="utf-8")
            with placeholder.open("wb") as handle:
                handle.truncate(1_000_000)
            ready, sparse = discover_logic_files(Path(root))
        self.assertEqual(ready, [materialized])
        self.assertEqual(sparse, [placeholder])


if __name__ == "__main__":
    unittest.main()
