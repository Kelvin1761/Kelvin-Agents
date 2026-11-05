"""EXP-20261105-09 D1 forward：反事實「初出穩定性分仍係 52.4」一定要同引擎 WC_AU_DEBUT_NEUTRAL=0 一樣。

2026-11-05 用 2026-11-06 Cranbourne（8 場、85 匹、6 匹初出路徑）實測：D1 評分後重砌 vs 引擎 =0 評分，差 0.0000；
其他馬冇郁。呢度鎖住條式同揀馬條件。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"))

from au_debut_neutral_forward import affected, legacy_form_quality, race_rows, scored_with_d1  # noqa: E402
from au_racing_engine.scoring import CONSISTENCY_MICRO_WEIGHTS, DEBUT_NO_EVIDENCE_LEGACY  # noqa: E402

PROV = {"consistency_score": "career_tag", "performance_quality_score": "consistency_fallback",
        "form_quality_score": "form_quality_fallback_composite"}


def auto(form=60.0, pq=60.0, fq=60.0, prov=PROV, trip=False, consistency=60.0):
    detail = {"trip_change": {"delta": -5.0}} if trip else {}
    return {"score_provenance": dict(prov),
            "feature_scores": {"form_score": form, "performance_quality_score": pq, "form_quality_score": fq,
                               "consistency_score": consistency},
            "stability_detail": {"form_quality": detail}}


class DebutNeutralTests(unittest.TestCase):
    def test_live_value_is_60(self) -> None:
        self.assertEqual(CONSISTENCY_MICRO_WEIGHTS["career0_base"], 60.0)
        self.assertEqual(DEBUT_NO_EVIDENCE_LEGACY, 52.4)

    def test_legacy_rebuild(self) -> None:
        self.assertAlmostEqual(legacy_form_quality(auto())[0], 0.6 * 60 + 0.4 * 52.4)
        self.assertAlmostEqual(legacy_form_quality(auto(form=70.0, fq=0.6 * 70 + 0.4 * 60))[0], 0.6 * 70 + 0.4 * 52.4)

    def test_trip_penalty_kept(self) -> None:
        self.assertAlmostEqual(legacy_form_quality(auto(fq=55.0, trip=True))[0], 0.6 * 60 + 0.4 * 52.4 - 5.0)

    def test_mismatch_flagged(self) -> None:
        self.assertEqual(legacy_form_quality(auto(fq=70.0))[1], "live_rebuild_mismatch")

    def test_only_debut_path_affected(self) -> None:
        self.assertTrue(affected(auto()))
        self.assertFalse(affected(auto(prov={**PROV, "form_quality_score": "form_quality_field_relative"})))
        self.assertFalse(affected(auto(prov={**PROV, "consistency_score": "computed"})))


    def test_pre_d1_record_is_skipped_not_counted_as_unchanged(self) -> None:
        old = auto(pq=52.4, fq=0.6 * 60 + 0.4 * 52.4, consistency=52.4)
        self.assertFalse(scored_with_d1(old))
        self.assertTrue(scored_with_d1(auto()))
        self.assertEqual(race_rows({"horses": {"1": {"python_auto": old}}}, [])[3], "pre_d1_record")


if __name__ == "__main__":
    unittest.main()
