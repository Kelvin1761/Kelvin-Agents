from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ENGINE_DIR = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "au_racing_engine"
sys.path.insert(0, str(ENGINE_DIR.parent))

from au_racing_engine.renderer import _confidence_tier_text, ensure_verdict


def _logic(scores: list[float]) -> dict:
    horses = {}
    for idx, score in enumerate(scores, start=1):
        horses[str(idx)] = {
            "horse_name": f"Horse {idx}",
            "python_auto": {"ability_score": score, "grade": "C"},
        }
    return {"race_analysis": {"race_number": 1}, "horses": horses}


class ConfidenceRadarTests(unittest.TestCase):
    def test_tight_race_widens_radar_to_five(self) -> None:
        logic = _logic([64.0, 63.5, 62.5, 62.0, 61.5, 60.0])  # top1-top3 gap 1.5
        verdict = ensure_verdict(logic)
        self.assertEqual(verdict["confidence_tier"], "tight")
        self.assertEqual(verdict["radar_size"], 5)
        self.assertEqual(len(verdict["radar"]), 5)
        statuses = [logic["horses"][str(i)]["python_auto"]["model_pick_status"] for i in range(1, 7)]
        self.assertEqual(statuses, ["MODEL_TOP_PICK", "MODEL_TOP_PICK", "WATCH", "WATCH", "WATCH", "NO_PICK"])

    def test_clear_race_keeps_standard_radar(self) -> None:
        logic = _logic([70.0, 66.0, 62.0, 61.0, 60.0, 59.0])  # gap 8.0
        verdict = ensure_verdict(logic)
        self.assertEqual(verdict["confidence_tier"], "clear")
        self.assertEqual(verdict["radar_size"], 4)
        statuses = [logic["horses"][str(i)]["python_auto"]["model_pick_status"] for i in range(1, 7)]
        self.assertEqual(statuses, ["MODEL_TOP_PICK", "MODEL_TOP_PICK", "WATCH", "WATCH", "NO_PICK", "NO_PICK"])

    def test_medium_race(self) -> None:
        logic = _logic([66.0, 64.0, 63.0, 61.0, 60.0])  # gap 3.0
        verdict = ensure_verdict(logic)
        self.assertEqual(verdict["confidence_tier"], "medium")
        self.assertEqual(verdict["radar_size"], 4)
        self.assertEqual(verdict["top1_top3_gap"], 3.0)

    def test_top_two_within_half_point_are_reported_as_tied(self) -> None:
        logic = _logic([66.0, 65.6, 62.0, 61.0, 60.0])
        verdict = ensure_verdict(logic)
        self.assertTrue(verdict["top_pick_tied"])
        self.assertEqual(verdict["top1_top2_gap"], 0.4)
        self.assertIn("#1/#2 同級睇待", _confidence_tier_text(verdict))

    def test_clean_7d_decision_trace_is_explicit(self) -> None:
        logic = _logic([66.0, 64.0, 63.0, 61.0])
        verdict = ensure_verdict(logic)
        trace = verdict["decision_trace"]
        self.assertEqual(trace["contract"], "clean_7d_static")
        self.assertFalse(trace["changed"])
        self.assertEqual(trace["pre_rank_order"], trace["post_rank_order"])

    def test_pace_figure_coverage_alerts_below_ninety_percent(self) -> None:
        logic = _logic([66.0, 64.0, 63.0, 61.0, 60.0])
        for idx, horse in enumerate(logic["horses"].values()):
            horse["python_auto"]["score_provenance"] = {
                "pace_figure_score": "measured" if idx < 4 else "missing_neutral"
            }
        verdict = ensure_verdict(logic)
        coverage = verdict["pace_figure_coverage"]
        self.assertEqual(coverage["pct"], 80.0)
        self.assertTrue(coverage["alert"])
        self.assertEqual(coverage["status"], "low")

    def test_legacy_logic_without_provenance_is_not_false_alerted(self) -> None:
        logic = _logic([66.0, 64.0, 63.0])
        coverage = ensure_verdict(logic)["pace_figure_coverage"]
        self.assertEqual(coverage["status"], "unavailable")
        self.assertIsNone(coverage["pct"])
        self.assertFalse(coverage["alert"])


if __name__ == "__main__":
    unittest.main()


