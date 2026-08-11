from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from hkjc_stability_residual_shadow import (  # noqa: E402
    DEFAULT_MODEL,
    EXPECTED_CAP,
    MODEL_VERSION,
    EXPECTED_FEATURES,
    apply_shadow_model,
    build_feature_frame,
    load_frozen_model,
    run_shadow,
)


class HkjcStabilityResidualShadowTests(unittest.TestCase):
    @staticmethod
    def _logic() -> dict:
        horses = {}
        for number in range(1, 5):
            horses[str(number)] = {
                "horse_name": f"測試馬{number}",
                "days_since_last": 14 + number * 7,
                "last_6_finishes": [number, number + 1, 3, 5, 7, 9],
                "trackwork": {
                    "entries": [
                        {"type": "gallop"},
                        {"type": "trial" if number % 2 else "gallop"},
                    ],
                    "flags": ["steady"] if number == 4 else [],
                },
                "python_auto": {
                    "ability_score": 75 - number,
                    "rank": number,
                    "matrix_scores": {"stability": 80 - number * 5},
                    "feature_scores": {
                        "form_score": 82 - number * 4,
                        "consistency_score": 78 - number * 3,
                    },
                    "derived_feature_scores": {
                        "trackwork_trend_score": 72 - number,
                    },
                },
            }
        return {
            "race_analysis": {"race_number": 3},
            "horses": horses,
        }

    def test_feature_frame_matches_frozen_contract(self) -> None:
        frame = build_feature_frame(self._logic())
        self.assertEqual(len(frame), 4)
        self.assertAlmostEqual(float(frame["rel_matrix_stability"].mean()), 0.0)
        self.assertEqual(frame.loc[0, "last6_runs"], 6)
        self.assertEqual(frame.loc[1, "tw_gallop_count"], 2.0)

    def test_shadow_probabilities_are_coherent_and_delta_is_bounded(self) -> None:
        payload = load_frozen_model(DEFAULT_MODEL)
        output = apply_shadow_model(build_feature_frame(self._logic()), payload)
        self.assertAlmostEqual(float(output["mainline_win_probability"].sum()), 1.0)
        self.assertAlmostEqual(float(output["shadow_win_probability"].sum()), 1.0)
        self.assertLessEqual(
            float(np.abs(output["bounded_logit_delta"]).max()), EXPECTED_CAP
        )
        self.assertEqual(set(output["mainline_rank"]), {1, 2, 3, 4})
        self.assertEqual(set(output["shadow_rank"]), {1, 2, 3, 4})

    def test_shadow_fails_closed_when_stored_mainline_rank_has_drifted(self) -> None:
        payload = load_frozen_model(DEFAULT_MODEL)
        logic = self._logic()
        logic["horses"]["1"]["python_auto"]["rank"] = 4
        with self.assertRaisesRegex(ValueError, "Stored mainline rank"):
            apply_shadow_model(build_feature_frame(logic), payload)

    def test_runner_writes_separate_artifacts_without_mutating_logic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logic_path = root / "Race_3_Logic.json"
            original = json.dumps(self._logic(), ensure_ascii=False, indent=2)
            logic_path.write_text(original, encoding="utf-8")
            results_path = root / "results.json"
            results_path.write_text(
                json.dumps(
                    {
                        "3": {
                            "results": [
                                {"pos": 1, "horse_no": 1},
                                {"pos": 2, "horse_no": 3},
                                {"pos": 3, "horse_no": 4},
                                {"pos": 4, "horse_no": 2},
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            csv_path, json_path, report = run_shadow(
                logic_path, results_path=results_path
            )

            self.assertEqual(logic_path.read_text(encoding="utf-8"), original)
            self.assertTrue(csv_path.is_file())
            self.assertTrue(json_path.is_file())
            self.assertEqual(report["model_version"], MODEL_VERSION)
            self.assertFalse(report["contract"]["mainline_modified"])
            self.assertEqual(report["evaluation"]["evaluated_races"], 1)

    def test_missing_python_auto_fails_closed(self) -> None:
        logic = self._logic()
        del logic["horses"]["1"]["python_auto"]
        with self.assertRaisesRegex(ValueError, "run HKJC Auto"):
            build_feature_frame(logic)

    def test_frozen_runner_reproduces_external_research_probabilities(self) -> None:
        artifact_root = (
            ROOT
            / ".agents"
            / "skills"
            / "hkjc_racing"
            / "hkjc_reflector"
            / "artifacts"
        )
        clean = pd.read_csv(
            artifact_root / "hkjc_ml_program" / "training_dataset_clean.csv",
            low_memory=False,
        )
        external = clean[clean["source_split"] == "external_holdout"].copy()
        expected = pd.read_csv(
            artifact_root
            / "hkjc_dimension_ml_program"
            / "dimension_predictions.csv",
            low_memory=False,
        )
        expected = expected[
            (expected["period"] == "external_holdout")
            & (expected["dimension"] == "stability")
            & (expected["target"] == "Win")
            & (expected["method"] == "Residual cap=0.05")
        ][["race_key", "horse_number", "probability"]]
        payload = load_frozen_model(DEFAULT_MODEL)
        outputs = []
        for race_key, group in external.groupby("race_key", sort=False):
            frame = group[EXPECTED_FEATURES].copy()
            frame["horse_number"] = group["horse_number"].astype(str)
            frame["horse_name"] = group["horse_name"].astype(str)
            frame["mainline_ability"] = group[
                "current_live_recomputed_ability"
            ].to_numpy()
            order = group.sort_values(
                ["current_live_recomputed_ability", "horse_number"],
                ascending=[False, True],
            ).index
            ranks = pd.Series(range(1, len(group) + 1), index=order)
            frame["stored_mainline_rank"] = ranks.loc[group.index].to_numpy()
            scored = apply_shadow_model(frame, payload)
            scored["race_key"] = race_key
            outputs.append(scored[["race_key", "horse_number", "shadow_win_probability"]])
        actual = pd.concat(outputs, ignore_index=True)
        actual["horse_number"] = actual["horse_number"].astype(int)
        comparison = expected.merge(
            actual, on=["race_key", "horse_number"], validate="one_to_one"
        )
        self.assertEqual(len(comparison), len(expected))
        np.testing.assert_allclose(
            comparison["shadow_win_probability"],
            comparison["probability"],
            rtol=0,
            atol=1e-12,
        )


if __name__ == "__main__":
    unittest.main()
