"""逐對深入覆盤（Case A：大熱贏但模型排第 2）單元測試。全部用合成 Logic 字典，唔讀真實資料。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / ".agents" / "skills" / "shared_racing" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import pair_autopsy as PA  # noqa: E402


def _make_au_pa(
    features: dict[str, float],
    *,
    overlays: dict[str, float] | None = None,
    evidence_state: dict[str, str] | None = None,
    provenance: dict[str, str] | None = None,
    rank: int = 1,
    matrix_override: dict[str, float] | None = None,
) -> dict:
    au_dim, au_mm, _au_ren, au_sco = PA._au_engine()
    full_feats = {k: 60.0 for k in au_dim.FEATURE_KEYS}
    full_feats.update(features)
    matrix = au_mm.map_features_to_matrix_scores(full_feats)
    if matrix_override:
        matrix.update(matrix_override)
    pure_7d = round(au_sco.compose_matrix_score(matrix), 4)
    ov = {k: 0.0 for k in PA.AU_OVERLAY_KEYS}
    if overlays:
        ov.update(overlays)
    final_score = round(pure_7d + sum(ov.values()), 4)
    ev = {k: "observed" for k in full_feats}
    if evidence_state:
        ev.update(evidence_state)
    prov = {k: "synthetic_observed" for k in full_feats}
    if provenance:
        prov.update(provenance)
    return {
        "rank": rank,
        "final_rank_score": final_score,
        "ability_score": final_score,
        "pure_7d_score": pure_7d,
        "matrix_scores": matrix,
        "feature_scores": full_feats,
        "feature_evidence_state": ev,
        "score_provenance": prov,
        **ov,
    }


def _make_hkjc_pa(
    features: dict[str, float],
    *,
    debut: bool = False,
    distance_adj: float = 0.0,
    deltas: dict[str, float] | None = None,
    provenance: dict[str, str] | None = None,
    rank: int = 1,
    matrix_override: dict[str, float] | None = None,
    race_shape_robustness: dict | None = None,
    thin_evidence_info: dict | None = None,
) -> dict:
    _hkjc_dim, hkjc_mm, _hkjc_ren, hkjc_sco = PA._hkjc_engine()
    all_keys = list(hkjc_sco.FEATURE_KEYS) + [
        "formline_strength_score",
        "margin_trend_score",
        "same_distance_signal_score",
        "trackwork_trend_score",
        "race_shape_context_score",
    ]
    full_feats = {k: 60.0 for k in all_keys}
    full_feats.update(features)
    dist_w = float(hkjc_sco.CENTRED_MATRIX_WEIGHTS["distance_fit"])
    feats_with_dist = dict(full_feats)
    feats_with_dist["distance_fit_score"] = 60.0 + distance_adj / dist_w
    matrix = hkjc_mm.map_features_to_matrix_scores(feats_with_dist, debut=debut)
    matrix["distance_fit"] = round(feats_with_dist["distance_fit_score"], 4)
    if matrix_override:
        matrix.update(matrix_override)

    weights = hkjc_sco.DEBUT_MATRIX_WEIGHTS if debut else hkjc_sco.MATRIX_WEIGHTS
    raw = sum(float(matrix[k]) * float(w) for k, w in weights.items())
    raw += sum(float(w) * (float(matrix[k]) - 60.0) for k, w in hkjc_sco.CENTRED_MATRIX_WEIGHTS.items())
    raw = round(raw, 2)
    extra_deltas = dict(deltas or {})
    raw = round(raw + sum(float(v) for v in extra_deltas.values()), 4)
    disp = round(hkjc_sco.to_display_scale(raw), 2)

    prov = {k: "synthetic_observed" for k in all_keys}
    prov["distance_fit_score"] = "same_distance_record" if distance_adj else "missing_neutral"
    if provenance:
        prov.update(provenance)

    pa = {
        "rank": rank,
        "ability_score_raw": raw,
        "ability_score": disp,
        "official_ranking_score": round(disp, 6),
        "matrix_scores": matrix,
        "feature_scores": {k: full_feats[k] for k in hkjc_sco.FEATURE_KEYS},
        "derived_feature_scores": {
            k: full_feats[k]
            for k in (
                "formline_strength_score",
                "margin_trend_score",
                "same_distance_signal_score",
                "trackwork_trend_score",
                "race_shape_context_score",
            )
        },
        "distance_suitability_adjustment": {"raw_adjustment": distance_adj},
        "score_provenance": prov,
        "reason_codes": ["debut_class_unknown"] if debut else [],
        "risk_flags": ["debut_race_experience_unknown"] if debut else [],
        **extra_deltas,
    }
    if race_shape_robustness is not None:
        pa["race_shape_robustness"] = race_shape_robustness
    if thin_evidence_info is not None:
        pa["thin_evidence"] = thin_evidence_info
    return pa


class SelectCaseATests(unittest.TestCase):
    def test_fav_wins_rank_2_creates_case(self):
        preds = {1: [{"horse_no": 3, "rank": 1}, {"horse_no": 5, "rank": 2}, {"horse_no": 1, "rank": 3}]}
        results = {1: {"results": [
            {"horse_no": 5, "placing": 1, "odds": 2.1},
            {"horse_no": 3, "placing": 2, "odds": 3.5},
            {"horse_no": 1, "placing": 3, "odds": 8.0},
        ]}}
        cases, counters = PA.select_case_a(preds, results)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0], {
            "race": 1, "field_size": 3, "winner_no": 5, "winner_sp": 2.1, "top_pick_no": 3, "fav_tied": False,
        })
        self.assertEqual(counters["races_with_results"], 1)
        self.assertEqual(counters["fav_won"], 1)
        self.assertEqual(counters["fav_won_rank2"], 1)
        self.assertEqual(counters["fav_won_rank1"], 0)

    def test_fav_wins_rank_1_and_rank_3plus_counters_only(self):
        preds = {
            1: [{"horse_no": 1, "rank": 1}, {"horse_no": 2, "rank": 2}],
            2: [{"horse_no": 1, "rank": 1}, {"horse_no": 2, "rank": 2}, {"horse_no": 4, "rank": 4}],
        }
        results = {
            1: {"results": [{"horse_no": 1, "placing": 1, "odds": 1.8}, {"horse_no": 2, "placing": 2, "odds": 4.0}]},
            2: {"results": [{"horse_no": 4, "placing": 1, "odds": 2.4}, {"horse_no": 1, "placing": 2, "odds": 3.0},
                            {"horse_no": 2, "placing": 3, "odds": 5.0}]},
        }
        cases, counters = PA.select_case_a(preds, results)
        self.assertEqual(cases, [])
        self.assertEqual(counters["races_with_results"], 2)
        self.assertEqual(counters["fav_won"], 2)
        self.assertEqual(counters["fav_won_rank1"], 1)
        self.assertEqual(counters["fav_won_rank2"], 0)
        self.assertEqual(counters["fav_won_rank3plus"], 1)

    def test_fav_tied_both_count_and_flag_set(self):
        preds = {1: [{"horse_no": 1, "rank": 1}, {"horse_no": 2, "rank": 2}, {"horse_no": 3, "rank": 3}]}
        results = {1: {"results": [
            {"horse_no": 2, "placing": 1, "odds": 2.5},
            {"horse_no": 3, "placing": 2, "odds": 2.5},
            {"horse_no": 1, "placing": 3, "odds": 6.0},
        ]}}
        cases, counters = PA.select_case_a(preds, results)
        self.assertEqual(len(cases), 1)
        self.assertTrue(cases[0]["fav_tied"])
        self.assertEqual(counters["fav_won_rank2"], 1)

    def test_winner_not_fav_excluded(self):
        preds = {1: [{"horse_no": 1, "rank": 1}, {"horse_no": 2, "rank": 2}]}
        results = {1: {"results": [
            {"horse_no": 2, "placing": 1, "odds": 7.5},
            {"horse_no": 1, "placing": 2, "odds": 1.9},
        ]}}
        cases, counters = PA.select_case_a(preds, results)
        self.assertEqual(cases, [])
        self.assertEqual(counters["races_with_results"], 1)
        self.assertEqual(counters["fav_won"], 0)

    def test_sp_missing_increments_counter_and_skips(self):
        preds = {1: [{"horse_no": 1, "rank": 1}, {"horse_no": 2, "rank": 2}]}
        results = {1: {"results": [
            {"horse_no": 2, "placing": 1, "odds": 2.0},
            {"horse_no": 1, "placing": 2, "odds": None},
        ]}}
        cases, counters = PA.select_case_a(preds, results)
        self.assertEqual(cases, [])
        self.assertEqual(counters["sp_missing"], 1)
        self.assertEqual(counters["fav_won"], 0)

    def test_dead_heat_for_first_ignored_with_note(self):
        preds = {1: [{"horse_no": 1, "rank": 1}, {"horse_no": 2, "rank": 2}]}
        results = {1: {"results": [
            {"horse_no": 1, "placing": 1, "odds": 2.2},
            {"horse_no": 2, "placing": 1, "odds": 2.0},
            {"horse_no": 3, "placing": 3, "odds": 9.0},
        ]}}
        cases, counters = PA.select_case_a(preds, results)
        self.assertEqual(cases, [])
        self.assertEqual(counters["dead_heat"], [1])
        self.assertIn({"race": 1, "note": "dead_heat"}, counters["notes"])
        self.assertEqual(counters["fav_won"], 0)

    def test_scratched_horse_ignored_for_field_size_and_sp(self):
        preds = {1: [{"horse_no": 1, "rank": 1}, {"horse_no": 2, "rank": 2}, {"horse_no": 9, "rank": 3}]}
        results = {1: {
            "scratched_horse_numbers": [9],
            "results": [
                {"horse_no": 2, "placing": 1, "odds": 2.0},
                {"horse_no": 1, "placing": 2, "odds": 3.0},
                {"horse_no": 9, "placing": 99, "odds": None},
            ],
        }}
        cases, counters = PA.select_case_a(preds, results)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["field_size"], 2)


class DecomposeAUTests(unittest.TestCase):
    def test_au_parts_sum_and_leaf_rounding_and_evidence(self):
        # jockey_trainer weights don't sum to exactly 1.0 (0.333333+0.285714+0.380952=0.999999)
        # and 2dp rounding in map_features_to_matrix_scores produces real leaf rounding drift.
        pa_top = _make_au_pa(
            {
                "form_quality_score": 74.0,
                "jockey_score": 68.123,
                "trainer_score": 64.456,
                "jockey_horse_fit_score": 66.789,
                "track_score": 60.0,     # 預設 60（fallback）
                "pace_figure_score": 60.0,  # 實測 60（observed）-> 唔應當證據薄
            },
            overlays={"draw_feature": 1.25},
            evidence_state={"track_score": "fallback", "pace_figure_score": "observed"},
            provenance={"track_score": "missing_neutral", "pace_figure_score": "pf_l600_delta_field_relative"},
            rank=1,
        )
        pa_win = _make_au_pa(
            {
                "form_quality_score": 66.0,
                "jockey_score": 60.0,
                "trainer_score": 60.0,
                "jockey_horse_fit_score": 60.0,
                "track_score": 52.0,
                "pace_figure_score": 71.0,
            },
            overlays={"draw_feature": -0.50},
            rank=2,
        )
        dtrace = {
            "changed": True,
            "thin_evidence_swap": {"demoted": "5", "promoted": "3", "default_leaf_count": 2},
            "reason": "swap test",
        }
        d = PA.decompose_au(pa_top, pa_win, decision_trace=dtrace)
        self.assertTrue(d["leaf_level_valid"])
        self.assertFalse(d["unexplained"])
        self.assertLess(abs(d["residual"]), 0.005)
        self.assertIsNotNone(d["swap"])

        top_level_sum = sum(p["contribution"] for p in d["parts"] if p["kind"] in ("dimension", "overlay", "adjustment"))
        self.assertAlmostEqual(top_level_sum + d["residual"], d["total_gap"], places=6)

        # Leaf contributions + leaf_rounding == dimension contribution for every dimension
        for dim_p in [p for p in d["parts"] if p["kind"] == "dimension"]:
            dim_key = dim_p["key"]
            leaf_sum = sum(p["contribution"] for p in d["parts"] if p["kind"] == "leaf" and p["dimension"] == dim_key)
            self.assertAlmostEqual(leaf_sum + d["leaf_rounding"][dim_key], dim_p["contribution"], places=6)
        self.assertGreater(abs(d["leaf_rounding"]["jockey_trainer"]), 1e-6)

        # Weak evidence flags track_score (fallback 60) but NOT pace_figure_score (observed 60, and negative anyway)
        weak_keys = {p["key"] for p in d["weak_evidence_reasons"]}
        self.assertIn("track_score", weak_keys)
        self.assertNotIn("pace_figure_score", weak_keys)
        track_part = next(p for p in d["parts"] if p["kind"] == "leaf" and p["key"] == "track_score")
        self.assertTrue(track_part["top_evidence"]["default_60"])
        pace_part = next(p for p in d["parts"] if p["kind"] == "leaf" and p["key"] == "pace_figure_score")
        self.assertFalse(pace_part["top_evidence"]["default_60"])

    def test_au_version_guard_trips_on_dimension_mismatch(self):
        pa_top = _make_au_pa({"form_quality_score": 70.0}, matrix_override={"stability": 85.0}, rank=1)
        pa_win = _make_au_pa({"form_quality_score": 65.0}, rank=2)
        d = PA.decompose_au(pa_top, pa_win)
        self.assertFalse(d["leaf_level_valid"])
        self.assertFalse(any(p["kind"] == "leaf" for p in d["parts"]))
        self.assertTrue(any(p["kind"] == "dimension" for p in d["parts"]))
        top_sum = sum(p["contribution"] for p in d["parts"] if p["kind"] in ("dimension", "overlay", "adjustment"))
        self.assertAlmostEqual(top_sum + d["residual"], d["total_gap"], places=6)


class DecomposeHKJCTests(unittest.TestCase):
    def test_hkjc_normal_vs_debut_and_thin_evidence(self):
        # top_pick is debut (uses DEBUT_MATRIX_WEIGHTS + DEBUT_MATRIX_FORMULAS), winner is normal (MATRIX_WEIGHTS)
        pa_top = _make_hkjc_pa(
            {
                "form_score": 62.0,
                "class_score": 74.0,
                "weight_score": 70.0,
                "jockey_score": 68.0,
                "race_shape_context_score": 65.0,
            },
            debut=True,
            deltas={"debut_trainer_delta": 1.10, "thin_evidence_delta": -0.75},
            thin_evidence_info={"starts": 1, "gap": 210, "lam": 0.5},
            rank=1,
        )
        pa_win = _make_hkjc_pa(
            {
                "form_score": 70.0,
                "consistency_score": 66.0,
                "speed_score": 72.0,
                "jockey_score": 64.0,
                "race_shape_context_score": 78.0,
            },
            debut=False,
            distance_adj=0.4284,
            deltas={"market_history_delta": -0.40},
            # Simulate winsorized race_shape (base 78 -> candidate 74)
            matrix_override={"race_shape": 74.0},
            race_shape_robustness={
                "applied": True,
                "base_race_shape": 78.0,
                "candidate_race_shape": 74.0,
                "raw_adjustment": 0.1925 * (74.0 - 78.0),
            },
            rank=2,
        )
        # Recompute pa_win raw score after winsorizing race_shape to 74.0
        _hd, _hmm, _hr, hkjc_sco = PA._hkjc_engine()
        win_raw = sum(float(pa_win["matrix_scores"][k]) * float(w) for k, w in hkjc_sco.MATRIX_WEIGHTS.items())
        win_raw += hkjc_sco.CENTRED_MATRIX_WEIGHTS["distance_fit"] * (pa_win["matrix_scores"]["distance_fit"] - 60.0)
        win_raw += pa_win["market_history_delta"]
        pa_win["ability_score_raw"] = round(win_raw, 4)
        pa_win["ability_score"] = round(hkjc_sco.to_display_scale(win_raw), 2)
        pa_win["official_ranking_score"] = round(pa_win["ability_score"], 6)

        d = PA.decompose_hkjc(pa_top, pa_win, [pa_top, pa_win])
        self.assertTrue(d["leaf_level_valid"])
        self.assertTrue(d["top_debut"])
        self.assertFalse(d["win_debut"])
        self.assertTrue(d["nonlinear"])
        self.assertFalse(d["unexplained"])
        self.assertLess(abs(d["residual"]), 0.02)

        thin_parts = [p for p in d["parts"] if p["kind"] == "adjustment" and p["key"] == "thin_evidence"]
        self.assertEqual(len(thin_parts), 1)
        self.assertAlmostEqual(thin_parts[0]["contribution"], -0.75, places=6)

        # class_advantage has weight 0.1667 for debut and 0.0 for normal -> positive contribution from top debut horse
        cls_dim = next(p for p in d["parts"] if p["kind"] == "dimension" and p["key"] == "class_advantage")
        self.assertGreater(cls_dim["contribution"], 1.5)

        top_sum = sum(p["contribution"] for p in d["parts"] if p["kind"] in ("dimension", "adjustment"))
        self.assertAlmostEqual(top_sum + d["residual"], d["total_gap"], places=6)


class MeetingDayAndRenderTests(unittest.TestCase):
    def _write_au_meeting(self, root: Path, name: str = "2026-11-26 Hawkesbury Race 1-1") -> Path:
        meeting = root / name
        snap = meeting / "_prediction_snapshots" / "20261126T100000+1100-abc"
        snap.mkdir(parents=True)
        (snap / "manifest.json").write_text(json.dumps({"created_at": "2026-11-26T10:00:00+11:00"}), encoding="utf-8")
        (snap / "Race_1_Auto_Scoring.csv").write_text(
            "race_number,horse_number,horse_name,rank,ability_score\n"
            "1,3,TopHorse,1,70.0\n"
            "1,5,FavHorse,2,67.0\n",
            encoding="utf-8",
        )
        pa_top = _make_au_pa({"form_quality_score": 76.0, "track_score": 60.0},
                             evidence_state={"track_score": "missing"},
                             provenance={"track_score": "missing_neutral"}, rank=1)
        pa_win = _make_au_pa({"form_quality_score": 65.0, "jockey_score": 72.0}, rank=2)
        logic = {
            "horses": {
                "3": {"horse_number": 3, "horse_name": "TopHorse", "python_auto": pa_top},
                "5": {"horse_number": 5, "horse_name": "FavHorse", "python_auto": pa_win},
            },
            "python_auto_verdict": {"decision_trace": {"changed": False}},
        }
        (snap / "Race_1_Logic.json").write_text(json.dumps(logic, ensure_ascii=False), encoding="utf-8")
        (meeting / "Race_Results_Reflector.md").write_text(
            "## Race 1\n1st: #5 FavHorse (1.5L) SP$2.10\n2nd: #3 TopHorse (1.5L) SP$4.20\n",
            encoding="utf-8",
        )
        return meeting

    def test_autopsy_meeting_and_day_and_render_md(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            meeting = self._write_au_meeting(root)
            res = PA.autopsy_meeting("au", meeting)
            self.assertIsNone(res["reason"])
            self.assertEqual(len(res["cases"]), 1)
            case = res["cases"][0]
            self.assertEqual(case["top_pick"]["name"], "TopHorse")
            self.assertEqual(case["winner"]["name"], "FavHorse")
            self.assertEqual(case["winner"]["sp"], 2.1)

            day_res = PA.autopsy_day("au", "2026-11-26", root=root)
            self.assertEqual(len(day_res["cases"]), 1)
            md = PA.render_md(day_res)
            self.assertIn("R1 Hawkesbury：大熱 FavHorse（SP 2.10，模型第 2）贏；我哋首選 TopHorse（SP 4.20，第 2）。", md)
            self.assertIn("近績質素分", md)
            self.assertIn("騎師分", md)

    def test_skip_reasons(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            empty = root / "2026-11-26 Empty"
            empty.mkdir()
            self.assertEqual(PA.autopsy_meeting("au", empty)["reason"], "no_results")

            no_snap = root / "2026-11-26 NoSnap"
            no_snap.mkdir()
            (no_snap / "Race_Results_Reflector.md").write_text("## Race 1\n1st: #1 A SP$2.0\n", encoding="utf-8")
            self.assertEqual(PA.autopsy_meeting("au", no_snap)["reason"], "no_snapshot")

            hk_nocut = root / "2026-11-26_HappyValley"
            hk_nocut.mkdir()
            (hk_nocut / "2026-11-26_HappyValley_全日賽果.json").write_text(
                json.dumps({"1": {"race_no": 1, "results": []}}), encoding="utf-8"
            )
            self.assertEqual(PA.autopsy_meeting("hkjc", hk_nocut)["reason"], "缺開跑時間")


if __name__ == "__main__":
    unittest.main()


class ScratchedTopPickTests(unittest.TestCase):
    def test_scratched_published_top_pick_uses_order_among_starters(self):
        """賽前首選臨場退出：有跑嘅馬入面大熱其實係我哋第 1 —— 唔可以將退出馬同頭馬對比（Hydrogen 2026-11-27）。"""
        preds = {1: [{"horse_no": 7, "rank": 1}, {"horse_no": 3, "rank": 2}, {"horse_no": 5, "rank": 3}]}
        results = {1: {"scratched_horse_numbers": [7], "results": [
            {"horse_no": 3, "placing": 1, "odds": 1.9}, {"horse_no": 5, "placing": 2, "odds": 3.5}]}}
        cases, counters = PA.select_case_a(preds, results)
        self.assertEqual(cases, [])
        self.assertEqual(counters["fav_won_rank1"], 1)
        self.assertIn({"race": 1, "note": "rank_shifted_by_scratching"}, counters["notes"])

    def test_winner_without_prediction_is_not_counted_as_fav_won(self):
        preds = {1: [{"horse_no": 3, "rank": 1}]}
        results = {1: {"results": [{"horse_no": 9, "placing": 1, "odds": 1.5}, {"horse_no": 3, "placing": 2, "odds": 4.0}]}}
        cases, counters = PA.select_case_a(preds, results)
        self.assertEqual((cases, counters["fav_won"], counters["winner_unranked"]), ([], 0, 1))
