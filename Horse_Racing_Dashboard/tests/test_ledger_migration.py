import sqlite3
import tempfile
import unittest
from pathlib import Path

from Horse_Racing_Dashboard.scripts.migrate_kv_to_d1 import build_migration_sql


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "migrations" / "0001_unified_bet_ledger.sql"


class LedgerMigrationTests(unittest.TestCase):
    def test_build_sql_imports_horses_sports_legs_and_tombstones_idempotently(self):
        roi = {
            "2026-07-15|HappyValley|1|3": {
                "date": "2026-07-15",
                "venue": "HappyValley",
                "region": "hkjc",
                "race_number": 1,
                "horse_number": 3,
                "horse_name": "Snapshot Horse",
                "stake": 1,
                "odds": 2.5,
                "result_position": 1,
                "payout": 2.5,
                "net_profit": 1.5,
                "status": "won",
                "_updated_at": 100,
            },
            "2026-07-15|HappyValley|2|4": {
                "date": "2026-07-15",
                "venue": "HappyValley",
                "race_number": 2,
                "horse_number": 4,
                "_deleted": True,
                "deleted_at": 200,
            },
            "2026-07-15|HappyValley|3|5": {
                "date": "2026-07-15",
                "venue": "HappyValley",
                "race_number": 3,
                "horse_number": 5,
                "horse_name": "Pending Horse",
                "stake": 1,
                "odds": 0,
                "result_position": None,
                "payout": 0,
                "net_profit": -1,
                "status": "pending",
                "_updated_at": 250,
            },
        }
        sports = {
            "tennis-combo": {
                "id": "tennis-combo",
                "sport": "tennis",
                "source_id": "tennis:combo:test",
                "event_date": "2026-07-25",
                "event_name": "2-match Combo",
                "market": "Tennis Multi",
                "selection": "A + B",
                "bet_type": "combo",
                "odds": 3,
                "stake": 1,
                "status": "pending",
                "payout": 0,
                "profit": 0,
                "analysis_snapshot": {"edge": 0.1},
                "legs": [
                    {"event_name": "A vs X", "market": "Match Betting", "selection": "A", "odds": 2},
                    {"event_name": "B vs Y", "market": "Match Betting", "selection": "B", "odds": 1.5},
                ],
                "created_at": 300,
                "updated_at": 300,
            },
        }

        sql, summary = build_migration_sql(roi, sports)
        self.assertEqual(summary["horse_rows"], 3)
        self.assertEqual(summary["sports_rows"], 1)
        self.assertEqual(summary["leg_rows"], 2)

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "ledger.sqlite"
            connection = sqlite3.connect(db_path)
            connection.executescript(SCHEMA.read_text(encoding="utf-8"))
            connection.executescript(sql)
            connection.executescript(sql)
            bets = connection.execute(
                "SELECT sport, COUNT(*) FROM bets GROUP BY sport ORDER BY sport"
            ).fetchall()
            legs = connection.execute("SELECT COUNT(*) FROM bet_legs").fetchone()[0]
            deleted = connection.execute(
                "SELECT deleted_at FROM bets WHERE source_id = ?",
                ("2026-07-15|HappyValley|2|4",),
            ).fetchone()[0]
            migrations = connection.execute("SELECT COUNT(*) FROM migration_state").fetchone()[0]
            pending_profit = connection.execute(
                "SELECT profit FROM bets WHERE source_id = ?",
                ("2026-07-15|HappyValley|3|5",),
            ).fetchone()[0]
            connection.close()

        self.assertEqual(bets, [("horses", 3), ("tennis", 1)])
        self.assertEqual(legs, 2)
        self.assertEqual(deleted, 200)
        self.assertEqual(migrations, 1)
        self.assertEqual(pending_profit, 0)


if __name__ == "__main__":
    unittest.main()
