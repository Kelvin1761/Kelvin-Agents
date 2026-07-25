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

from services.settlement_exporter import (  # noqa: E402
    export_nba_settlements,
    export_tennis_settlements,
)


class SettlementExporterTests(unittest.TestCase):
    def test_tennis_exporter_uses_tracker_status_and_resolves_combo_legs_per_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tennis.db"
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
                INSERT INTO matches VALUES (10, '2026-07-25', 1, 2);
                INSERT INTO matches VALUES (20, '2026-07-25', 3, 4);
                INSERT INTO match_results VALUES (1, 10, 1, 'official', '{}');
                INSERT INTO match_results VALUES (2, 20, 4, 'official', '{}');
                INSERT INTO clv_tracker VALUES (
                    7, 'MARKET_LEG', 42, 10, '2026-07-25',
                    'WON', 1.1, '2026-07-26T00:00:00Z'
                );
                """
            )
            legs = [
                {
                    "match_id": 10,
                    "selection_name": "Player A",
                    "selection_side": "player_a",
                    "market_key": "match_winner",
                    "market_name": "Match Betting",
                    "odds": 2.1,
                },
                {
                    "match_id": 20,
                    "selection_name": "Player C",
                    "selection_side": "player_a",
                    "market_key": "match_winner",
                    "market_name": "Match Betting",
                    "odds": 1.5,
                },
            ]
            connection.execute(
                "INSERT INTO combo_tracker VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    8,
                    "combo-key",
                    "2026-07-25",
                    json.dumps(legs),
                    3.15,
                    "LOST",
                    -1,
                    "2026-07-26T00:00:00Z",
                    "2026-07-26T00:00:00Z",
                ),
            )
            connection.commit()
            connection.close()

            payload = export_tennis_settlements(db_path, "2026-07-25")

            self.assertEqual(payload["validation_status"], "valid")
            single = next(row for row in payload["settlements"] if row["source_id"] == "tennis:market:42")
            combo = next(row for row in payload["settlements"] if row["source_id"] == "tennis:combo:combo-key")
            self.assertEqual(single["status"], "won")
            self.assertEqual(combo["status"], "lost")
            self.assertEqual([leg["status"] for leg in combo["legs"]], ["won", "lost"])

    def test_nba_exporter_grades_banker_and_combo_from_results_brief(self):
        with tempfile.TemporaryDirectory() as tmp:
            analysis_dir = Path(tmp) / "2026-04-15 NBA Analysis"
            analysis_dir.mkdir()
            (analysis_dir / "Sportsbet_Odds_CHI_WAS.json").write_text(
                json.dumps(
                    {
                        "target_analysis_date": "2026-04-15",
                        "game_tag": "CHI_WAS",
                        "source": "sportsbet.com.au",
                        "player_props": {"PTS": {"Zach LaVine": {"line": "24+", "odds": 1.72}}},
                    }
                ),
                encoding="utf-8",
            )
            (analysis_dir / "Game_CHI_WAS_Full_Analysis.md").write_text(
                """# 🏀 NBA Wong Choi — Chicago Bulls @ Washington Wizards
**odds_source**: SPORTSBET_LIVE ✅
## 🎰 SGM Parlay 組合 (Python Auto-Selection V5)
### 🛡️ 組合 1: 穩膽 SGM (Low Risk) — 組合賠率 @2.12
| Leg | 選擇 | 賠率 | L10 | 調整命中率 | EV |
|---|---|---:|---:|---:|---:|
| 🧩 1 | Zach LaVine PTS 24+ | @1.72 | 80% | 74% | +5.1% |
| 🧩 2 | Jordan Poole AST 4+ | @1.23 | 90% | 82% | +2.0% |
## 📊 球員盤口詳細分析 (Appendix)
✅ Python 預填完成 | 組合數: 1 | 未填寫項目 殘留: 0 個
""",
                encoding="utf-8",
            )
            (analysis_dir / "Results_Brief_2026-04-14.json").write_text(
                json.dumps(
                    {
                        "date": "2026-04-14",
                        "games": [
                            {
                                "away": {"team": "CHI", "score": 110},
                                "home": {"team": "WAS", "score": 105},
                                "players": [
                                    {"name": "Zach LaVine", "pts": 30, "reb": 5, "ast": 4, "fg3m": 3},
                                    {"name": "Jordan Poole", "pts": 20, "reb": 2, "ast": 3, "fg3m": 2},
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            payload = export_nba_settlements(analysis_dir)

            self.assertEqual(payload["validation_status"], "valid")
            banker = next(row for row in payload["settlements"] if row["source_id"].endswith(":banker"))
            combo = next(row for row in payload["settlements"] if row["source_id"].endswith(":combo:1"))
            self.assertEqual(banker["status"], "won")
            self.assertEqual(combo["status"], "lost")
            self.assertEqual([leg["status"] for leg in combo["legs"]], ["won", "lost"])


if __name__ == "__main__":
    unittest.main()
