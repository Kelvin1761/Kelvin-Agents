import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


DASHBOARD_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = DASHBOARD_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.multisport_exporter import (  # noqa: E402
    export_nba_snapshot,
    export_tennis_snapshot,
    validate_multisport_feed,
)


class MultiSportExporterTests(unittest.TestCase):
    def test_nba_exporter_requires_verified_sportsbet_source_and_parses_combo_legs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            analysis_dir = root / "2026-04-15 NBA Analysis"
            analysis_dir.mkdir()
            (analysis_dir / "Sportsbet_Odds_CHI_WAS.json").write_text(
                json.dumps(
                    {
                        "target_analysis_date": "2026-04-15",
                        "game_tag": "CHI_WAS",
                        "source": "sportsbet.com.au",
                        "player_props": {
                            "PTS": {
                                "Zach LaVine": {"line": "24+", "odds": 1.72}
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            (analysis_dir / "Game_CHI_WAS_Full_Analysis.md").write_text(
                """# 🏀 NBA Wong Choi — Chicago Bulls @ Washington Wizards
**日期**: 2026-04-15
**odds_source**: SPORTSBET_LIVE ✅
## 🎰 SGM Parlay 組合 (Python Auto-Selection V5)
### 🛡️ 組合 1: 穩膽 SGM (Low Risk) — 組合賠率 @2.12
| Leg | 選擇 | 賠率 | L10 | 調整命中率 | EV |
|---|---|---:|---:|---:|---:|
| 🧩 1 | Zach LaVine 24+ PTS | @1.72 | 80% | 74% | +5.1% |
| 🧩 2 | Jordan Poole 4+ AST | @1.23 | 90% | 82% | +2.0% |
## 📊 球員盤口詳細分析 (Appendix)
✅ Python 預填完成 | 組合數: 1 | 未填寫項目 殘留: 0 個
""",
                encoding="utf-8",
            )

            snapshot = export_nba_snapshot(root, target_date="2026-04-15")

            self.assertEqual(snapshot["validation_status"], "valid")
            self.assertEqual(snapshot["analysis_run_id"], "nba:2026-04-15")
            self.assertEqual(len(snapshot["recommendations"]), 2)
            recommendation = next(
                row for row in snapshot["recommendations"] if row["bet_type"] == "combo"
            )
            banker = next(
                row for row in snapshot["recommendations"] if row["category"] == "banker"
            )
            self.assertEqual(recommendation["odds"], 2.12)
            self.assertEqual(recommendation["odds_status"], "sportsbet_extracted")
            self.assertEqual(recommendation["bet_type"], "combo")
            self.assertEqual(len(recommendation["legs"]), 2)
            self.assertEqual(recommendation["legs"][0]["odds"], 1.72)
            self.assertIn("Sportsbet_Odds_CHI_WAS.json", recommendation["source_files"])
            self.assertEqual(banker["selection"], "Zach LaVine 24+ PTS")
            self.assertEqual(banker["metrics"]["model_probability"], 0.74)
            self.assertEqual(banker["metrics"]["expected_value"], 0.051)
            self.assertEqual(banker["metrics"]["l10_hit_rate"], 0.8)

    def test_nba_exporter_blocks_analysis_without_matching_sportsbet_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            analysis_dir = Path(tmp) / "2026-04-15 NBA Analysis"
            analysis_dir.mkdir()
            (analysis_dir / "Game_CHI_WAS_Full_Analysis.md").write_text(
                "# NBA\n**odds_source**: SPORTSBET_LIVE ✅\nPython Auto-Selection\n",
                encoding="utf-8",
            )

            snapshot = export_nba_snapshot(Path(tmp), target_date="2026-04-15")

            self.assertEqual(snapshot["validation_status"], "blocked")
            self.assertEqual(snapshot["recommendations"], [])
            self.assertIn("missing_matching_sportsbet_json", snapshot["warnings"])

    def test_tennis_exporter_emits_only_validated_props_and_preserves_combo_legs(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tennis.db"
            self._create_tennis_database(db_path)

            snapshot = export_tennis_snapshot(db_path, target_date="2026-07-25")

            self.assertEqual(snapshot["validation_status"], "valid")
            self.assertEqual(snapshot["analysis_run_id"], "tennis:2026-07-25")
            self.assertEqual(len(snapshot["recommendations"]), 2)
            single = next(row for row in snapshot["recommendations"] if row["bet_type"] == "single")
            combo = next(row for row in snapshot["recommendations"] if row["bet_type"] == "combo")
            self.assertEqual(single["selection"], "Over 7.5")
            self.assertEqual(single["odds"], 1.8)
            self.assertEqual(single["odds_status"], "sportsbet_extracted")
            self.assertEqual(single["metrics"]["model_probability"], 0.62)
            self.assertEqual(single["metrics"]["expected_value"], 0.116)
            self.assertEqual(single["outcome"], "pending")
            self.assertEqual(combo["odds"], 3.42)
            self.assertEqual(len(combo["legs"]), 2)
            self.assertEqual(combo["legs"][1]["selection"], "Under 18.5")
            self.assertEqual(snapshot["strategy"]["status"], "VALIDATED")
            self.assertEqual(snapshot["strategy"]["enabled_families"], ["player_aces"])
            self.assertEqual(snapshot["coverage"]["fixtures_found"], 1)
            self.assertEqual(snapshot["coverage"]["sportsbet_priced_matches"], 1)
            self.assertEqual(snapshot["coverage"]["singles_candidates"], 1)
            self.assertEqual(snapshot["coverage"]["modelled_matches"], 1)
            self.assertEqual(snapshot["coverage"]["unmodelled_priced_matches"], 0)
            self.assertEqual(snapshot["coverage"]["priced_ratio"], 1.0)
            self.assertEqual(
                snapshot["coverage"]["latest_sportsbet_scrape"],
                "2026-07-25T03:53:40Z",
            )

    def test_feed_validator_rejects_duplicate_ids_and_missing_live_odds(self):
        recommendation = {
            "id": "duplicate",
            "sport": "tennis",
            "event_date": "2026-07-25",
            "event_name": "A vs B",
            "market": "Match Betting",
            "selection": "A",
            "odds": None,
            "decision": "BET",
            "validation_status": "valid",
        }
        feed = {
            "schema_version": 2,
            "generated_at": "2026-07-25T00:00:00Z",
            "sports": {
                "nba": {"recommendations": []},
                "tennis": {"recommendations": [recommendation, dict(recommendation)]},
            },
        }

        errors = validate_multisport_feed(feed)

        self.assertIn("duplicate_recommendation_id:duplicate", errors)
        self.assertIn("missing_live_odds:duplicate", errors)

    @staticmethod
    def _create_tennis_database(path):
        connection = sqlite3.connect(path)
        connection.executescript(
            """
            CREATE TABLE players (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE tournaments (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE matches (
                id INTEGER PRIMARY KEY,
                match_date TEXT NOT NULL,
                tour TEXT NOT NULL,
                round TEXT NOT NULL,
                tournament_id INTEGER NOT NULL,
                player_a_id INTEGER NOT NULL,
                player_b_id INTEGER NOT NULL
            );
            CREATE TABLE market_predictions (
                id INTEGER PRIMARY KEY,
                match_id INTEGER NOT NULL,
                market_key TEXT NOT NULL,
                market_name TEXT NOT NULL,
                selection_name TEXT NOT NULL,
                selection_side TEXT,
                line REAL,
                odds REAL NOT NULL,
                model_status TEXT NOT NULL,
                model_probability REAL,
                no_vig_market_probability REAL,
                edge REAL,
                minimum_acceptable_odds REAL,
                decision TEXT NOT NULL,
                banker_eligible INTEGER NOT NULL,
                confidence INTEGER NOT NULL,
                risk TEXT NOT NULL,
                reason TEXT,
                pricing_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE odds_snapshots (
                id INTEGER PRIMARY KEY,
                event_id TEXT NOT NULL,
                match_id INTEGER,
                source_provider TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            );
            CREATE TABLE predictions (
                id INTEGER PRIMARY KEY,
                match_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE combo_tracker (
                id INTEGER PRIMARY KEY,
                combo_key TEXT NOT NULL,
                match_id INTEGER NOT NULL,
                match_date TEXT NOT NULL,
                match_label TEXT NOT NULL,
                tier TEXT NOT NULL,
                legs_json TEXT NOT NULL,
                combo_odds REAL NOT NULL,
                adjusted_confidence INTEGER,
                adjusted_edge REAL,
                stake_units REAL NOT NULL,
                result_status TEXT NOT NULL,
                profit_loss_units REAL,
                recorded_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                settled_at TEXT
            );
            CREATE TABLE clv_tracker (
                id INTEGER PRIMARY KEY,
                recommendation_type TEXT NOT NULL,
                source_id INTEGER NOT NULL,
                match_id INTEGER NOT NULL,
                match_date TEXT NOT NULL,
                closing_odds REAL,
                clv REAL,
                result_status TEXT NOT NULL,
                profit_loss_units REAL
            );
            CREATE TABLE prop_tracker (
                id INTEGER PRIMARY KEY,
                match_id INTEGER NOT NULL,
                match_date TEXT NOT NULL,
                match_label TEXT NOT NULL,
                market_key TEXT NOT NULL,
                line REAL NOT NULL,
                selection TEXT NOT NULL,
                side TEXT NOT NULL,
                decimal_odds REAL NOT NULL,
                model_prob_raw REAL,
                market_prob_fair REAL,
                blended_prob REAL,
                edge REAL,
                ev REAL,
                stake_units REAL NOT NULL,
                is_value INTEGER NOT NULL,
                result_status TEXT NOT NULL,
                profit_loss_units REAL
            );
            CREATE TABLE feature_snapshots (
                id INTEGER PRIMARY KEY,
                match_id INTEGER NOT NULL,
                data_quality_score REAL NOT NULL
            );
            INSERT INTO players VALUES (1, 'Maks Kasnikowski'), (2, 'Otto Virtanen');
            INSERT INTO tournaments VALUES (1, 'ATP Tampere Challenger');
            INSERT INTO matches VALUES (10, '2026-07-25', 'ATP', 'UNKNOWN', 1, 1, 2);
            INSERT INTO odds_snapshots VALUES (
                50, 'sportsbet-50', 10, 'sportsbet', '2026-07-25T03:53:40Z'
            );
            INSERT INTO predictions VALUES (60, 10, '2026-07-25T03:53:50Z');
            INSERT INTO market_predictions VALUES (
                100, 10, 'match_winner', 'Match Betting', 'Otto Virtanen',
                'player_b', NULL, 1.56, 'MODELLED', 0.779823, 0.590551,
                0.189272, 1.3426, 'BET', 1, 85, 'Low',
                'core_banker', '{"tier":"CORE_BANKER"}', '2026-07-25T03:53:50Z'
            );
            INSERT INTO market_predictions VALUES (
                101, 10, 'total_games', 'Total Games', 'Over 22.5',
                'over', 22.5, 1.90, 'MODELLED', 0.52, 0.50,
                0.02, 1.85, 'NO_BET', 0, 55, 'Medium',
                'edge_too_small', '{}', '2026-07-25T03:53:50Z'
            );
            INSERT INTO clv_tracker VALUES (
                1, 'MARKET_LEG', 100, 10, '2026-07-25',
                1.50, 0.04, 'WON', 0.56
            );
            INSERT INTO prop_tracker VALUES (
                1000, 10, '2026-07-25', 'Maks Kasnikowski vs Otto Virtanen',
                'total_otto_virtanen_aces_7_5', 7.5, 'Over 7.5', 'over',
                1.80, 0.68, 0.55, 0.62, 0.07, 0.116, 1.0, 1, 'PENDING', NULL
            );
            INSERT INTO feature_snapshots VALUES (70, 10, 0.92);
            """
        )
        connection.executemany(
            """
            INSERT INTO prop_tracker VALUES (
                ?, 10, '2026-07-24', 'Maks Kasnikowski vs Otto Virtanen',
                'total_otto_virtanen_aces_7_5', 7.5, 'Over 7.5', 'over',
                1.80, 0.90, 0.60, 0.70, 0.10, 0.26, 1.0, 1, 'WON', 0.80
            )
            """,
            [(2000 + index,) for index in range(120)],
        )
        legs = [
            {
                "id": "prop:9:total_alex_aces_7_5:over:7.5",
                "match_id": 9,
                "match_label": "Alex vs Bob",
                "market_key": "total_alex_aces_7_5",
                "market_name": "Total Alex Aces",
                "selection_name": "Over 7.5",
                "line": 7.5,
                "odds": 1.8,
                "confidence": 62,
                "edge": 0.06,
                "data_quality": 0.91,
            },
            {
                "id": "prop:10:total_otto_virtanen_aces_18_5:under:18.5",
                "match_id": 10,
                "match_label": "Maks Kasnikowski vs Otto Virtanen",
                "market_key": "total_otto_virtanen_aces_18_5",
                "market_name": "Total Otto Virtanen Aces",
                "selection_name": "Under 18.5",
                "line": 18.5,
                "odds": 1.9,
                "confidence": 60,
                "edge": 0.05,
                "data_quality": 0.92,
            },
        ]
        connection.execute(
            """
            INSERT INTO combo_tracker VALUES (
                200, 'combo-key', 10, '2026-07-25',
                'Alex vs Bob', 'PROP_2_LEG_TRIAL', ?, 3.42,
                37, 0.055, 1.0, 'PENDING', NULL,
                '2026-07-25T03:53:51Z', '2026-07-25T03:53:51Z', NULL
            )
            """,
            (json.dumps(legs),),
        )
        connection.commit()
        connection.close()


if __name__ == "__main__":
    unittest.main()
