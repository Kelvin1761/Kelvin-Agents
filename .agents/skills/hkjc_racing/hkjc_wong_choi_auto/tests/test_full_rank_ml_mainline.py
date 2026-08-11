from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[5]
SKILL_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi_auto"
ENGINE_DIR = SKILL_DIR / "scripts" / "racing_engine"
sys.path.insert(0, str(SKILL_DIR / "scripts"))
sys.path.insert(0, str(ENGINE_DIR))

from full_rank_ml import (  # noqa: E402
    MATRIX_WEIGHT,
    ML_WEIGHT,
    MODEL_PATH,
    MODEL_SHA256,
    RANKING_CONTRACT_VERSION,
    apply_full_rank_ml,
    build_model_frame,
)
from renderer import (  # noqa: E402
    ensure_verdict,
    render_race_csv,
    render_race_markdown,
    validate_report_text,
)
from validation import _validate_verdict  # noqa: E402
import hkjc_auto_orchestrator as auto_orchestrator  # noqa: E402
import full_rank_ml  # noqa: E402


EXTERNAL_LEDGER = (
    ROOT
    / ".agents"
    / "skills"
    / "hkjc_racing"
    / "hkjc_reflector"
    / "artifacts"
    / "hkjc_full_rank_ml_program"
    / "external_predictions.csv"
)


def _logic_from_rows(rows: pd.DataFrame) -> dict:
    horses = {}
    for row in rows.itertuples(index=False):
        matrix_scores = {
            "stability": float(row.matrix_stability),
            "sectional": float(row.matrix_sectional),
            "race_shape": float(row.matrix_race_shape),
            "trainer_signal": float(row.matrix_trainer_signal),
            "horse_health": float(row.matrix_horse_health),
            "form_line": float(row.matrix_form_line),
            "class_advantage": float(row.matrix_class_advantage),
        }
        horses[str(row.horse_number)] = {
            "horse_name": row.horse_name,
            "python_auto": {
                "matrix_scores": matrix_scores,
                "ability_score": float(row.current_live_recomputed_ability),
                "grade": "B",
                "feature_scores": {},
            },
        }
    return {"race_analysis": {"race_number": int(rows.race_number.iloc[0])}, "horses": horses}


