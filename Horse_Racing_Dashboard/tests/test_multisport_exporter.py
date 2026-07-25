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
            self.assertEqual(len(snapshot["recommendations"]), 1)
            recommendation = snapshot["recommendations"][0]
            self.assertEqual(recommendation["odds"], 2.12)
            self.assertEqual(recommendation["bet_type"], "combo")
            self.assertEqual(len(recommendation["legs"]), 2)
            self.assertEqual(recommendation["legs"][0]["odds"], 1.72)
            self.assertIn("Sportsbet_Odds_CHI_WAS.json", recommendation["source_files"])

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

    def test_tennis_exporter_emits_only_bet_rows_and_preserves_combo_legs(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tennis.db"
            self._create_tennis_database(db_path)

            snapshot = export_tennis_snapshot(db_path, target_date="2026-07-25")

            self.assertEqual(snapshot["validation_status"], "valid")
            self.assertEqual(snapshot["analysis_run_id"], "tennis:2026-07-25")
            self.assertEqual(len(snapshot["recommendations"]), 2)
            single = next(row for row in snapshot["recommendations"] if row["bet_type"] == "single")
            combo = next(row for row in snapshot["recommendations"] if row["bet_type"] == "combo")
            self.assertEqual(single["selection"], "Otto Virtanen")
            self.assertEqual(single["odds"], 1.56)
            self.assertEqual(single["metrics"]["model_probability"], 0.779823)
            self.assertEqual(combo["odds"], 3.9)
            self.assertEqual(len(combo["legs"]), 2)
            self.assertEqual(combo["legs"][1]["selection"], "Otto Virtanen")

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
            INSERT INTO players VALUES (1, 'Maks Kasnikowski'), (2, 'Otto Virtanen');
            INSERT INTO tournaments VALUES (1, 'ATP Tampere Challenger');
            INSERT INTO matches VALUES (10, '2026-07-25', 'ATP', 'UNKNOWN', 1, 1, 2);
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
            """
        )
        legs = [
            {
                "id": "9|match_winner|Elina Avanesyan|None",
                "match_id": 9,
                "match_label": "Anna Bondar vs Elina Avanesyan",
                "market_key": "match_winner",
                "market_name": "Match Betting",
                "selection_name": "Elina Avanesyan",
                "odds": 2.5,
                "confidence": 75,
                "edge": 0.153867,
            },
            {
                "id": "10|match_winner|Otto Virtanen|None",
                "match_id": 10,
                "match_label": "Maks Kasnikowski vs Otto Virtanen",
                "market_key": "match_winner",
                "market_name": "Match Betting",
                "selection_name": "Otto Virtanen",
                "odds": 1.56,
                "confidence": 75,
                "edge": 0.166559,
            },
        ]
        connection.execute(
            """
            INSERT INTO combo_tracker VALUES (
                200, 'combo-key', 10, '2026-07-25',
                'Anna Bondar vs Elina Avanesyan', '價值膽', ?, 3.9,
                75, 0.1602, 2.0, 'PENDING', NULL,
                '2026-07-25T03:53:51Z', '2026-07-25T03:53:51Z', NULL
            )
            """,
            (json.dumps(legs),),
        )
        connection.commit()
        connection.close()


if __name__ == "__main__":
    unittest.main()
