from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[5]
AUTO_SCRIPT_DIR = (
    ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi_auto" / "scripts"
)
ENGINE_DIR = AUTO_SCRIPT_DIR / "racing_engine"
MAIN_SCRIPT_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi" / "scripts"
REFLECTOR_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"
for path in (AUTO_SCRIPT_DIR, ENGINE_DIR, MAIN_SCRIPT_DIR, REFLECTOR_DIR):
    sys.path.insert(0, str(path))

import create_hkjc_logic_skeleton as skeleton
import hkjc_auto_orchestrator as auto
import hkjc_orchestrator as main
import live_priors
import rescore_backtest
import review_auto_weighting
from engine_core import RacingEngine
from renderer import _shadow_flag_candidates, render_race_csv


def _minimal_logic() -> dict:
    return {
        "race_analysis": {
            "race_number": 1,
            "race_class": "第四班",
            "venue": "跑馬地",
            "distance": "1200",
        },
        "horses": {
            "1": {
                "horse_name": "測試甲",
                "jockey": "潘頓",
                "trainer": "蔡約翰",
                "weight": "126",
                "barrier": "2",
                "last_6_finishes": "1-2-3",
                "season_stats": "季內 (1-1-1-3)",
                "trackwork": {},
                "_data": {},
            }
        },
    }