class ThinEvidenceRailTests(unittest.TestCase):
    """證據厚度安全欄：首選有 ≥2 個計分 leaf 停留預設 60 → 同第 2 位對調。

    根據：654 場乾淨語料，首選 ≥2 個預設嘅 19/44 上名 = 43.18% vs 基準 58.72%
    （二項 p = 0.027）；配對 bootstrap 首選上名 +1.70pp [+0.15, +3.36]。
    """

    SCORED = ("form_score", "performance_quality_score", "pace_figure_score",
              "trial_score", "jockey_score", "trainer_score",
              "jockey_horse_fit_score", "rating_score", "track_score")

    def _logic(self, specs):
        """specs = [(ability, n_default)] —— 第一個係場內最高分。"""
        horses = {}
        for i, (ability, n_def) in enumerate(specs, start=1):
            fs = {k: 70.0 for k in self.SCORED}
            for k in list(self.SCORED)[:n_def]:
                fs[k] = 60.0
            horses[str(i)] = {
                "horse_name": f"H{i}",
                "python_auto": {"ability_score": ability, "grade": "B",
                                "feature_scores": fs},
            }
        return {"horses": horses}

    def test_fires_when_top_pick_has_two_defaults(self):
        v = ensure_verdict(self._logic([(70.0, 2), (69.0, 0), (68.0, 0), (60.0, 0)]))
        self.assertEqual(v["ranking"][0]["horse_number"], "2")
        self.assertEqual(v["ranking"][1]["horse_number"], "1")
        swap = v["decision_trace"]["thin_evidence_swap"]
        self.assertEqual(swap["demoted"], "1")
        self.assertEqual(swap["promoted"], "2")
        self.assertEqual(swap["default_leaf_count"], 2)

    def test_does_not_fire_on_one_default(self):
        # 1 個預設嗰批實測 **跑得好過**基準（+2.23pp），所以一定唔可以觸發。
        v = ensure_verdict(self._logic([(70.0, 1), (69.0, 0), (68.0, 0), (60.0, 0)]))
        self.assertEqual(v["ranking"][0]["horse_number"], "1")
        self.assertIsNone(v["decision_trace"]["thin_evidence_swap"])
        self.assertFalse(v["decision_trace"]["changed"])

    def test_top3_and_top4_membership_never_changes(self):
        """呢個係安全欄零成本嘅來源：只換 1↔2 次序，成員不變。"""
        logic = self._logic([(70.0, 3), (69.0, 0), (68.0, 0), (67.0, 0), (50.0, 0)])
        v = ensure_verdict(logic)
        self.assertEqual({i["horse_number"] for i in v["ranking"][:3]}, {"1", "2", "3"})
        self.assertEqual({i["horse_number"] for i in v["ranking"][:4]}, {"1", "2", "3", "4"})

    def test_missing_feature_scores_is_not_no_evidence(self):
        """冇 feature_scores = 唔係一匹評過分嘅馬，唔准當 9 個預設。"""
        logic = {"horses": {
            "1": {"horse_name": "A", "python_auto": {"ability_score": 66.0, "grade": "B"}},
            "2": {"horse_name": "B", "python_auto": {"ability_score": 64.0, "grade": "B"}},
        }}
        v = ensure_verdict(logic)
        self.assertEqual(v["ranking"][0]["horse_number"], "1")
        self.assertFalse(v["decision_trace"]["changed"])

    def test_confidence_gaps_measured_on_ability_not_display_order(self):
        """安全欄唔可以污染信心指標。

        第一版把對調放喺 gap 計算**之前**，於是 2026-08-22 Randwick R1 出咗
        `top1_top2_gap = −0.84`（負數）同 `top_pick_tied = True`（無條件）。
        呢啲指標描述能力分散度，唔係展示次序。
        """
        v = ensure_verdict(self._logic([(71.05, 2), (70.20, 0), (69.88, 0), (68.26, 0)]))
        # 安全欄要照觸發
        self.assertEqual(v["ranking"][0]["horse_number"], "2")
        self.assertIsNotNone(v["decision_trace"]["thin_evidence_swap"])
        # 但 gap 要用**能力**次序計，一定係正數
        self.assertAlmostEqual(v["top1_top2_gap"], 0.85, places=2)
        self.assertAlmostEqual(v["top1_top3_gap"], 1.17, places=2)
        self.assertFalse(v["top_pick_tied"])


class WetOverlayGoingSpecificTests(unittest.TestCase):
    """濕地 overlay：今日地況嗰個 bucket 算全份，另一個算半份。

    2026-08-23：原本 1:1 溝埋，唔理今日跑咩地。Randwick R1（Soft 6）實例：
    Clear Proof 軟地 7:2-2-0（4/7 = 57%）被 2 場重地 0-0-0 拉到 overlay −0.571。
    """

    def test_soft_day_halves_the_heavy_record(self):
        from au_racing_engine.scoring import wet_form_feature
        gsl = "11:1-1-1 | 軟地: 7:2-2-0 | 重地: 2:0-0-0"
        # 軟地 7 場 4 上名 + 重地 (2 場 0 上名)×0.5 → (4+2)/(8+4) = 0.500 → 0.0
        self.assertAlmostEqual(wet_form_feature("Soft 6", gsl), 0.0, places=3)

    def test_heavy_day_halves_the_soft_record(self):
        from au_racing_engine.scoring import wet_form_feature
        gsl = "11:1-1-1 | 軟地: 7:2-2-0 | 重地: 2:0-0-0"
        # 重地 2 場 0 上名 + 軟地 (7 場 4 上名)×0.5 → (2+2)/(5.5+4) = 0.421
        self.assertLess(wet_form_feature("Heavy 9", gsl), 0.0)

    def test_dry_going_still_returns_zero(self):
        from au_racing_engine.scoring import wet_form_feature
        gsl = "11:1-1-1 | 軟地: 7:2-2-0 | 重地: 2:0-0-0"
        self.assertEqual(wet_form_feature("Good 4", gsl), 0.0)

    def test_matching_bucket_dominates(self):
        """同一份重地往績，喺重地日應該比喺軟地日影響更大。"""
        from au_racing_engine.scoring import wet_form_feature
        gsl = "0:0-0-0 | 軟地: 0:0-0-0 | 重地: 4:2-1-1"
        self.assertGreater(wet_form_feature("Heavy 9", gsl),
                           wet_form_feature("Soft 6", gsl))
