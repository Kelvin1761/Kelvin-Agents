from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"
SHARED_SCRIPTS = ROOT / ".agents" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SHARED_SCRIPTS))

from au_auto_orchestrator import _facts_path_for_logic
import build_au_logic
from au_racing_engine.engine_core import RacingEngine, enrich_logic_from_facts, _extract_career_starts
from inject_fact_anchors import (
    _enrich_stats_from_formguide,
    _history_kind_label,
    parse_formguide_for_horse,
    parse_racecard,
)

MODERN_FACTS = "\n".join(
    [
        "## Race 3",
        "### 馬匹 #7 Example Star (檔位 4) | 騎師: J Doe | 練馬師: T Smith",
        "- **🔗 賽績線**",
        "| 日期 | 賽事 | 名次 | 對手 | 下仗班次 | 對手後續成績 | 強度 |",
        "|---|---|---|---|---|---|---|",
        "| 2026-05-01 | Randwick R5 | 2 | 頭馬: Rival A | Group 3 | 出 2 次: 1 勝 | 強 |",
        "| 1 | 正式 | 2026-05-01 | Randwick | 1400m | Good 4 | 8 | 2 | 升班 | 9-8-2 | 4 | 較快 | Genuine | 34.12 | 後上 | 中等 | Crowded late | 受阻 |",
        "| 2 | 試閘 | 2026-03-28 | Randwick | 1050m | Good 4 | 4 | 1 | Trial | 4-3-1 | 3 | 較快 | Moderate | 33.90 | 跟前 | 低 | - | [-] |",
    ]
)