class PipelineIntegrityTests(unittest.TestCase):
    def test_full_race_builder_strips_retired_llm_scaffold(self) -> None:
        legacy = {
            "horse_name": "測試甲",
            "_data": {"raw_l400": "23.1"},
            "matrix": {"stability": {"score": "[FILL]"}},
            "fine_tune": {"trigger": "[FILL]"},
            "core_logic": "[FILL]",
        }
        with mock.patch.object(
            skeleton,
            "build_horse_skeleton_from_facts",
            return_value=(legacy, {"name": "測試甲"}, {}),
        ):
            logic, _summaries = skeleton.build_full_logic_from_facts(
                "", "Facts.md", 1, [1]
            )
        self.assertEqual(logic["logic_profile"], "AUTO_MINIMAL_V1")
        self.assertEqual(logic["horses"]["1"]["_data"]["raw_l400"], "23.1")
        self.assertNotIn("[FILL", json.dumps(logic, ensure_ascii=False))

    def test_full_race_builder_parses_race_header_once(self) -> None:
        facts = (
            "場地: 跑馬地 | 距離: 1200m | 班次: C4\n"
            "### 馬號 1 — 測試甲 | 騎師: 潘頓 | 練馬師: 蔡約翰"
            " | 負磅: 126 | 檔位: 2\n"
        )
        with (
            mock.patch.object(
                skeleton,
                "build_horse_skeleton_from_facts",
                return_value=({"horse_name": "測試甲", "_data": {}}, {}, {}),
            ) as build_horse,
            mock.patch.object(
                skeleton,
                "extract_race_header",
                wraps=skeleton.extract_race_header,
            ) as parse_header,
        ):
            skeleton.build_full_logic_from_facts(facts, "Facts.md", 1, [1])
        self.assertEqual(parse_header.call_count, 1)
        self.assertEqual(
            build_horse.call_args.kwargs["race_header"]["venue"],
            "跑馬地",
        )

    def test_trackwork_json_is_parsed_once_per_file_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            facts = folder / "07-15 Race 1 Facts.md"
            facts.write_text("facts", encoding="utf-8")
            trackwork = folder / "07-15 Race 1 晨操.json"
            trackwork.write_text(
                json.dumps(
                    {
                        "horses": {
                            "1": {"horse_name": "馬一", "entries": []},
                            "2": {"horse_name": "馬二", "entries": []},
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            skeleton._read_json_cached.cache_clear()
            first = skeleton.load_trackwork_for_horse(
                facts, 1, 1, horse_name="馬一"
            )
            second = skeleton.load_trackwork_for_horse(
                facts, 1, 2, horse_name="馬二"
            )
            cache = skeleton._read_json_cached.cache_info()
            self.assertEqual((cache.misses, cache.hits), (1, 1))
            first["horse_name"] = "已修改"
            self.assertEqual(second["horse_name"], "馬二")

    def test_cloud_placeholder_prior_is_not_opened(self) -> None:
        path = Path("/virtual/cloud-placeholder.csv")
        with (
            mock.patch.object(live_priors, "_is_materialized_file", return_value=False),
            mock.patch.object(live_priors.pd, "read_csv") as read_csv,
        ):
            self.assertIsNone(live_priors._read_prior_csv(path, ("Starts",)))
            read_csv.assert_not_called()

    def test_race_files_use_numeric_order(self) -> None:
        paths = [Path("Race_10_Logic.json"), Path("Race_2_Logic.json"), Path("Race_1_Logic.json")]
        self.assertEqual(
            [path.name for path in sorted(paths, key=auto._race_file_sort_key)],
            ["Race_1_Logic.json", "Race_2_Logic.json", "Race_10_Logic.json"],
        )

    def test_facts_files_use_numeric_order_and_reject_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for race_number in (10, 2, 1):
                (folder / f"07-15 Race {race_number} Facts.md").write_text(
                    "facts", encoding="utf-8"
                )
            self.assertEqual(
                [race for race, _path in main._iter_facts_files(folder)],
                [1, 2, 10],
            )
            (folder / "copy Race 2 Facts.md").write_text("facts", encoding="utf-8")
            with self.assertRaises(SystemExit):
                main._iter_facts_files(folder)

    def test_auto_rejects_ambiguous_support_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            logic = folder / "Race_1_Logic.json"
            logic.write_text("{}", encoding="utf-8")
            (folder / "a Race 1 Facts.md").write_text("facts", encoding="utf-8")
            (folder / "b Race 1 Facts.md").write_text("facts", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "multiple Facts files"):
                auto._facts_path_for_logic(logic, 1)

    def test_summary_distinguishes_scored_from_evaluated_races(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            runner = auto.HKJCAutoOrchestrator(folder)
            logic = _minimal_logic()
            logic["horses"]["1"]["python_auto"] = {"rank": 1, "ability_score": 60}
            with mock.patch.object(runner, "_load_meeting_results", return_value={}):
                summary = runner._write_evaluation_summary([logic])
            self.assertEqual(summary["race_count"], 1)
            self.assertEqual(summary["evaluated_race_count"], 0)
            self.assertEqual(sum(summary["kpis"].values()), 0)

    def test_racecard_uses_horse_number_when_name_spelling_differs(self) -> None:
        _, metadata = auto._parse_racecard_meta(
            "馬號: 3\n馬名: 官方寫法\n負磅: 126\n騎師: 鍾易禮 (-2)\n"
            "檔位: 7\n練馬師: 測試練馬師\n評分: 67\n評分+/-: -2\n"
        )
        self.assertEqual(metadata["3"]["rating"], 67)
        self.assertEqual(metadata["3"]["change"], -2)
        self.assertEqual(metadata["3"]["jockey"], "鍾易禮")
        self.assertEqual(metadata["3"]["weight"], 124)
        self.assertEqual(metadata["3"]["barrier"], 7)

    def test_facts_header_does_not_inject_second_combo_prior_source(self) -> None:
        horse = _minimal_logic()["horses"]["1"]
        auto._enrich_horse_headers(
            {"1": horse},
            {"1": {"horse_name": "測試甲", "jockey": "潘頓", "trainer": "蔡約翰"}},
        )
        self.assertNotIn("jockey_trainer_combo_prior", horse["_data"])

    def test_same_complete_logic_scores_same_with_header_fallback_present(self) -> None:
        first = _minimal_logic()["horses"]["1"]
        second = copy.deepcopy(first)
        auto._enrich_horse_headers({"1": first}, {})
        auto._enrich_horse_headers(
            {"1": second},
            {"1": {"horse_name": "測試甲", "jockey": "潘頓", "trainer": "蔡約翰"}},
        )
        context = _minimal_logic()["race_analysis"]
        score_a = RacingEngine(first, copy.deepcopy(context)).analyze_horse()["ability_score"]
        score_b = RacingEngine(second, copy.deepcopy(context)).analyze_horse()["ability_score"]
        self.assertEqual(score_a, score_b)

    def test_authoritative_header_overwrites_stale_logic_and_data_copy(self) -> None:
        horse = _minimal_logic()["horses"]["1"]
        horse.update({"jockey": "舊騎師", "trainer": "舊練馬師", "weight": "135"})
        horse["_data"].update(
            {"jockey_name": "更舊騎師", "trainer_name": "更舊練馬師", "weight_carried": 133}
        )
        auto._enrich_horse_headers(
            {"1": horse},
            {"1": {"jockey": "新騎師", "trainer": "新練馬師", "weight": "124"}},
        )
        self.assertEqual(horse["jockey"], "新騎師")
        self.assertEqual(horse["trainer"], "新練馬師")
        self.assertEqual(horse["weight"], "124")
        self.assertEqual(horse["_data"]["jockey_name"], "新騎師")
        self.assertEqual(horse["_data"]["trainer_name"], "新練馬師")
        self.assertEqual(horse["_data"]["weight_carried"], "124")

    def test_alignment_builds_field_names_after_official_racecard_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            logic_path = folder / "Race_1_Logic.json"
            facts = folder / "07-15 Race 1 Facts.md"
            card = folder / "07-15 Race 1 排位表.md"
            facts.write_text(
                "### 馬號 1 — Facts馬名 | 騎師: Facts騎師 | 練馬師: Facts練馬師"
                " | 負磅: 126 | 檔位: 9\n",
                encoding="utf-8",
            )
            card.write_text(
                "班次: 第四班\n馬號: 1\n馬名: 官方馬名\n負磅: 126\n"
                "騎師: 鍾易禮 (-2)\n檔位: 3\n練馬師: 官方練馬師\n評分: 67\n",
                encoding="utf-8",
            )
            logic = _minimal_logic()
            logic["horses"]["1"]["horse_name"] = "舊馬名"
            auto._align_runner_headers(
                logic_path, logic["race_analysis"], logic["horses"]
            )
            horse = logic["horses"]["1"]
            self.assertEqual(horse["horse_name"], "官方馬名")
            self.assertEqual(horse["jockey"], "鍾易禮")
            self.assertEqual(horse["trainer"], "官方練馬師")
            self.assertEqual(horse["weight"], 124)
            self.assertEqual(horse["barrier"], 3)
            self.assertEqual(logic["race_analysis"]["field_horse_names"], ["官方馬名"])

    def test_alignment_rejects_logic_racecard_runner_set_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            logic_path = folder / "Race_1_Logic.json"
            (folder / "07-15 Race 1 排位表.md").write_text(
                "馬號: 1\n馬名: 馬一\n評分: 60\n"
                "馬號: 2\n馬名: 馬二\n評分: 59\n",
                encoding="utf-8",
            )
            logic = _minimal_logic()
            with self.assertRaisesRegex(ValueError, "runner set differs"):
                auto._align_runner_headers(
                    logic_path, logic["race_analysis"], logic["horses"]
                )

    def test_weight_review_uses_live_race_shape_context_feature(self) -> None:
        logic = _minimal_logic()
        horse = logic["horses"]["1"]
        context = logic["race_analysis"]
        live = RacingEngine(copy.deepcopy(horse), copy.deepcopy(context)).analyze_horse()
        reviewed = review_auto_weighting.compute_full_feature_scores(horse, context)
        self.assertEqual(
            reviewed["race_shape_context_score"],
            live["derived_feature_scores"]["race_shape_context_score"],
        )

    def test_reflector_rescore_uses_production_prior_cleanup_and_ranking(self) -> None:
        logic = _minimal_logic()
        logic["horses"]["1"]["_data"]["jockey_trainer_combo_prior"] = {
            "starts": 999,
            "win_rate": 99,
            "place_rate": 99,
        }
        rescored = rescore_backtest.rescore_logic(logic)
        horse = rescored["horses"]["1"]
        self.assertNotIn("jockey_trainer_combo_prior", horse["_data"])
        self.assertEqual(horse["python_auto"]["rank"], 1)

    def test_invalid_scoring_does_not_overwrite_last_good_logic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Race_1_Logic.json"
            original = _minimal_logic()
            path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
            runner = auto.HKJCAutoOrchestrator(path)
            with (
                mock.patch.object(auto, "validate_logic_data", return_value=["forced failure"]),
                mock.patch.object(auto, "_enrich_profile_history"),
            ):
                self.assertIsNone(runner.score_race(path))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), original)

    def test_invalid_report_does_not_overwrite_last_good_logic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Race_1_Logic.json"
            original = _minimal_logic()
            path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
            runner = auto.HKJCAutoOrchestrator(path)
            with (
                mock.patch.object(
                    auto,
                    "prepare_race_outputs",
                    side_effect=ValueError("forced report failure"),
                ),
                mock.patch.object(auto, "_enrich_profile_history"),
            ):
                self.assertIsNone(runner.score_race(path))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), original)

    def test_extra_stale_runner_forces_logic_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            facts = folder / "07-15 Race 1 Facts.md"
            logic = folder / "Race_1_Logic.json"
            facts.write_text("### 馬號 1 — 測試甲\n", encoding="utf-8")
            logic.write_text(
                json.dumps({"horses": {"1": {}, "12": {"horse_name": "已退出"}}}, ensure_ascii=False),
                encoding="utf-8",
            )
            self.assertTrue(main._logic_needs_refresh(facts, logic, [1]))

    def test_newer_racecard_forces_logic_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            facts = folder / "07-15 Race 1 Facts.md"
            card = folder / "07-15 Race 1 排位表.md"
            logic = folder / "Race_1_Logic.json"
            facts.write_text("### 馬號 1 — 測試甲\n", encoding="utf-8")
            card.write_text("馬號: 1\n馬名: 測試甲\n評分: 60\n", encoding="utf-8")
            logic.write_text(
                json.dumps({"horses": {"1": {}}}, ensure_ascii=False),
                encoding="utf-8",
            )
            os.utime(facts, ns=(1_000_000_000, 1_000_000_000))
            os.utime(logic, ns=(2_000_000_000, 2_000_000_000))
            os.utime(card, ns=(3_000_000_000, 3_000_000_000))
            self.assertTrue(main._logic_needs_refresh(facts, logic, [1]))

    def test_validation_rejects_formula_contract_drift(self) -> None:
        logic = _minimal_logic()
        horse = logic["horses"]["1"]
        horse["python_auto"] = RacingEngine(
            horse, logic["race_analysis"]
        ).analyze_horse()
        auto._apply_sip_enhancements(logic["horses"])
        auto.ensure_verdict(logic)
        logic["python_auto_run_contract"] = auto.scoring_run_contract()
        self.assertEqual(auto.validate_logic_data(logic), [])
        logic["python_auto_run_contract"]["matrix_formulas"]["race_shape"][0]["weight"] = 999
        self.assertIn(
            "SCHEMA-009 run contract matrix formulas mismatch",
            auto.validate_logic_data(logic),
        )

    def test_validation_checks_ability_formula_even_with_sip_boost(self) -> None:
        logic = _minimal_logic()
        horse_auto = RacingEngine(
            logic["horses"]["1"], logic["race_analysis"]
        ).analyze_horse()
        base_score = horse_auto["ability_score"]
        horse_auto["sip_flags"] = [
            {"reason": "fixture", "boost": 1.0, "original_score": base_score}
        ]
        horse_auto["ability_score"] = round(base_score + 1.0, 2)
        horse_auto["grade"] = auto.compute_grade(horse_auto["ability_score"])
        logic["horses"]["1"]["python_auto"] = horse_auto
        auto.ensure_verdict(logic)
        logic["python_auto_run_contract"] = auto.scoring_run_contract()
        self.assertNotIn(
            "SCORE-004",
            " ".join(auto.validate_logic_data(logic)),
        )

        horse_auto["ability_score"] = round(horse_auto["ability_score"] + 4.0, 2)
        horse_auto["grade"] = auto.compute_grade(horse_auto["ability_score"])
        auto.ensure_verdict(logic)
        self.assertIn(
            "SCORE-004",
            " ".join(auto.validate_logic_data(logic)),
        )

    def test_shadow_watch_reads_derived_feature_namespace(self) -> None:
        horse = {
            "_data": {
                "best_distance": "今仗 1650m = 相近贏馬經驗",
                "draw_position_fit": "✅匹配",
                "trackwork_digest": "操練穩定",
                "trackwork_health": "正常",
                "last_finish": 1,
            }
        }
        scored = {
            "rank": 3,
            "feature_scores": {"risk_score": 65},
            "derived_feature_scores": {
                "same_distance_signal_score": 50,
                "trackwork_trend_score": 70,
            },
        }
        context = {"venue": "跑馬地", "distance": "1650m"}
        self.assertEqual(_shadow_flag_candidates(horse, context, scored), [])
        scored["derived_feature_scores"]["same_distance_signal_score"] = 60
        self.assertTrue(_shadow_flag_candidates(horse, context, scored))

    def test_scoring_csv_includes_derived_and_matrix_audit_scores(self) -> None:
        logic = _minimal_logic()
        logic["horses"]["1"]["python_auto"] = RacingEngine(
            logic["horses"]["1"], logic["race_analysis"]
        ).analyze_horse()
        header = render_race_csv(logic).splitlines()[0].split(",")
        self.assertIn("race_shape_context_score", header)
        self.assertIn("matrix_race_shape", header)

    def test_profile_history_excludes_same_day_and_future_results(self) -> None:
        horse = _minimal_logic()["horses"]["1"]
        horse["trackwork"] = {"horseid": "HK_2024_A001"}
        entries = [
            {
                "date": "20/07/26",
                "rating": 99,
                "class_grade": "1",
                "placing": 1,
                "jockey": "未來騎師",
                "running_positions": [1, 1, 1],
            },
            {
                "date": "15/07/26",
                "rating": 88,
                "class_grade": "2",
                "placing": 1,
                "jockey": "同日騎師",
                "running_positions": [1, 1, 1],
            },
            {
                "date": "10/07/26",
                "rating": 60,
                "class_grade": "4",
                "placing": 4,
                "jockey": "舊騎師",
                "running_positions": [4, 4, 4],
            },
        ]
        with mock.patch.object(
            auto,
            "_get_profile_scraper",
            return_value=lambda _horse_id: {"entries": entries},
        ):
            auto._enrich_profile_history(
                {"1": horse},
                as_of_date=date(2026, 7, 15),
            )
        self.assertEqual(horse["_data"]["rating_high_3s"], 60)
        self.assertIn("今仗轉用騎師潘頓", horse["_data"]["jockey_change_note"])

    def test_meeting_date_is_inferred_from_archive_folder(self) -> None:
        inferred = auto._meeting_date_for_logic(
            Path("/archive/2026-07-15_HappyValley/Race_1_Logic.json"),
            {},
        )
        self.assertEqual(inferred, date(2026, 7, 15))

    def test_fresh_logic_build_replaces_stale_runner_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            facts = folder / "07-15 Race 1 Facts.md"
            logic = folder / "Race_1_Logic.json"
            facts.write_text("fixture", encoding="utf-8")
            logic.write_text(
                json.dumps({"horses": {"9": {"horse_name": "已退出"}}}, ensure_ascii=False),
                encoding="utf-8",
            )

            def fake_run(cmd, **_kwargs):
                output = Path(cmd[6])
                data = {
                    "horses": {
                        "1": {"horse_name": "馬1"},
                        "2": {"horse_name": "馬2"},
                    }
                }
                output.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            with mock.patch.object(main.subprocess, "run", side_effect=fake_run):
                result = main._generate_logic_for_race(
                    1, facts, [1, 2], logic, stream=False
                )

            self.assertEqual(result["returncode"], 0)
            self.assertEqual(set(json.loads(logic.read_text(encoding="utf-8"))["horses"]), {"1", "2"})


if __name__ == "__main__":
    unittest.main()
