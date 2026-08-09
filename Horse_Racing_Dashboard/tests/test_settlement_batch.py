import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


DASHBOARD_DIR = Path(__file__).resolve().parents[1]
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from settle_dashboard_bets import build_settlement_batch  # noqa: E402


class SettlementBatchTests(unittest.TestCase):
    def test_batch_is_empty_and_explains_missing_result_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = build_settlement_batch(Path(tmp))

        self.assertEqual(payload["summary"], {"total": 0, "tennis": 0, "nba": 0})
        self.assertEqual(payload["sources"]["tennis"]["validation_status"], "unavailable")
        self.assertEqual(payload["sources"]["nba"]["validation_status"], "unavailable")

    def test_batch_includes_native_tennis_tracker_settlement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "tennis.db"
            connection = sqlite3.connect(db_path)
            connection.executescript(
                """
                CREATE TABLE matches (
                    id INTEGER PRIMARY KEY, match_date TEXT,
                    player_a_id INTEGER, player_b_id INTEGER
                );
                CREATE TABLE match_results (
                    id INTEGER PRIMARY KEY, match_id INTEGER,
                    winner_player_id INTEGER, source_provider TEXT, score_json TEXT
                );
                CREATE TABLE clv_tracker (
                    id INTEGER PRIMARY KEY, recommendation_type TEXT,
                    source_id INTEGER, match_id INTEGER, match_date TEXT,
                    result_status TEXT, profit_loss_units REAL, updated_at TEXT
                );
                CREATE TABLE combo_tracker (
                    id INTEGER PRIMARY KEY, combo_key TEXT, match_date TEXT,
                    legs_json TEXT, combo_odds REAL, result_status TEXT,
                    profit_loss_units REAL, settled_at TEXT, updated_at TEXT
                );
                INSERT INTO matches VALUES (1, '2026-07-25', 1, 2);
                INSERT INTO match_results VALUES (1, 1, 1, 'official', '{}');
                INSERT INTO clv_tracker VALUES (
                    1, 'MARKET_LEG', 99, 1, '2026-07-25',
                    'WON', 1.1, '2026-07-26T00:00:00Z'
                );
                """
            )
            connection.commit()
            connection.close()

            payload = build_settlement_batch(
                root,
                target_date="2026-07-25",
                tennis_db=db_path,
            )

        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["settlements"][0]["source_id"], "tennis:market:99")
        self.assertEqual(payload["settlements"][0]["status"], "won")


if __name__ == "__main__":
    unittest.main()
