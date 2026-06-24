from __future__ import annotations

import json
import csv
import subprocess
import sys
import tempfile
import unittest
import io
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
SKILL_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi_auto"
SCRIPT = SKILL_DIR / "scripts" / "hkjc_auto_orchestrator.py"
ENGINE_DIR = SKILL_DIR / "scripts" / "racing_engine"
EXTRACTOR_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_race_extractor" / "scripts"
sys.path.insert(0, str(ENGINE_DIR))
sys.path.insert(0, str(EXTRACTOR_DIR))

import extract_trackwork
from matrix_mapper import map_features_to_matrix_scores
from scoring import MATRIX_WEIGHTS, compute_grade
from engine_core import RacingEngine
from features.jockey import JockeyScorer
from features.speed import SpeedScorer
from features.trainer import TrainerScorer


def _logic() -> dict:
    return {
        "race_analysis": {"race_number": 1, "race_class": "第五班", "distance": "1650"},
        "horses": {
            "1": {
                "horse_name": "測試甲",
                "jockey": "潘頓",
                "trainer": "蔡約翰",
                "weight": "126",
                "barrier": "2",
                "last_6_finishes": "1-2-3-4-5-6",
                "season_stats": "季內 (1-1-1-3)",
                "trackwork": {},
                "_data": {
                    "trackwork_digest": "晨操正常。",
                    "recent_6_detail": "第1仗: 1名 | 第2仗: 2名 | 第3仗: 3名",
                    "margin_trend": "1→2→3 → 趨勢: 穩定",
                    "engine_type": "混合型 | 信心: 中",
                    "best_distance": "1650m | 今仗 1650m = 3場 (1-1-1)",
                    "raw_l400": "23.40",
                    "l400_trend": "23.40→23.55→23.70 → 趨勢: 穩定",
                    "energy_trend": "90→91→92 → 趨勢: 上升 ✅",
                    "finish_time_adj": "+0.20s→+0.10s",
                    "finish_time_adj_level": "➖ 步速修正後接近平均",
                    "position_window": "第1仗: 沿途位=8-7-1, XW=(1W1W1W), 消耗=低消耗",
                    "draw_verdict": "✅有利 (上名30.0%/入Q24.0%/勝8.0%)",
                    "running_style": "後上 | 信心: 高",
                    "position_pi": "[+3, +4, +5] → 趨勢: 上升軌 ✅",
                    "draw_position_fit": "走內(1-2W):3場 平均名次3.0 上名2次",
                    "track_bias": "內檔(1-4)上名率26.5% vs 外檔(9+)上名率18.2% → 輕微偏內",
                    "gear_change": "上仗 B/TT → 今仗 B/TT | 無變動",
                    "trackwork_trainer": "賽日騎師沒有直接參與操練；操練者身份：助手3次。操練配備：B/TT；備戰分60。",
                    "jockey_combo_block": "人馬組合統計 [V5.1]:**\n  今場騎師: 潘頓\n  📊 騎師×此馬歷史:\n  | 騎師 | 場次 | 勝 | 入Q | 上名 | 平均名次 | 勝率 | 位率 |\n  |------|------|---|-----|------|----------|------|------|\n  | 潘頓 ← 今場 | 3 | 1 | 1 | 2 | 3.0 | 33.3% | 66.7% |\n  近6場騎師歷史:\n  | # | 日期 | 騎師 | 名次 | 備注 |\n  |---|------|------|------|------|\n  | 1 | 01/05/2026 | 潘頓 | 1 |  |\n  | 2 | 12/04/2026 | 潘頓 | 2 |  |\n  | 3 | 01/04/2026 | 田泰安 | 4 |  |",
                    "weight_trend": "1121→1118→1116 → 📈微增 (波幅5lb)",
                    "trackwork_health": "active_days=18, blank_days=3, swimming=10, aqua_walker=0, risk_flags=['操練放緩']",
                    "medical_flags": "✅ 無醫療事故記錄",
                    "formline_strength": "中強 (強組比例: 4/10)",
                    "last_finish": "1",
                    "last_margin": "頭位",
                    "total_starts": 18,
                    "total_wins": 3,
                    "rating_trend": "52→50→48→47 → 回落中",
                    "weight_carried": 126,
                    "venue_transfer": "未知",
                },
            },
            "2": {
                "horse_name": "測試乙",
                "jockey": "普通騎師",
                "trainer": "普通練馬師",
                "weight": "133",
                "barrier": "12",
                "last_6_finishes": "9-8-7-6-5-4",
                "season_stats": "季內 (0-0-0-6)",
                "trackwork": {},
                "_data": {"trackwork_digest": "晨操放緩。"},
            },
        },
    }