class FactsPathGlobTests(unittest.TestCase):
    def test_accepts_underscore_and_space_naming(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            logic = folder / "Race_3_Logic.json"
            logic.write_text("{}", encoding="utf-8")

            underscore = folder / "07-15 Race_3_Facts.md"
            underscore.write_text("x", encoding="utf-8")
            self.assertEqual(_facts_path_for_logic(logic, 3), underscore)
            underscore.unlink()

            spaced = folder / "11-01 Race 3 Facts.md"
            spaced.write_text("x", encoding="utf-8")
            self.assertEqual(_facts_path_for_logic(logic, 3), spaced)

    def test_does_not_cross_match_race_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            logic = folder / "Race_1_Logic.json"
            logic.write_text("{}", encoding="utf-8")
            (folder / "11-01 Race 10 Facts.md").write_text("x", encoding="utf-8")
            self.assertIsNone(_facts_path_for_logic(logic, 1))

    def test_ignores_directory_named_like_facts_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            logic = folder / "Race_1_Logic.json"
            logic.write_text("{}", encoding="utf-8")
            (folder / "Race_1_Facts.md").mkdir()
            real_facts = folder / "05-08 Race 1 Facts.md"
            real_facts.write_text("x", encoding="utf-8")
            self.assertEqual(_facts_path_for_logic(logic, 1), real_facts)


class BuilderEnricherParityTests(unittest.TestCase):
    def test_archived_winner_margin_is_zero_when_rebuilding_facts(self) -> None:
        formguide = "\n".join(
            [
                "[4] Example Star (12)",
                "Randwick R5 2026-08-01 1400m cond:Good $100000 J Doe (4) 58kg "
                "margin:5.75L starters:10 finish:1/10",
                "1-Example Star (4), 2-Rival (2) 5.75L",
            ]
        )
        rows = parse_formguide_for_horse(
            formguide, 4, "Example Star", [1], as_of="2026-08-09"
        )
        self.assertEqual(rows[0]["finish_pos"], 1)
        self.assertEqual(rows[0]["margin"], 0.0)

    def test_non_top3_trial_finish_token_is_not_treated_as_no_trial(self) -> None:
        formguide = "\n".join(
            [
                "[4] Example Star (12)",
                "Southside Cranbourne **(TRIAL)** R4 2026-08-01 1000m cond:Good "
                "$0 J Doe (4) 58kg margin:4.18L starters:8 finish:5/8",
                "1-Rival (2), 2-Other (3) 1.0L, 3-Third (1) 2.0L",
            ]
        )
        rows = parse_formguide_for_horse(
            formguide, 4, "Example Star", [], as_of="2026-08-09"
        )
        self.assertTrue(rows[0]["is_trial"])
        self.assertEqual(rows[0]["finish_pos"], 5)
        self.assertEqual(rows[0]["pos_source"], "finish_token")

    def test_sportsbet_exact_race_class_survives_formguide_parse(self) -> None:
        formguide = "\n".join(
            [
                "[4] Example Star (12)",
                "Randwick R5 2026-08-01 1400m cond:Good $100000 J Doe (4) 58kg "
                "margin:1.2L starters:10 finish:3/10 RaceClass:[F&M CL3-SW]",
                "1-Rival (2), 2-Other (3) 0.5L, 3-Example Star (4) 1.2L",
            ]
        )
        rows = parse_formguide_for_horse(
            formguide, 4, "Example Star", [3], as_of="2026-08-09"
        )
        self.assertEqual(rows[0]["source_race_class"], "F&M CL3-SW")

    def test_formguide_dossier_censors_target_and_future_runs(self) -> None:
        formguide = "\n".join(
            [
                "[4] Example Star (12)",
                "Randwick R5 2026-08-09 1400m cond:Good $100,000 J Doe (4) 58kg margin:0 HC:80",
                "1-Example Star (4)",
                "Rosehill R3 2026-08-01 1400m cond:Good $80,000 J Doe (3) 58kg margin:1.2 HC:78",
                "1-Rival (2) 2-Example Star (3) 1.2L",
            ]
        )
        rows = parse_formguide_for_horse(
            formguide,
            4,
            "Example Star",
            [1, 2],
            as_of="2026-08-09",
        )
        self.assertEqual([row["date"] for row in rows], ["2026-08-01"])

    def test_historical_hc_is_not_rendered_as_race_class(self) -> None:
        self.assertEqual(_history_kind_label({"is_trial": False, "hc": 106}), "HC106")
        self.assertEqual(_history_kind_label({"is_trial": False, "hc": None}), "正式")
        self.assertEqual(_history_kind_label({"is_trial": True, "hc": 106}), "試閘")

    def test_engine_keeps_historical_hc_as_rating_evidence(self) -> None:
        facts = "\n".join(
            [
                "| # | 類型／歷史HC | 日期 | 場地 | 路程 | 場地狀況 | 檔位 | 名次 | 班次 | 跑位軌跡 |",
                "|---|---|---|---|---|---|---|---|---|---|",
                "| 1 | HC106 | 2026-05-16 | Doomben R5 | 1600m | 7 | 9 | 4 | = | S4→F4 |",
            ]
        )
        engine = RacingEngine.__new__(RacingEngine)
        engine.facts_section = facts
        engine._record_entry_cache = None
        rows = engine._record_entries()
        self.assertEqual(rows[0]["kind"], "HC106")
        self.assertEqual(rows[0]["historical_rating"], 106.0)

    def test_engine_keeps_exact_class_as_report_only_evidence(self) -> None:
        facts = "\n".join(
            [
                "| # | 類型 | 日期 | 場地 | 路程 | 地 | 檔 | 名次 | 班次 | 軌跡 | PI | 段速 | 早段 | L600 | 跑法 | 消耗 | 備註 | 寬恕 | 獎金 | Sportsbet原始班次 |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
                "| 1 | 正式 | 2026-08-01 | Randwick R5 | 1400m | Good | 4 | 3/10 | = | S4→F3 | 1 | 一般 | - | - | 跟前 | 低 | - | - | 75000 | F&M CL3-SW |",
            ]
        )
        engine = RacingEngine.__new__(RacingEngine)
        engine.facts_section = facts
        engine._record_entry_cache = None
        row = engine._record_entries()[0]
        self.assertEqual(row["source_race_class"], "F&M CL3-SW")
        self.assertNotIn("class", row)

    def test_formguide_record_enrichment_keeps_complete_sportsbet_values(self) -> None:
        horse = {"num": 4}
        formguide = "\n".join(
            [
                "[4] Example Star (12)",
                "Career:    45: 5-7-7       Last 10: 656587",
                "Track:     1: 0-0-0        Distance: 27: 3-5-4       Trk/Dist: 0: 0-0-0",
                "Firm:      0: 0-0-0        Good: 18: 3-2-2       Soft: 20: 1-4-4",
                "Heavy:     7: 1-1-1",
                "1st Up:    9: 2-1-1        2nd Up: 7: 1-1-2",
                "Randwick R5 2026-07-01 1400m cond:Good",
            ]
        )

        _enrich_stats_from_formguide(formguide, horse)

        self.assertEqual(horse["track_stats"], "1:0-0-0")
        self.assertEqual(horse["dist_stats"], "27:3-5-4")
        self.assertEqual(horse["trkdist_stats"], "0:0-0-0")
        self.assertEqual(horse["good_stats"], "18:3-2-2")
        self.assertEqual(horse["soft_stats"], "20:1-4-4")
        self.assertEqual(horse["heavy_stats"], "7:1-1-1")
        self.assertEqual(horse["first_up"], "9:2-1-1")
        self.assertEqual(horse["second_up"], "7:1-1-2")

    def test_partial_record_is_missing_instead_of_cross_contaminating(self) -> None:
        horse = {"num": 4}
        formguide = "\n".join(
            [
                "[4] Example Star (12)",
                "Track: 1: Distance: 27: 3-5-4 Trk/Dist: 0: 0-0-0",
                "Randwick R5 2026-07-01 1400m cond:Good",
            ]
        )

        _enrich_stats_from_formguide(formguide, horse)

        self.assertEqual(horse["track_stats"], "N/A")
        self.assertEqual(horse["dist_stats"], "27:3-5-4")

    def test_engine_record_segments_are_field_aligned(self) -> None:
        engine = RacingEngine.__new__(RacingEngine)
        engine.data = {
            "track_stats_line": "1: | 同程: 27: | 同場同程: 0:",
            "going_stats_line": "18:3-2-2 | 軟地: 20:1-4-4 | 重地: 7:1-1-1",
        }

        self.assertEqual(engine._same_track_stats()["places"], 0)
        going = engine._going_stats()
        self.assertEqual(going["好地"]["starts"], 0)
        self.assertEqual(going["好地"]["places"], 0)
        self.assertEqual(going["軟地"]["places"], 9)
        self.assertEqual(going["重地"]["places"], 3)

    def test_integer_only_sportsbet_career_is_not_debut(self) -> None:
        facts = "\n".join(
            [
                "### 馬匹 #4 Example Star (檔位 2)",
                "  - 生涯: 45",
                "  - 生涯標記: `DEBUT` (生涯 0 場)",
            ]
        )
        self.assertEqual(_extract_career_starts(facts), 45)
        self.assertEqual(build_au_logic._extract_career_starts(facts), 45)
        self.assertEqual(build_au_logic._extract_career_tag(facts), "ESTABLISHED")

    def test_sportsbet_racecard_keeps_full_career_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            racecard = Path(tmp) / "Racecard.md"
            racecard.write_text(
                "\n".join(
                    [
                        "RACE 1 — 1400m",
                        "1. Example Star (3)",
                        (
                            "Trainer: T Smith | Jockey: J Doe | Weight: 58.0kg | "
                            "Age: 5yoG | Rating: 70"
                        ),
                        "Career: 45 : 5-7-7 | Win: 11% | Place: 42%",
                        "----------------------------------------",
                    ]
                ),
                encoding="utf-8",
            )
            horses = parse_racecard(str(racecard))

        self.assertEqual(horses[0]["career"], "45 : 5-7-7")

    def test_racecard_restores_people_missing_from_legacy_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            facts_path = folder / "11-01 Race 3 Facts.md"
            facts_path.write_text(
                "## Race 3\n### 馬匹 #7 Example Star (檔位 4)\n",
                encoding="utf-8",
            )
            (folder / "11-01 Race 3 Racecard.md").write_text(
                "\n".join(
                    [
                        "RACE 3 — 1400m | Maiden",
                        "7. Example Star (4)",
                        "Trainer: T Smith | Jockey: J Doe | Weight: 58.0kg | Age: 5yoG | Rating: 70",
                    ]
                ),
                encoding="utf-8",
            )
            logic = {
                "race_analysis": {"race_number": 3},
                "horses": {
                    "7": {
                        "horse_name": "Example Star",
                        "jockey": "",
                        "trainer": "",
                        "_data": {},
                    }
                },
            }
            enriched = enrich_logic_from_facts(logic, facts_path)

        horse = enriched["horses"]["7"]
        self.assertEqual(horse["jockey"], "J Doe")
        self.assertEqual(horse["trainer"], "T Smith")
        self.assertEqual(horse["rating"], 70.0)

    def test_canonical_builder_is_enrichment_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            facts_path = Path(tmp) / "11-01 Race 3 Facts.md"
            facts_path.write_text(MODERN_FACTS, encoding="utf-8")
            built = build_au_logic.build_logic_from_facts(facts_path)
            enriched = enrich_logic_from_facts(
                copy.deepcopy(built),
                facts_path,
            )
        self.assertEqual(built, enriched)

    def test_track_resources_resolve_from_builder(self) -> None:
        self.assertTrue(build_au_logic.TRACK_RESOURCE_DIR.is_dir())
        profile = build_au_logic._load_track_profile("Warwick Farm", 1100)
        self.assertEqual(profile["venue"], "Warwick Farm")
        self.assertGreater(profile["straight_m"], 0)

    def test_predicted_pace_populates_backward_compatible_alias(self) -> None:
        facts = "\n".join(
            [
                "### 🗺️ 自動步速圖 (Python Facts Model V4)",
                "- **predicted_pace:** 正常",
                "- **pace_confidence:** High",
            ]
        )
        speed_map = build_au_logic._parse_speed_map(facts)
        self.assertEqual(speed_map["predicted_pace"], "正常")
        self.assertEqual(speed_map["expected_pace"], "正常")

    def test_arbitrary_temp_folder_is_not_a_venue(self) -> None:
        self.assertEqual(build_au_logic._venue_from_folder_name("local"), "")
        self.assertEqual(
            build_au_logic._venue_from_folder_name(
                "2026-07-15 Warwick Farm Race 1-7"
            ),
            "Warwick Farm",
        )


class FactsSectionRefreshTests(unittest.TestCase):
    def _enrich(self, logic: dict) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            facts_path = Path(tmp) / "11-01 Race 3 Facts.md"
            facts_path.write_text(MODERN_FACTS, encoding="utf-8")
            return enrich_logic_from_facts(logic, facts_path)

    def test_stale_facts_section_is_replaced_from_facts_file(self) -> None:
        logic = {
            "race_analysis": {"race_number": 3},
            "horses": {
                "7": {
                    "horse_name": "Example Star",
                    "_data": {"facts_section": "OLD PRE-REALIGNMENT BLOB WITHOUT MARKERS"},
                }
            },
        }
        enriched = self._enrich(logic)
        section = enriched["horses"]["7"]["_data"]["facts_section"]
        self.assertIn("賽績線", section)
        self.assertIn("試閘", section)
        self.assertNotIn("OLD PRE-REALIGNMENT BLOB", section)

    def test_stale_facts_scalars_are_replaced_from_matching_horse_block(self) -> None:
        facts = "\n".join(
            [
                "## Race 3",
                "### 馬匹 #7 Example Star (檔位 4) | 騎師: J Doe | 練馬師: T Smith",
                "  - Last 10 字串: `24`",
                "  - 生涯: 2:0-1-0",
                "  - 同場: 2:0-1-0 | 同程: 1:0-1-0 | 同場同程: 1:0-1-0",
                "  - 好地: 1:0-0-0 | 軟地: 1:0-1-0 | 重地: 0:0-0-0",
                "  - 初出: 1:0-0-0 | 二出: 1:0-1-0",
                "| # | 類型 | 日期 | 場地 | 路程 | 場地狀況 | 檔位 | 名次 | 班次 | 跑位軌跡 | PI | 段速 | 早段步速 | L600/RT | 走位跑法 | 走位消耗 | 備註 | 寬恕認定 |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
                "| 1 | Maiden/SW | 2026-05-01 | Randwick | 1400m | Soft 5 | 4 | 2 | ↑升班 | 4-3-2 | 3 | 快 | Moderate | 34.0 | 跟前 | 低 | - | [-] |",
                "| 2 | 試閘 | 2026-04-01 | Randwick | 1050m | Good 4 | 2 | 1 | Trial | 2-1-1 | - | - | - | - | 跟前 | 低 | - | [-] |",
                "- **🔧 引擎與距離:**",
                "  - 引擎: Type A | 信心: 高 | 依據: 正式賽樣本",
                "  - 跑法: 跟前 / 守中 | 信心: 高 | 依據: 兩仗走位",
                "  - 距離分佈: 1400m: 1場 (0-1-0) ← 今仗 ✅",
            ]
        )
        logic = {
            "race_analysis": {"race_number": 3},
            "horses": {
                "7": {
                    "horse_name": "Example Star",
                    "_data": {
                        "last10_raw": "999",
                        "formal_count": 0,
                        "trial_count": 9,
                        "trial_top3_count": 0,
                        "track_stats_line": "0:0-0-0 | 同程: 0:0-0-0 | 同場同程: 0:0-0-0",
                        "going_stats_line": "0:0-0-0 | 軟地: 0:0-0-0 | 重地: 9:9-0-0",
                        "running_style_line": "後上 / 後上",
                        "engine_type_line": "Type C",
                    },
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            facts_path = Path(tmp) / "11-01 Race 3 Facts.md"
            facts_path.write_text(facts, encoding="utf-8")
            enriched = enrich_logic_from_facts(logic, facts_path)

        data = enriched["horses"]["7"]["_data"]
        self.assertEqual(data["last10_raw"], "24")
        self.assertEqual(data["formal_count"], 1)
        self.assertEqual(data["trial_count"], 1)
        self.assertEqual(data["trial_top3_count"], 1)
        self.assertEqual(
            data["track_stats_line"],
            "2:0-1-0 | 同程: 1:0-1-0 | 同場同程: 1:0-1-0",
        )
        self.assertEqual(
            data["going_stats_line"],
            "1:0-0-0 | 軟地: 1:0-1-0 | 重地: 0:0-0-0",
        )
        self.assertEqual(data["running_style_line"], "跟前 / 守中")
        self.assertEqual(data["engine_type_line"], "Type A")

    def test_missing_section_fails_instead_of_scoring_stale_logic(self) -> None:
        logic = {
            "race_analysis": {"race_number": 3},
            "horses": {
                "9": {  # not in the Facts file
                    "horse_name": "Absent Horse",
                    "_data": {"facts_section": "KEEP ME"},
                }
            },
        }
        with self.assertRaisesRegex(ValueError, "FIELD ALIGNMENT FAILED"):
            self._enrich(logic)

    def test_temp_folder_name_cannot_overwrite_existing_venue(self) -> None:
        logic = {
            "race_analysis": {
                "race_number": 3,
                "meeting_intelligence": {
                    "venue": "Warwick Farm",
                    "going": "Soft 5",
                    "source": "Race_3_Logic.json",
                },
            },
            "horses": {
                "7": {"horse_name": "Example Star", "_data": {}},
            },
        }
        enriched = self._enrich(logic)
        meeting = enriched["race_analysis"]["meeting_intelligence"]
        self.assertEqual(meeting["venue"], "Warwick Farm")
        self.assertNotIn("tmp", meeting["venue"].lower())

    def test_stale_pf_payload_is_replaced_by_matching_formguide(self) -> None:
        logic = {
            "race_analysis": {"race_number": 3},
            "horses": {
                "7": {
                    "horse_name": "Example Star",
                    "_data": {
                        "pf_metrics": {
                            "pf_aggregates": {
                                "l600_delta_avg": 9.99,
                                "pf_run_count": 1,
                            }
                        }
                    },
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            facts_path = folder / "11-01 Race 3 Facts.md"
            facts_path.write_text(MODERN_FACTS, encoding="utf-8")
            formguide_path = folder / "11-01 Race 3 Formguide.md"
            formguide_path.write_text(
                "\n".join(
                    [
                        "[7] Example Star (4)",
                        (
                            "Randwick R5 2026-10-01 1400m "
                            "PF[Runner Time: 84.20 Last600: 49.50 "
                            "L600 Delta: -1.25 Early Runner Pace: Moderate. "
                            "Early Race Pace: Fast.]"
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            enriched = enrich_logic_from_facts(logic, facts_path)

        pf = enriched["horses"]["7"]["_data"]["pf_metrics"]
        self.assertEqual(pf["pf_aggregates"]["source"], "racenet_formguide_cfb")
        self.assertEqual(pf["pf_aggregates"]["l600_delta_avg"], -1.25)
        self.assertEqual(pf["pf_aggregates"]["runner_time_avg"], 84.2)

    def test_stale_cross_horse_formguide_digest_is_replaced_atomically(self) -> None:
        logic = {
            "race_analysis": {"race_number": 3},
            "horses": {
                "7": {
                    "horse_name": "Example Star",
                    "_data": {
                        "sire_line": "Wrong Horse Sire",
                        "latest_official_jockey": "Wrong Rider",
                        "has_blinkers": True,
                        "current_jockey_formal_rides": 99,
                    },
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            facts_path = folder / "11-01 Race 3 Facts.md"
            facts_path.write_text(MODERN_FACTS, encoding="utf-8")
            formguide_path = folder / "11-01 Race 3 Formguide.md"
            formguide_path.write_text(
                "\n".join(
                    [
                        "[7] Example Star (4)",
                        "3yoG BAY | Sire: Correct Sire | Dam: Test Dam",
                        "T: T Smith (LY: 100:10-20-15) | J: J Doe (LY: 80:8-12-10)",
                        "Randwick R5 2026-10-01 1400m cond:4 $60,000 J Doe (4) 58kg Flucs:$5 $6 01:23.500 2nd@800m 2nd@400m 2nd@Settled.",
                    ]
                ),
                encoding="utf-8",
            )
            enriched = enrich_logic_from_facts(logic, facts_path)

        data = enriched["horses"]["7"]["_data"]
        self.assertEqual(data["sire_line"], "Correct Sire")
        self.assertEqual(data["latest_official_jockey"], "J Doe")
        self.assertFalse(data["has_blinkers"])
        self.assertEqual(data["current_jockey_formal_rides"], 1)

    def test_cross_horse_formguide_identity_is_rejected_before_refresh(self) -> None:
        logic = {
            "race_analysis": {"race_number": 3},
            "horses": {
                "7": {
                    "horse_name": "Example Star",
                    "_data": {"sire_line": "Existing Correct Sire"},
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            facts_path = folder / "11-01 Race 3 Facts.md"
            facts_path.write_text(MODERN_FACTS, encoding="utf-8")
            (folder / "11-01 Race 3 Formguide.md").write_text(
                "\n".join(
                    [
                        "[7] Different Horse (4)",
                        "3yoG BAY | Sire: Wrong Sire | Dam: Wrong Dam",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "FORMGUIDE ALIGNMENT FAILED"):
                enrich_logic_from_facts(logic, facts_path)


if __name__ == "__main__":
    unittest.main()