class FullRankMlMainlineTests(unittest.TestCase):
    def test_model_artifact_checksum_is_pinned(self) -> None:
        self.assertTrue(MODEL_PATH.is_file())
        self.assertEqual(hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(), MODEL_SHA256)

    def test_corrupt_portable_artifact_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            corrupt = Path(tmp) / "ranker.json"
            corrupt.write_text("{}", encoding="utf-8")
            full_rank_ml.load_model_bundle.cache_clear()
            try:
                with mock.patch.object(full_rank_ml, "MODEL_PATH", corrupt):
                    with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                        full_rank_ml.load_model_bundle()
            finally:
                full_rank_ml.load_model_bundle.cache_clear()

    def test_model_frame_builds_fold_compatible_relative_features(self) -> None:
        logic = {
            "horses": {
                str(index): {
                    "python_auto": {
                        "matrix_scores": {
                            "sectional": 60 + index,
                            "trainer_signal": 61 + index,
                            "stability": 62 + index,
                            "race_shape": 63 + index,
                            "class_advantage": 64 + index,
                            "horse_health": 65 + index,
                            "form_line": 66 + index,
                        }
                    }
                }
                for index in range(1, 4)
            }
        }
        _, rows, _ = build_model_frame(logic["horses"])
        relative = np.asarray(
            [
                [value for key, value in row.items() if key.startswith("rel_matrix_")]
                for row in rows
            ],
            dtype=float,
        )
        np.testing.assert_allclose(relative.mean(axis=0), np.zeros(7), atol=1e-12)
        np.testing.assert_allclose(relative.std(axis=0, ddof=1), np.ones(7), atol=1e-12)

    def test_external_ledger_replays_exact_hybrid_scores_and_ranks(self) -> None:
        ledger = pd.read_csv(EXTERNAL_LEDGER, encoding="utf-8-sig")
        replayed_races = 0
        for _, rows in ledger.groupby("race_key", sort=False):
            logic = _logic_from_rows(rows)
            contract = apply_full_rank_ml(logic)
            verdict = ensure_verdict(logic)
            expected = rows.sort_values("probability", ascending=False)["horse_number"].astype(str).tolist()
            actual = [str(item["horse_number"]) for item in verdict["ranking"]]
            self.assertEqual(actual, expected)
            expected_scores = rows.set_index(rows["horse_number"].astype(str))["hybrid_rank_score"]
            for horse_number, horse in logic["horses"].items():
                self.assertAlmostEqual(
                    horse["python_auto"]["rank_score"],
                    float(expected_scores.loc[horse_number]),
                    places=10,
                )
            self.assertEqual(contract["version"], RANKING_CONTRACT_VERSION)
            self.assertEqual(contract["matrix_weight"], MATRIX_WEIGHT)
            self.assertEqual(contract["ml_weight"], ML_WEIGHT)
            replayed_races += 1
        self.assertEqual(replayed_races, 9)

    def test_hybrid_verdict_contract_validates(self) -> None:
        ledger = pd.read_csv(EXTERNAL_LEDGER, encoding="utf-8-sig")
        logic = _logic_from_rows(next(iter(ledger.groupby("race_key")))[1])
        apply_full_rank_ml(logic)
        ensure_verdict(logic)
        scored = [
            (horse_number, horse["python_auto"])
            for horse_number, horse in logic["horses"].items()
        ]
        self.assertEqual(_validate_verdict(logic, scored), [])

    def test_hybrid_contract_is_explainable_in_markdown_and_csv(self) -> None:
        ledger = pd.read_csv(EXTERNAL_LEDGER, encoding="utf-8-sig")
        logic = _logic_from_rows(next(iter(ledger.groupby("race_key")))[1])
        apply_full_rank_ml(logic)
        markdown = render_race_markdown(logic)
        scoring_csv = render_race_csv(logic)
        self.assertIn("70% 七維矩陣全場次序 + 30% ML 全場競爭力次序", markdown)
        self.assertIn("唔做逐場人手換馬", markdown)
        self.assertEqual(validate_report_text(markdown), [])
        self.assertIn("ranking_contract_id", scoring_csv.splitlines()[0])
        self.assertIn("ml_rank_percentile", scoring_csv.splitlines()[0])

    def test_default_auto_run_writes_hybrid_outputs(self) -> None:
        logic = {
            "race_analysis": {
                "race_number": 1,
                "race_class": "第四班",
                "distance": "1200",
                "venue": "沙田",
            },
            "horses": {},
        }
        for index, finishes in enumerate(
            ("1-2-3-4-5-6", "2-3-4-5-6-7", "4-5-6-7-8-9"), start=1
        ):
            logic["horses"][str(index)] = {
                "horse_name": f"測試{index}",
                "jockey": "普通騎師",
                "trainer": "普通練馬師",
                "weight": str(120 + index),
                "barrier": str(index),
                "last_6_finishes": finishes,
                "season_stats": "季內 (1-1-1-3)",
                "trackwork": {},
                "_data": {
                    "trackwork_digest": "晨操正常。",
                    "medical_flags": "✅ 無醫療事故記錄",
                },
            }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Race_1_Logic.json"
            path.write_text(json.dumps(logic, ensure_ascii=False), encoding="utf-8")
            runner = auto_orchestrator.HKJCAutoOrchestrator(path)
            with mock.patch.object(auto_orchestrator, "_enrich_profile_history"):
                result = runner.score_race(path)
            self.assertIsNotNone(result)
            self.assertEqual(
                result["python_auto_ranking_contract"]["version"],
                RANKING_CONTRACT_VERSION,
            )
            self.assertTrue((Path(tmp) / "Race_1_Auto_Analysis.md").is_file())
            self.assertTrue((Path(tmp) / "Race_1_Auto_Scoring.csv").is_file())


if __name__ == "__main__":
    unittest.main()