class AutoOutputTests(unittest.TestCase):
    def test_orchestrator_backfills_missing_header_metadata_from_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            logic_path = folder / "Race_1_Logic.json"
            logic = _logic()
            logic["horses"]["1"]["trainer"] = ""
            logic["horses"]["1"]["jockey"] = ""
            logic["horses"]["1"]["weight"] = ""
            logic["horses"]["1"]["barrier"] = ""
            logic["horses"]["1"]["_data"]["trainer_name"] = ""
            logic["horses"]["1"]["_data"]["jockey_name"] = ""
            logic_path.write_text(json.dumps(logic, ensure_ascii=False), encoding="utf-8")
            (folder / "05-13 Race 1 Facts.md").write_text(
                "### 馬號 1 — 測試甲 | 騎師: 潘頓 | 練馬師: 蔡約翰 | 負磅: 126 | 檔位: 2\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(folder)],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            updated = json.loads(logic_path.read_text(encoding="utf-8"))
            horse = updated["horses"]["1"]
            self.assertEqual(horse["trainer"], "蔡約翰")
            self.assertEqual(horse["jockey"], "潘頓")
            self.assertEqual(horse["weight"], "126")
            self.assertEqual(horse["barrier"], "2")
            self.assertEqual(horse["_data"]["trainer_name"], "蔡約翰")
            self.assertEqual(horse["_data"]["jockey_name"], "潘頓")

    def test_orchestrator_backfills_missing_trainer_from_trackwork_when_facts_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            logic_path = folder / "Race_1_Logic.json"
            logic = _logic()
            logic["horses"]["1"]["trainer"] = ""
            logic["horses"]["1"]["_data"]["trainer_name"] = ""
            logic_path.write_text(json.dumps(logic, ensure_ascii=False), encoding="utf-8")
            (folder / "05-13 Race 1 Facts.md").write_text(
                "### 馬號 1 — 測試甲 | 騎師: 潘頓 | 負磅: 126 | 檔位: 2\n",
                encoding="utf-8",
            )
            (folder / "2026-05-13 Race 1 晨操.md").write_text(
                "### 馬號 1 — 測試甲 | 騎師: 潘頓 | 練馬師: 蔡約翰\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(folder)],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            updated = json.loads(logic_path.read_text(encoding="utf-8"))
            horse = updated["horses"]["1"]
            self.assertEqual(horse["trainer"], "蔡約翰")
            self.assertEqual(horse["_data"]["trainer_name"], "蔡約翰")

    def test_calibrated_matrix_weights_are_locked(self) -> None:
        # ML walk-forward backtest (18 meetings / 180 races) showed horse_health
        # is noise in the ranking layer; its 0.0378 mass was redistributed
        # proportionally (total mass kept at 0.9999 to preserve the grade scale).
        self.assertAlmostEqual(sum(MATRIX_WEIGHTS.values()), 1.0, places=3)
        self.assertEqual(
            MATRIX_WEIGHTS,
            {
                "sectional": 0.1849,
                "trainer_signal": 0.2209,
                "stability": 0.0919,
                "race_shape": 0.2560,
                "class_advantage": 0.1335,
                "horse_health": 0.0378,
                "form_line": 0.0749,
            },
        )

    def test_chinese_jockey_and_trainer_names_are_scored(self) -> None:
        self.assertEqual(JockeyScorer({"jockey": "潘頓"}, {}).compute()[0], 85.0)
        self.assertEqual(JockeyScorer({"jockey": "麥道朗"}, {}).compute()[0], 85.0)
        self.assertEqual(JockeyScorer({"jockey": "田泰安"}, {}).compute()[0], 75.0)
        self.assertEqual(JockeyScorer({"jockey": "艾兆禮"}, {}).compute()[0], 75.0)
        self.assertEqual(TrainerScorer({"trainer": "蔡約翰"}, {}).compute()[0], 80.0)
        self.assertEqual(TrainerScorer({"trainer": "韋達"}, {}).compute()[0], 75.0)
        self.assertEqual(TrainerScorer({"trainer": "姚本輝"}, {}).compute()[0], 70.0)

    def test_grade_uses_displayed_ability_boundary(self) -> None:
        self.assertEqual(compute_grade(60.0), "C+")
        self.assertEqual(compute_grade(59.99), "C")
        self.assertEqual(compute_grade(56.0), "C")
        self.assertEqual(compute_grade(55.99), "C-")
        self.assertEqual(compute_grade(52.0), "C-")
        self.assertEqual(compute_grade(51.99), "D")
        self.assertEqual(compute_grade(48.0), "D")
        self.assertEqual(compute_grade(47.99), "E")

    def test_track_going_does_not_reward_generic_draw_hit_rate(self) -> None:
        horse = {
            "horse_name": "測試甲",
            "jockey": "普通騎師",
            "trainer": "普通練馬師",
            "weight": "126",
            "barrier": "6",
            "last_6_finishes": "4-5-6",
            "season_stats": "季內 (0-0-0-3)",
            "_data": {
                "track_bias": "內檔(1-4)上名率28.2% vs 外檔(9+)上名率18.5% → 輕微偏內",
                "draw_verdict": "⚠️中性 (上名25.0%/入Q19.0%/勝13.0%)",
            },
        }
        result = RacingEngine(horse, {"distance": "1200m"}).analyze_horse()

        self.assertEqual(result["feature_scores"]["track_going_score"], 60.0)

    def test_foreign_runner_not_penalised_for_missing_hk_data(self) -> None:
        # A visiting international runner: real overseas form, no HKJC form/medical.
        foreign = {
            "horse_name": "外國馬",
            "jockey": "海外騎師",
            "trainer": "海外練馬師",
            "weight": "126",
            "barrier": "6",
            "_data": {
                "pdf_overseas_races": [
                    {"date": "2026/05/01", "track_dist": "Royal Ascot 1600m",
                     "class_level": "G1", "rank": "1/12", "jockey": "X",
                     "weight": "126", "time": "1.35.2", "margin": "1"},
                ],
            },
        }
        # Same horse but with NO real overseas rows (all-dash placeholder) and no HK data.
        blank = {
            **foreign,
            "_data": {"pdf_overseas_races": [
                {"date": "-", "track_dist": "-", "class_level": "-", "rank": "-",
                 "jockey": "-", "weight": "-", "time": "-", "margin": "-"}]},
        }
        eng_f = RacingEngine(foreign, {"distance": "1600m"})
        eng_b = RacingEngine(blank, {"distance": "1600m"})
        self.assertTrue(eng_f._is_foreign_runner())
        self.assertFalse(eng_b._is_foreign_runner())

        # Isolate the medical/coverage gating with neutral features (no draw/distance noise).
        neutral = {"draw_score": 60, "distance_score": 60, "risk_score": 60}
        risk_f, _, _ = eng_f._risk_score(neutral)
        risk_b, _, _ = eng_b._risk_score(neutral)
        self.assertNotIn("medical_record_unknown", eng_f.risk_flags)
        self.assertIn("medical_record_unknown", eng_b.risk_flags)
        self.assertGreater(risk_f, risk_b)  # foreign not docked for missing HK medical

        conf_f, _, _ = eng_f._confidence_score(neutral)
        self.assertGreaterEqual(conf_f, 60.0)  # not structurally low-confidence

    def test_confidence_does_not_create_trainer_signal_edge(self) -> None:
        low_confidence = {
            "form_score": 60,
            "speed_score": 60,
            "class_score": 60,
            "jockey_score": 60,
            "trainer_score": 60,
            "draw_score": 50,
            "distance_score": 60,
            "track_going_score": 60,
            "weight_score": 64,
            "consistency_score": 60,
            "risk_score": 60,
            "confidence_score": 40,
        }
        high_confidence = {**low_confidence, "confidence_score": 90}
        inside_draw = {**low_confidence, "draw_score": 75}

        low_scores = map_features_to_matrix_scores(low_confidence)
        high_scores = map_features_to_matrix_scores(high_confidence)
        inside_scores = map_features_to_matrix_scores(inside_draw)

        self.assertEqual(low_scores["trainer_signal"], high_scores["trainer_signal"])
        self.assertGreater(inside_scores["race_shape"], low_scores["race_shape"])
        self.assertEqual(inside_scores["race_shape"], 75.0)

    def test_stability_uses_trackwork_trend_instead_of_confidence(self) -> None:
        base = {
            "form_score": 70,
            "speed_score": 60,
            "class_score": 60,
            "jockey_score": 60,
            "trainer_score": 60,
            "draw_score": 60,
            "distance_score": 60,
            "track_going_score": 60,
            "weight_score": 60,
            "consistency_score": 70,
            "risk_score": 60,
            "confidence_score": 40,
            "trackwork_trend_score": 52,
            "formline_strength_score": 60,
            "margin_trend_score": 60,
        }
        high_confidence = {**base, "confidence_score": 90}
        stronger_trackwork = {**base, "trackwork_trend_score": 70}

        base_scores = map_features_to_matrix_scores(base)
        high_confidence_scores = map_features_to_matrix_scores(high_confidence)
        stronger_trackwork_scores = map_features_to_matrix_scores(stronger_trackwork)

        self.assertEqual(base_scores["stability"], high_confidence_scores["stability"])
        self.assertGreater(stronger_trackwork_scores["stability"], base_scores["stability"])

    def test_form_line_uses_formline_strength_and_margin_trend(self) -> None:
        weak_line = {
            "form_score": 85,
            "speed_score": 60,
            "class_score": 60,
            "jockey_score": 60,
            "trainer_score": 60,
            "draw_score": 60,
            "distance_score": 60,
            "track_going_score": 60,
            "weight_score": 60,
            "consistency_score": 85,
            "risk_score": 60,
            "confidence_score": 60,
            "formline_strength_score": 54,
            "margin_trend_score": 48,
            "same_distance_signal_score": 54,
        }
        strong_line = {
            **weak_line,
            "formline_strength_score": 88,
            "margin_trend_score": 76,
            "same_distance_signal_score": 72,
        }

        weak_scores = map_features_to_matrix_scores(weak_line)
        strong_scores = map_features_to_matrix_scores(strong_line)

        self.assertGreater(strong_scores["form_line"], weak_scores["form_line"])
        self.assertEqual(weak_scores["stability"], strong_scores["stability"])
        same_distance_only = {**weak_line, "same_distance_signal_score": 90}
        self.assertEqual(map_features_to_matrix_scores(same_distance_only)["form_line"], weak_scores["form_line"])

    def test_formline_strength_rewards_higher_class_follow_up_more_than_lower_class(self) -> None:
        base_horse = {
            "_data": {
                "formline_strength": "中強 (強組比例: 4/10)",
            }
        }
        high_follow_up = {
            "_data": {
                "formline_strength": "中強 (強組比例: 4/10)",
                "formline_higher_win_count": 2,
                "formline_same_win_count": 0,
                "formline_lower_win_count": 0,
            }
        }
        low_follow_up = {
            "_data": {
                "formline_strength": "中強 (強組比例: 4/10)",
                "formline_higher_win_count": 0,
                "formline_same_win_count": 0,
                "formline_lower_win_count": 2,
            }
        }

        base_score, _, _ = RacingEngine(base_horse, {}). _formline_strength_score()
        high_score, _, _ = RacingEngine(high_follow_up, {}). _formline_strength_score()
        low_score, _, _ = RacingEngine(low_follow_up, {}). _formline_strength_score()

        self.assertGreater(high_score, base_score)
        self.assertLess(low_score, high_score)

    def test_sectional_uses_recalibrated_speed_and_going_mix(self) -> None:
        features = {
            "form_score": 60,
            "speed_score": 80,
            "class_score": 60,
            "jockey_score": 60,
            "trainer_score": 60,
            "draw_score": 60,
            "distance_score": 60,
            "track_going_score": 60,
            "weight_score": 60,
            "consistency_score": 60,
            "risk_score": 60,
            "confidence_score": 60,
            "formline_strength_score": 60,
            "margin_trend_score": 60,
        }

        scores = map_features_to_matrix_scores(features)

        self.assertEqual(scores["sectional"], 73.0)

    def test_horse_health_matrix_embeds_health_only_v2(self) -> None:
        steady = {
            "horse_name": "測試穩定",
            "jockey": "普通騎師",
            "trainer": "普通練馬師",
            "weight": "126",
            "barrier": "6",
            "last_6_finishes": "4-4-4-4-4-4",
            "season_stats": "季內 (0-0-0-6)",
            "days_since_last": "21",
            "_data": {
                "trackwork_digest": "晨操正常。",
                "trackwork_health": "active_days=18, blank_days=3, swimming=10, aqua_walker=0, risk_flags=[]",
                "medical_flags": "✅ 無醫療事故記錄",
                "weight_trend": "1120→1122→1121→1123 → 📈微增 (波幅3lb)",
            },
        }
        volatile = {
            **steady,
            "horse_name": "測試波動",
            "days_since_last": "8",
            "_data": {
                **steady["_data"],
                "weight_trend": "1120→1140→1116→1148 → 📉大減 (波幅32lb)",
            },
        }

        steady_result = RacingEngine(steady, {"distance": "1650m"}).analyze_horse()
        volatile_result = RacingEngine(volatile, {"distance": "1650m"}).analyze_horse()

        self.assertGreater(
            steady_result["matrix_scores"]["horse_health"],
            volatile_result["matrix_scores"]["horse_health"],
        )

    def test_health_context_gives_partial_credit_when_issue_has_recovery_evidence(self) -> None:
        recovering = {
            "horse_name": "測試回勇",
            "jockey": "普通騎師",
            "trainer": "普通練馬師",
            "weight": "126",
            "barrier": "6",
            "last_6_finishes": "2-5-6-7-8-9",
            "season_stats": "季內 (0-1-0-6)",
            "days_since_last": "18",
            "_data": {
                "trackwork_digest": "晨操正常。",
                "trackwork_health": "active_days=18, blank_days=2, swimming=8, aqua_walker=0, risk_flags=[]",
                "medical_flags": "曾有血液異常，已復課",
                "weight_trend": "1120→1122→1121 → 📈微增 (波幅2lb)",
                "raw_l400": "23.20",
            },
        }
        unresolved = {
            **recovering,
            "horse_name": "測試未回",
            "last_6_finishes": "8-9-10-11-8-9",
            "_data": {
                **recovering["_data"],
                "raw_l400": "24.80",
            },
        }

        recovering_result = RacingEngine(recovering, {"distance": "1400m"}).analyze_horse()
        unresolved_result = RacingEngine(unresolved, {"distance": "1400m"}).analyze_horse()

        self.assertGreater(
            recovering_result["feature_scores"]["risk_score"],
            unresolved_result["feature_scores"]["risk_score"],
        )

    def test_trainer_signal_matrix_embeds_trainer_signal_v3(self) -> None:
        neutral = {
            "horse_name": "測試中性",
            "jockey": "普通騎師",
            "trainer": "普通練馬師",
            "weight": "126",
            "barrier": "6",
            "last_6_finishes": "4-4-4-4-4-4",
            "season_stats": "季內 (0-0-0-6)",
            "_data": {
                "trackwork_digest": "晨操正常。",
                "trackwork_trainer": "賽日騎師沒有直接參與操練；操練者身份：助手3次。操練配備：B/TT；備戰分60。",
            },
        }
        supported = {
            **neutral,
            "horse_name": "測試支持",
            "jockey": "田泰安",
            "trainer": "蔡約翰",
            "_data": {
                **neutral["_data"],
                "trackwork_trainer": "賽日騎師有直接參與操練；操練者身份：助手3次、田泰安1次。操練配備：B/TT；備戰分75。",
                "jockey_combo_block": "人馬組合統計 [V5.1]:**\n  今場騎師: 田泰安\n  📊 騎師×此馬歷史:\n  | 騎師 | 場次 | 勝 | 入Q | 上名 | 平均名次 | 勝率 | 位率 |\n  |------|------|---|-----|------|----------|------|------|\n  | 田泰安 ← 今場 | 3 | 1 | 1 | 2 | 3.0 | 33.3% | 66.7% |\n",
                "jockey_trainer_combo_prior": {
                    "starts": 85.0,
                    "wins": 9.0,
                    "places": 25.0,
                    "win_rate": 10.59,
                    "place_rate": 29.41,
                },
            },
        }

        neutral_result = RacingEngine(neutral, {"distance": "1650m"}).analyze_horse()
        supported_result = RacingEngine(supported, {"distance": "1650m"}).analyze_horse()

        self.assertGreater(
            supported_result["matrix_scores"]["trainer_signal"],
            neutral_result["matrix_scores"]["trainer_signal"],
        )

    def test_distance_score_does_not_treat_untried_trip_as_proven(self) -> None:
        horse = {
            "horse_name": "測試丙",
            "jockey": "普通騎師",
            "trainer": "普通練馬師",
            "weight": "126",
            "barrier": "6",
            "last_6_finishes": "3-3-4-5-6-7",
            "season_stats": "季內 (1-1-0-6) | 同程 (0-0-0-0)",
            "_data": {
                "best_distance": "1200m | 今仗 1650m = 未跑過，但有相近上名經驗 (1600m)",
                "trackwork_digest": "晨操正常。",
            },
        }

        result = RacingEngine(horse, {"distance": "1650m"}).analyze_horse()

        self.assertEqual(result["feature_scores"]["distance_score"], 62.0)
        self.assertNotIn("distance_score", [item["key"] for item in result["matrix_reasoning"]["class_advantage"]["components"]])
        self.assertEqual(result["matrix_reasoning"]["race_shape"]["components"][0]["key"], "race_shape_context_score")
        self.assertEqual(len(result["matrix_reasoning"]["race_shape"]["components"]), 1)

    def test_trackwork_parser_separates_sectionals_from_total_time(self) -> None:
        parsed = extract_trackwork.parse_work_times("28.6 24.5 (53.1) (巫顯東)")
        self.assertEqual(parsed["sectionals"], [28.6, 24.5])
        self.assertEqual(parsed["final_time"], 53.1)

    def test_speed_score_ignores_parenthesized_total_time(self) -> None:
        horse = {
            "trackwork": {
                "entries": [
                    {
                        "type": "gallop",
                        "details": "28.6 24.5 (53.1) (巫顯東)",
                        "times": [28.6, 24.5, 53.1],
                    }
                ]
            }
        }
        score, reason = SpeedScorer(horse, {}).compute()
        self.assertEqual(score, 60.0)
        self.assertEqual(reason, "Sectional data incomplete")

    def test_speed_score_does_not_convert_total_time_to_fake_elite_split(self) -> None:
        horse = {
            "trackwork": {
                "entries": [
                    {
                        "type": "gallop",
                        "details": "27.7 29.4 24.6 (1.21.7) (助手)",
                        "times": [27.7, 29.4, 24.6, 21.7],
                    }
                ]
            }
        }
        score, reason = SpeedScorer(horse, {}).compute()
        self.assertEqual(score, 60.0)
        self.assertEqual(reason, "Sectional data incomplete")

    def test_speed_score_uses_race_sectional_signals(self) -> None:
        horse = {
            "_data": {
                "raw_l400": "23.17",
                "finish_time_adj_level": "✅ 步速修正後仍具競爭力 (近 3 仗修正平均: +0.26s)",
                "energy_trend": "103→100→100→102→102→102 → 趨勢: 穩定",
                "l400_trend": "23.17→23.55→22.42→22.22→23.04→23.50 → 趨勢: 波動",
                "engine_type": "漸進加速型 | 信心: 中 | 依據: 近6場全段速剖面 3/6 場漸進加速型",
                "best_distance": "1650m | 今仗 1650m = 同程適配",
            }
        }
        score, reason = SpeedScorer(horse, {"distance": "1650m"}).compute()
        self.assertAlmostEqual(score, 75.86, places=2)
        self.assertIn("Positive race sectional profile", reason)
        self.assertIn("L400=23.17", reason)

    def test_orchestrator_writes_analysis_csv_and_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            logic_path = folder / "Race_1_Logic.json"
            logic_path.write_text(json.dumps(_logic(), ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(folder)],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue((folder / "Race_1_Auto_Analysis.md").exists())
            self.assertTrue((folder / "Race_1_Auto_Scoring.csv").exists())
            self.assertTrue((folder / "HKJC_Auto_Scoring.csv").exists())
            updated = json.loads(logic_path.read_text(encoding="utf-8"))
            self.assertIn("python_auto_verdict", updated)
            auto = updated["horses"]["1"]["python_auto"]
            self.assertEqual(auto["version"], "HKJC_AUTO_SCORE_V2")
            self.assertEqual(len(auto["feature_scores"]), 12)
            self.assertIn("matrix_scores", auto)
            self.assertIn("matrix_reasoning", auto)
            self.assertIn("core_logic", auto)
            self.assertNotIn("|", auto["core_logic"])
            self.assertNotIn("主要支持位係", auto["core_logic"])
            self.assertTrue(auto["core_logic"].strip())
            self.assertTrue(len(auto["core_logic"]) > 50)  # Check that it generated a substantial paragraph
            self.assertNotIn("近績欄顯示近跑為", auto["core_logic"])
            self.assertNotIn("近21日快操", auto["core_logic"])
            self.assertIn("狀態", auto["matrix_reasoning"]["stability"]["text"])
            self.assertEqual(auto["matrix_reasoning"]["stability"]["components"][2]["key"], "trackwork_trend_score")
            report = (folder / "Race_1_Auto_Analysis.md").read_text(encoding="utf-8")
            self.assertIn("## [第一部分] 🗺️ 戰場全景", report)
            self.assertIn("#### [第二部分] 全場馬匹深度分析", report)
            self.assertIn("#### [第三部分] 最終預測 (The Verdict)", report)
            self.assertIn("#### [第四部分] 分析盲區(緊隨第三部分)", report)
            self.assertIn("綜合戰力分", report)
            self.assertIn("評分構成", report)
            self.assertNotIn("近績欄顯示近跑為", report)
            self.assertNotIn("季內/同程資料顯示", report)
            self.assertNotIn("近績排序為", report)
            self.assertNotIn("由相關 12 項分數映射", report)
            self.assertNotIn("能力分", report)
            self.assertNotIn("- **模型狀態:** 不選", report)
            self.assertNotIn("**模型狀態:** `不選`", report)
            self.assertIn("近3-5仗走位窗口", report)
            self.assertIn("晨操部署", report)
            self.assertIn("休賽 / 體重趨勢", report)
            self.assertIn("班次 / 評分背景", report)
            self.assertNotIn("`✅`", report)
            self.assertNotIn("`❌`", report)
            self.assertNotIn("[FILL", report)

    def test_hv_middle_distance_shadow_watch_is_rendered_without_reordering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            logic_path = folder / "Race_4_Logic.json"
            logic = _logic()
            logic["race_analysis"] = {"race_number": 4, "race_class": "第四班", "distance": "1650", "venue": "跑馬地"}

            logic["horses"]["1"]["jockey"] = "普通騎師"
            logic["horses"]["1"]["trainer"] = "普通練馬師"
            logic["horses"]["1"]["season_stats"] = "季內 (0-0-1-6)"
            logic["horses"]["1"]["last_6_finishes"] = "1-9-6-6-3-9"
            logic["horses"]["1"]["_data"]["trackwork_digest"] = "晨操資料已提取，分類為「狀態延續」。近21日快操4課、踱步11課、游水17課，空白日2日；操練趨勢穩定。正面訊號：操練穩定持續。"
            logic["horses"]["1"]["_data"]["trackwork_health"] = "active_days=19, blank_days=2, swimming=17, aqua_walker=0, risk_flags=[]"
            logic["horses"]["1"]["_data"]["best_distance"] = "1800m | 今仗 1650m = 1場 (0-0-1)"
            logic["horses"]["1"]["_data"]["draw_position_fit"] = "走內(1-2W):2場 平均名次4.5 上名1次 | 偏好: 明顯走內有利 | 今仗檔2=內檔 → ✅匹配走內偏好"
            logic["horses"]["1"]["_data"]["draw_verdict"] = "⚠️中性 (上名25.0%/入Q19.0%/勝6.0%)"
            logic["horses"]["1"]["_data"]["position_pi"] = "[+0, +5, +5, +5, +11] → 趨勢: 衰退中 ⚠️"
            logic["horses"]["1"]["_data"]["last_finish"] = "1"
            logic["horses"]["1"]["_data"]["last_margin"] = "2-1/2"
            logic["horses"]["1"]["_data"]["margin_trend"] = "2-1/2→4-1/2→4-3/4→1-1/2→2-3/4→3-1/2 → 📉擴大中"
            logic["horses"]["1"]["_data"]["medical_flags"] = "✅ 無醫療事故記錄"

            logic["horses"]["3"] = {
                "horse_name": "強勢甲",
                "jockey": "潘頓",
                "trainer": "蔡約翰",
                "weight": "121",
                "barrier": "1",
                "last_6_finishes": "1-1-2-2-3-3",
                "season_stats": "季內 (2-2-1-6)",
                "trackwork": {},
                "_data": {
                    "trackwork_digest": "晨操資料已提取，分類為「狀態延續」。近21日快操5課、踱步18課、游水18課，空白日1日；操練趨勢加強中。",
                    "recent_6_detail": "第1仗: 1名 | 第2仗: 1名 | 第3仗: 2名",
                    "margin_trend": "1/2→1/2→3/4 → 📈收窄中",
                    "engine_type": "漸進加速型 | 信心: 高",
                    "best_distance": "1650m | 今仗 1650m = 5場 (2-2-1)",
                    "raw_l400": "22.80",
                    "l400_trend": "22.80→22.90→23.00 → 趨勢: 穩定",
                    "energy_trend": "95→96→97 → 趨勢: 上升 ✅",
                    "finish_time_adj_level": "✅ 步速修正後仍具競爭力 (近 3 仗修正平均: +0.02s)",
                    "position_window": "第1仗: 沿途位=4-4-1, XW=(1W1W), 消耗=低消耗",
                    "draw_verdict": "✅有利 (上名35.0%/入Q24.0%/勝15.0%)",
                    "running_style": "跟前 | 信心: 高",
                    "position_pi": "[+2, +2, +3] → 趨勢: 上升軌 ✅",
                    "draw_position_fit": "走內(1-2W):5場 平均名次2.0 上名4次 | 今仗檔1=內檔 → ✅匹配走內偏好",
                    "trackwork_trainer": "備戰分80。",
                    "trackwork_health": "active_days=20, blank_days=1, swimming=18, aqua_walker=2, risk_flags=[]",
                    "medical_flags": "✅ 無醫療事故記錄",
                    "formline_strength": "中強 (強組比例: 4/10)",
                    "last_finish": "1",
                    "last_margin": "1/2",
                    "total_starts": 20,
                    "total_wins": 4,
                    "rating_trend": "60→60→59→58 → 穩定",
                    "weight_carried": 121,
                },
            }
            logic["horses"]["4"] = {
                "horse_name": "強勢乙",
                "jockey": "布文",
                "trainer": "韋達",
                "weight": "122",
                "barrier": "3",
                "last_6_finishes": "2-2-1-4-3-2",
                "season_stats": "季內 (1-2-1-6)",
                "trackwork": {},
                "_data": {
                    "trackwork_digest": "晨操資料已提取，分類為「狀態延續」。近21日快操4課、踱步16課、游水16課，空白日1日；操練趨勢穩定。",
                    "recent_6_detail": "第1仗: 2名 | 第2仗: 2名 | 第3仗: 1名",
                    "margin_trend": "1/2→1→3/4 → 📈收窄中",
                    "engine_type": "漸進加速型 | 信心: 高",
                    "best_distance": "1650m | 今仗 1650m = 4場 (1-2-1)",
                    "raw_l400": "23.05",
                    "l400_trend": "23.05→23.10→23.20 → 趨勢: 穩定",
                    "energy_trend": "93→94→95 → 趨勢: 上升 ✅",
                    "finish_time_adj_level": "✅ 步速修正後仍具競爭力 (近 3 仗修正平均: +0.10s)",
                    "position_window": "第1仗: 沿途位=5-5-2, XW=(1W1W), 消耗=低消耗",
                    "draw_verdict": "✅有利 (上名30.0%/入Q22.0%/勝12.0%)",
                    "running_style": "跟前 | 信心: 中",
                    "position_pi": "[+1, +2, +2] → 趨勢: 上升軌 ✅",
                    "draw_position_fit": "走內(1-2W):4場 平均名次2.5 上名3次 | 今仗檔3=內檔 → ✅匹配走內偏好",
                    "trackwork_trainer": "備戰分75。",
                    "trackwork_health": "active_days=19, blank_days=1, swimming=16, aqua_walker=1, risk_flags=[]",
                    "medical_flags": "✅ 無醫療事故記錄",
                    "formline_strength": "中強 (強組比例: 3/10)",
                    "last_finish": "2",
                    "last_margin": "1/2",
                    "total_starts": 18,
                    "total_wins": 3,
                    "rating_trend": "58→57→56→56 → 穩定",
                    "weight_carried": 122,
                },
            }
            logic_path.write_text(json.dumps(logic, ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(folder)],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            updated = json.loads(logic_path.read_text(encoding="utf-8"))
            auto = updated["horses"]["1"]["python_auto"]
            self.assertEqual(auto["rank"], 3)
            self.assertEqual(auto["shadow_flags"][0]["code"], "HV_MID_LAST_START_WINNER")
            verdict = updated["python_auto_verdict"]
            self.assertEqual(verdict["top4"][2]["horse_name"], "測試甲")
            self.assertTrue(any(item["horse_name"] == "測試甲" for item in verdict["shadow_watch"]))
            report = (folder / "Race_4_Auto_Analysis.md").read_text(encoding="utf-8")
            self.assertIn("影子觀察名單", report)
            self.assertIn("跑馬地中距離上仗交代型", report)
            self.assertIn("[1] 測試甲", report)
            race_csv = (folder / "Race_4_Auto_Scoring.csv").read_text(encoding="utf-8")
            rows = list(csv.DictReader(io.StringIO(race_csv)))
            target = next(row for row in rows if row["horse_name"] == "測試甲")
            self.assertEqual(target["shadow_flag_labels"], "跑馬地中距離上仗交代型")
            self.assertIn("上仗已有交代", target["shadow_flag_reasons"])

    def test_validate_engine_flag_runs_real_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            logic_path = folder / "Race_1_Logic.json"
            logic_path.write_text(json.dumps(_logic(), ensure_ascii=False), encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(folder), "--validate-engine"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("Engine validation passed", result.stdout)

    def test_meeting_run_emits_observability_log_and_evaluation_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            logic_path = folder / "Race_1_Logic.json"
            facts_path = folder / "05-13 Race 1 Facts.md"
            results_path = folder / "05-13 測試 全日賽果.json"
            logic_path.write_text(json.dumps(_logic(), ensure_ascii=False), encoding="utf-8")
            facts_path.write_text(
                "\n".join(
                    [
                        "### 馬號 1 — 測試甲 | 騎師: 潘頓 | 練馬師: 蔡約翰 | 負磅: 126 | 檔位: 2",
                        "### 馬號 2 — 測試乙 | 騎師: 普通騎師 | 練馬師: 普通練馬師 | 負磅: 133 | 檔位: 12",
                    ]
                ),
                encoding="utf-8",
            )
            results_path.write_text(
                json.dumps(
                    {
                        "1": {
                            "results": [
                                {"pos": 1, "horse_no": 1, "horse_name": "測試甲"},
                                {"pos": 2, "horse_no": 2, "horse_name": "測試乙"},
                                {"pos": 3, "horse_no": 3, "horse_name": "後備丙"},
                            ]
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(folder), "--scoring-profile", "class_form_combined"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            log_path = folder / "racing_run_log.jsonl"
            self.assertTrue(log_path.exists())
            records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
            event_types = {record["event_type"] for record in records}
            self.assertIn("run_started", event_types)
            self.assertIn("horse_scored", event_types)
            self.assertIn("evaluation_completed", event_types)
            horse_records = [record for record in records if record["event_type"] == "horse_scored"]
            self.assertEqual(len(horse_records), 2)
            evaluation_summary = folder / "evaluation_summary.json"
            self.assertTrue(evaluation_summary.exists())
            summary = json.loads(evaluation_summary.read_text(encoding="utf-8"))
            self.assertEqual(summary["scoring_profile"], "class_form_combined")
            self.assertIn("gold", summary["kpis"])

    def test_consistency_shadow_profile_is_written_without_changing_mainline_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            logic_path = folder / "Race_1_Logic.json"
            results_path = folder / "05-13 測試 全日賽果.json"
            logic = _logic()
            logic["horses"]["1"]["_data"]["recent_6_detail"] = "第1仗: 4名 1-1/4 | 第2仗: 4名 1-1/2 | 第3仗: 5名 2-1/4 | 第4仗: 9名 8-1/2 | 第5仗: 10名 10 | 第6仗: 11名 12"
            logic["horses"]["1"]["_data"]["margin_trend"] = "1-1/4→1-1/2→2-1/4→8-1/2→10→12 → 📈收窄中"
            logic_path.write_text(json.dumps(logic, ensure_ascii=False), encoding="utf-8")
            results_path.write_text(
                json.dumps(
                    {
                        "1": {
                            "results": [
                                {"pos": 1, "horse_no": 1, "horse_name": "測試甲"},
                                {"pos": 2, "horse_no": 2, "horse_name": "測試乙"},
                                {"pos": 3, "horse_no": 3, "horse_name": "後備丙"},
                            ]
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(folder),
                    "--scoring-profile",
                    "consistency_context_shadow",
                    "--shadow-profile",
                    "consistency_context",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            updated = json.loads(logic_path.read_text(encoding="utf-8"))
            auto = updated["horses"]["1"]["python_auto"]
            self.assertIn("shadow_profiles", auto)
            self.assertIn("consistency_context", auto["shadow_profiles"])
            shadow = auto["shadow_profiles"]["consistency_context"]
            self.assertIn("ability_score", shadow)
            self.assertIn("rank", shadow)
            self.assertIn("rank_delta", shadow)
            self.assertIn("python_auto_shadow_verdicts", updated)
            self.assertIn("consistency_context", updated["python_auto_shadow_verdicts"])

            summary = json.loads((folder / "evaluation_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["shadow_profile"], "consistency_context")
            self.assertIn("shadow_profiles", summary)
            self.assertIn("consistency_context", summary["shadow_profiles"])

            race_csv = (folder / "Race_1_Auto_Scoring.csv").read_text(encoding="utf-8")
            rows = list(csv.DictReader(io.StringIO(race_csv)))
            target = next(row for row in rows if row["horse_name"] == "測試甲")
            self.assertIn("shadow_consistency_rank", target)
            self.assertIn("shadow_consistency_ability", target)
            self.assertIn("shadow_consistency_delta", target)

            report = (folder / "Race_1_Auto_Analysis.md").read_text(encoding="utf-8")
            self.assertIn("Consistency Shadow Top 4", report)
            self.assertIn("Consistency Shadow", report)


if __name__ == "__main__":
    unittest.main()
