"""A blank new season must not count as evidence of unsuccessful starts."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine.engine_core import RacingEngine
from hkjc_racing_engine import scoring
from hkjc_racing_engine.matrix_mapper import map_features_to_matrix_scores


def evaluate(record):
    horse = {"career_tag": "ESTABLISHED", "career_race_starts": 15,
             "is_debut": False, "season_stats": record}
    engine = RacingEngine(horse, {})
    score, note, _ = engine._class_score({})
    return score, note, engine.risk_flags


class ZeroStartSeasonTests(unittest.TestCase):
    def test_unraced_season_matches_missing_evidence(self):
        empty = evaluate("季內 (0-0-0-0)")
        missing = evaluate("")
        self.assertEqual(empty[0], missing[0])
        self.assertNotIn("季內未上名", empty[1])
        self.assertNotIn("class_edge_unproven", empty[2])

    def test_actual_unplaced_start_still_counts(self):
        empty = evaluate("季內 (0-0-0-0)")
        raced = evaluate("季內 (0-0-0-1)")
        self.assertEqual(raced[0], empty[0] - 4)
        self.assertIn("季內未上名", raced[1])
        self.assertIn("class_edge_unproven", raced[2])

    def test_perfect_record_keeps_season_bonus(self):
        empty = evaluate("季內 (0-0-0-0)")
        placed = evaluate("季內 (3-0-0-0)")
        self.assertEqual(placed[0], empty[0] + scoring.CLASS_MICRO_WEIGHTS["season_place_3_bonus"])
        self.assertIn("季內有交代", placed[1])

    def test_distance_record_cannot_supply_season_evidence(self):
        with_distance = evaluate("季內 (0-0-0-0) | 同程 (1-0-0-1)")
        self.assertNotIn("季內未上名", with_distance[1])
        self.assertNotIn("同程", with_distance[1])

    def test_distance_record_is_an_independent_visible_adjustment(self):
        horse = {
            "career_tag": "ESTABLISHED",
            "career_race_starts": 15,
            "is_debut": False,
            "season_stats": "季內 (0-0-0-0) | 同程 (1-0-0-1)",
        }
        engine = RacingEngine(horse, {"distance": "1200"})
        class_score, _, _ = engine._class_score({})
        features = {"class_score": class_score, "weight_score": 60.0}
        matrix = map_features_to_matrix_scores(features)
        adjustment = engine._distance_suitability_adjustment(features, matrix)

        self.assertEqual(adjustment["signal"], "same_distance_placed")
        self.assertAlmostEqual(adjustment["raw_adjustment"], 0.4284, places=6)
        self.assertEqual(class_score, evaluate("季內 (0-0-0-0)")[0])

    def test_distance_v2_is_recorded_as_shadow_without_replacing_live_v1(self):
        horse = {
            "career_tag": "ESTABLISHED",
            "career_race_starts": 15,
            "is_debut": False,
            "season_stats": "季內 (0-0-0-0) | 同程 (1-0-0-1)",
            "distance_suitability_v2": (
                "今場=跑馬地草地 66.0分 | 目標有效樣本=2.0(原始3) | "
                "場地基準有效樣本=4.0(原始6) | 採用來源=local_history"
            ),
        }
        engine = RacingEngine(horse, {"venue": "跑馬地", "distance": "1200"})
        features = {"class_score": 60.0, "weight_score": 60.0}
        matrix = map_features_to_matrix_scores(features)
        adjustment = engine._distance_suitability_adjustment(features, matrix)

        self.assertEqual(adjustment["signal"], "same_distance_placed")
        self.assertGreater(adjustment["raw_adjustment"], 0.0)
        self.assertEqual(adjustment["v2_shadow"]["profile"]["weight"], 0.08)
        self.assertEqual(adjustment["v2_shadow"]["component_score"], 66.0)
        self.assertEqual(
            adjustment["v2_shadow"]["status"],
            "prospective_shadow_pending_primary_gate",
        )

    def test_distance_v2_awt_is_visible_but_not_ranked(self):
        horse = {
            "career_tag": "ESTABLISHED", "career_race_starts": 5,
            "distance_suitability_v2": (
                "今場=沙田AWT 68.0分 | 目標有效樣本=1.0(原始1) | "
                "場地基準有效樣本=2.0(原始2) | 採用來源=foreign_dirt_synthetic"
            ),
        }
        engine = RacingEngine(horse, {"venue": "沙田", "surface": "AWT", "distance": "1200"})
        features = {"class_score": 60.0, "weight_score": 60.0}
        matrix = map_features_to_matrix_scores(features)
        adjustment = engine._distance_suitability_adjustment(features, matrix)

        self.assertEqual(adjustment["signal"], "neutral")
        self.assertEqual(adjustment["raw_adjustment"], 0.0)
        self.assertEqual(adjustment["v2_shadow"]["profile"]["weight"], 0.0)
        self.assertEqual(adjustment["v2_shadow"]["candidate_raw_adjustment"], 0.0)

    def test_distance_v2_standard_shadow_replaces_v1_only_inside_candidate(self):
        horse = {
            "career_tag": "ESTABLISHED", "career_race_starts": 10,
            "season_stats": "季內 (0-0-0-0) | 同程 (1-0-0-2)",
            "distance_suitability_v2": (
                "今場=跑馬地草地 65.0分 | 目標有效樣本=2.0(原始2) | "
                "場地基準有效樣本=3.0(原始4) | 採用來源=local_history"
            ),
        }
        engine = RacingEngine(horse, {"venue": "跑馬地", "distance": "1200"})
        baseline = engine.analyze_horse()
        shadow = engine.build_shadow_profile("distance_suitability_v2", base_auto=baseline)

        self.assertTrue(shadow["applied"])
        self.assertEqual(shadow["profile"], "distance_suitability_v2")
        self.assertEqual(shadow["surface"], "HV_TURF")
        self.assertEqual(shadow["candidate_profile"]["weight"], 0.08)
        self.assertEqual(shadow["evidence_status"], "prospective_shadow_pending_primary_gate")

    def test_two_wins_from_six_is_proven_distance_and_not_a_risk(self):
        horse = {
            "career_tag": "ESTABLISHED",
            "career_race_starts": 7,
            "is_debut": False,
            "season_stats": "季內 (0-0-0-0) | 同程 (2-0-0-4) | 同場同程 (2-0-0-4)",
            "_data": {
                "best_distance": "1200m | 今仗 1200m = 6場 (2-0-0-4)",
                "medical_flags": "✅ 無醫療事故記錄",
            },
        }
        engine = RacingEngine(horse, {"distance": "1200"})
        result = engine.analyze_horse()

        self.assertEqual(result["feature_scores"]["distance_score"], 72.0)
        self.assertNotIn("distance_unproven", result["risk_flags"])
        self.assertNotIn("路程證明不足", result["score_breakdown"]["risk_score"]["note"])
        self.assertEqual(
            result["distance_suitability_adjustment"]["signal"],
            "same_distance_placed",
        )
        self.assertGreater(result["distance_suitability_adjustment"]["raw_adjustment"], 0)
        self.assertNotIn("同程", result["score_breakdown"]["class_score"]["note"])


class MedicalContextReadoutTests(unittest.TestCase):
    def test_latest_incident_qualifies_speed_interpretation(self):
        engine = RacingEngine({"_data": {"medical_flags": "第1仗: ⚠️ 心臟·心律不正"}}, {})
        note = engine._describe_sectional_matrix(38, {"speed_score": 43}, {})
        self.assertIn("不能視作多次獨立能力下滑", note)
        self.assertIn("復出風險", note)

    def test_older_incident_does_not_excuse_latest_speed(self):
        engine = RacingEngine({"_data": {"medical_flags": "第2仗: ⚠️ 心臟·心律不正"}}, {})
        note = engine._describe_sectional_matrix(38, {"speed_score": 43}, {})
        self.assertNotIn("上仗有醫療異常", note)

    def test_known_medical_record_is_not_called_missing(self):
        engine = RacingEngine({"_data": {"medical_flags": "第1仗: ⚠️ 心臟·心律不正"}}, {})
        note = engine._describe_horse_health_matrix(60, {}, {})
        self.assertIn("歷史醫療異常", note)
        self.assertNotIn("醫療資料未齊", note)


def incident_horse(*, medical="第1仗: ⚠️ 心臟·心律不正", raw_l400="26.10", l400_trend=None):
    return {
        "horse_name": "異常仗測試馬",
        "career_tag": "ESTABLISHED",
        "career_race_starts": 12,
        "last_6_finishes": "12-2-3-4-5-6",
        "season_stats": "季內 (0-0-0-0)",
        "weight": "126",
        "barrier": "4",
        "_data": {
            "medical_flags": medical,
            "raw_l400": raw_l400,
            "l400_trend": l400_trend or "（最舊 → 最新）22.49→22.25→23.38→26.10 → 趨勢: 衰退中 ⚠️",
            "energy_trend": "（最舊 → 最新）98→96→99→61 → 趨勢: 下降 ⚠️",
            "finish_time_block": "偏差: -0.72s→-0.19s→-0.71s→+2.36s → 趨勢: 📉退步中 ⚠️",
            "finish_time_adj_level": "⚠️ 步速修正後仍偏慢",
            "engine_type": "快開慢收型 | 信心: 中",
            "best_distance": "1650m | 今仗 1650m = 4場",
            "trackwork_digest": "晨操正常。",
            "recent_6_detail": "第1仗: 12名 18-1/2 | 第2仗: 2名 1/2 | 第3仗: 3名 1",
            "last_finish": "12",
            "last_margin": "18-1/2",
            "weight_carried": 126,
        },
    }


class IncidentReliabilityShadowTests(unittest.TestCase):
    def test_current_oldest_to_latest_sequence_uses_only_prior_runs(self):
        context = RacingEngine(incident_horse(), {"distance": "1650"})._prior_l400_median()
        self.assertEqual(context["prior_median"], 22.49)
        self.assertEqual(context["prior_runs"], 3)
        self.assertEqual(context["sequence_direction"], "oldest_to_latest")

    def test_legacy_latest_to_oldest_sequence_is_detected_from_raw_anchor(self):
        horse = incident_horse(
            raw_l400="25.43",
            l400_trend="25.43→25.59→24.84→24.40→23.28→24.32 → 趨勢: 衰退中 ⚠️",
        )
        context = RacingEngine(horse, {})._prior_l400_median()
        self.assertEqual(context["prior_median"], 24.4)
        self.assertEqual(context["sequence_direction"], "latest_to_oldest")

    def test_unanchored_sequence_is_not_adjusted(self):
        horse = incident_horse(raw_l400="27.00")
        self.assertIsNone(RacingEngine(horse, {})._prior_l400_median())

    def test_combined_shadow_changes_only_sectional_dimension(self):
        engine = RacingEngine(incident_horse(), {"distance": "1650"})
        baseline = engine.analyze_horse()
        shadow = engine.build_shadow_profile("incident_reliability", base_auto=baseline)
        self.assertTrue(shadow["applied"])
        self.assertGreater(shadow["sectional_score"], baseline["matrix_scores"]["sectional"])
        self.assertGreater(shadow["ability_score"], baseline["ability_score"])
        for key, value in baseline["matrix_scores"].items():
            if key != "sectional":
                self.assertEqual(shadow["matrix_scores"][key], value)
        self.assertEqual(
            {item["factor"] for item in shadow["adjustments"]},
            {"raw_l400", "l400_trend", "energy_trend", "finish_time_trend"},
        )

    def test_older_incident_does_not_change_shadow_score(self):
        engine = RacingEngine(incident_horse(medical="第2仗: ⚠️ 心臟·心律不正"), {"distance": "1650"})
        baseline = engine.analyze_horse()
        shadow = engine.build_shadow_profile("incident_reliability", base_auto=baseline)
        self.assertFalse(shadow["applied"])
        self.assertEqual(shadow["ability_score"], baseline["ability_score"])
