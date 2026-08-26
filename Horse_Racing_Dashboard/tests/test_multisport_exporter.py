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
            self.assertEqual(single["metrics"]["stake_units"], 1.5)
            self.assertEqual(single["outcome"], "pending")
            self.assertEqual(combo["odds"], 3.42)
            self.assertEqual(len(combo["legs"]), 2)
            self.assertEqual(combo["legs"][1]["selection"], "Under 18.5")
            self.assertEqual(combo["metrics"]["stake_units"], 1.0)
            self.assertEqual(snapshot["strategy"]["status"], "VALIDATED_SINGLE")
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

    def test_tennis_dashboard_limits_validated_singles_to_one_per_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tennis.db"
            self._create_tennis_database(db_path)
            connection = sqlite3.connect(db_path)
            connection.execute(
                "INSERT INTO matches VALUES (11,'2026-07-25','ATP','R16',1,1,2)"
            )
            connection.execute("INSERT INTO feature_snapshots VALUES (71,11,0.93)")
            # Stronger same-match prop must replace, not sit beside, the
            # existing match-10 recommendation.
            connection.execute(
                "INSERT INTO prop_tracker VALUES "
                "(1001,10,'2026-07-25','A vs B','total_a_aces_8_5',8.5,"
                "'Over 8.5','over',1.9,0.70,0.52,0.64,0.08,0.216,1,1,'PENDING',NULL)"
            )
            connection.execute(
                "INSERT INTO prop_tracker VALUES "
                "(1002,11,'2026-07-25','A vs B','total_b_aces_6_5',6.5,"
                "'Over 6.5','over',1.8,0.68,0.54,0.61,0.07,0.098,1,1,'PENDING',NULL)"
            )
            connection.commit()
            connection.close()

            snapshot = export_tennis_snapshot(db_path, target_date="2026-07-25")
            singles = [
                row for row in snapshot["recommendations"]
                if row["bet_type"] == "single"
            ]
            self.assertEqual(len(singles), 2)
            self.assertEqual(
                {row["context"]["match_id"] for row in singles}, {10, 11}
            )
            match_ten = next(row for row in singles if row["context"]["match_id"] == 10)
            self.assertEqual(match_ten["selection"], "Over 8.5")

    def test_tennis_strategy_state_excludes_future_settlements(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tennis.db"
            self._create_tennis_database(db_path)
            connection = sqlite3.connect(db_path)
            connection.executemany(
                """
                INSERT INTO prop_tracker VALUES (
                    ?, 10, '2026-07-26', 'Future A vs B',
                    'total_otto_virtanen_aces_7_5', 7.5, 'Over 7.5', 'over',
                    1.80, 0.10, 0.60, 0.20, 0.01, -0.64, 1.0, 1,
                    'WON', 0.80
                )
                """,
                [(3000 + index,) for index in range(120)],
            )
            connection.commit()
            connection.close()

            snapshot = export_tennis_snapshot(db_path, target_date="2026-07-25")

            assert snapshot["strategy"]["enabled_families"] == ["player_aces"]
            assert snapshot["strategy"]["families"]["player_aces"][
                "scorecard_settled"
            ] == 120

    def test_tennis_dashboard_promotes_early_main_with_half_unit_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tennis.db"
            self._create_tennis_database(db_path)
            connection = sqlite3.connect(db_path)
            connection.execute(
                "DELETE FROM prop_tracker WHERE id >= 2055 AND id < 3000"
            )
            connection.commit()
            connection.close()

            snapshot = export_tennis_snapshot(db_path, target_date="2026-07-25")

            self.assertEqual(snapshot["strategy"]["status"], "EARLY_MAIN")
            self.assertEqual(
                snapshot["strategy"]["early_main_families"], ["player_aces"]
            )
            single = next(
                row for row in snapshot["recommendations"]
                if row["bet_type"] == "single"
            )
            combo = next(
                row for row in snapshot["recommendations"]
                if row["bet_type"] == "combo"
            )
            self.assertEqual(single["category"], "early_main_prop")
            self.assertEqual(single["metrics"]["stake_units"], 0.5)
            self.assertEqual(combo["category"], "early_main_prop_combo")
            self.assertEqual(combo["metrics"]["stake_units"], 0.5)

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
                "confidence_score": 82,
                "hit_probability": 0.62,
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
                "confidence_score": 80,
                "hit_probability": 0.60,
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


class TennisHonestPanelTests(unittest.TestCase):
    """The panel showed a family scorecard and archived July props and no
    overall figure, while the tracker's own provably pre-match rows read
    -23.38% ROI. A page that omits that is misleading, not neutral.
    """

    def _db(self, tmp: str, *, with_columns: bool = True) -> Path:
        db = Path(tmp) / "tennis-panel.db"
        conn = sqlite3.connect(db)
        rank_cols = ", current_rank INTEGER, overall_elo REAL" if with_columns else ""
        conn.executescript(
            f"""
            CREATE TABLE players (id INTEGER PRIMARY KEY, name TEXT{rank_cols});
            CREATE TABLE matches (id INTEGER PRIMARY KEY, match_date TEXT,
                player_a_id INTEGER, player_b_id INTEGER, tournament_id INTEGER);
            CREATE TABLE prop_tracker (
                id INTEGER PRIMARY KEY, stake_units REAL, profit_loss_units REAL,
                result_status TEXT, is_value INTEGER, is_point_in_time INTEGER);
            CREATE TABLE prop_live_bets (prop_id INTEGER);
            CREATE TABLE tournaments (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE rankings_history (player_id INTEGER, ranking_date TEXT, rank INTEGER);
            -- As-of rows, published BEFORE the fixture date. Player C has none,
            -- so fixture 2 is unranked exactly as the model sees it.
            INSERT INTO rankings_history VALUES (1,'2026-08-01',10),(2,'2026-08-01',20),
                                                (4,'2026-08-01',40);
            INSERT INTO tournaments VALUES (1,'ATP Test'),(2,'ATP Test Doubles');
            """
        )
        if with_columns:
            conn.executescript(
                """
                INSERT INTO players VALUES (1,'A',10,1800.0),(2,'B',20,1750.0),
                                           (3,'C',NULL,NULL),(4,'D',40,1700.0),
                                           (5,'E/F',NULL,NULL),(6,'G/H',NULL,NULL);
                """
            )
        else:
            conn.executescript(
                "INSERT INTO players VALUES (1,'A'),(2,'B'),(3,'C'),(4,'D'),"
                "(5,'E/F'),(6,'G/H');"
            )
        conn.executescript(
            """
            INSERT INTO matches VALUES (1,'2026-08-27',1,2,1),(2,'2026-08-27',3,4,1);
            -- A doubles fixture must not count against input completeness: it
            -- never enters the singles pipeline, and a pair label has no rank
            -- by definition. 413 of the 1,636 unranked priced players are pairs.
            INSERT INTO matches VALUES (3,'2026-08-27',5,6,2);
            -- two pre-match bets (one won, one lost) and one post-start winner
            INSERT INTO prop_tracker VALUES
                (1, 1.0,  0.9, 'WON',  1, 1),
                (2, 1.0, -1.0, 'LOST', 1, 1),
                (3, 1.0,  5.0, 'WON',  1, 0);
            """
        )
        conn.commit()
        conn.close()
        return db

    def test_the_record_counts_only_provably_pre_match_bets(self):
        from backend.services.multisport_exporter import _tennis_verified_record

        with tempfile.TemporaryDirectory() as tmp:
            conn = sqlite3.connect(self._db(tmp))
            conn.row_factory = sqlite3.Row
            record = _tennis_verified_record(conn)
            conn.close()
        self.assertEqual(record["point_in_time_settled"], 2)
        self.assertEqual(record["point_in_time_won"], 1)
        # (0.9 - 1.0) / 2.0 staked. The post-start +5.0 must not appear.
        self.assertAlmostEqual(record["point_in_time_roi"], -0.05, places=4)
        self.assertEqual(record["excluded_from_judgement"], 1)
        self.assertEqual(record["live_stakes_placed"], 0)

    def test_rank_completeness_is_measured_as_of_not_from_the_mutable_column(self):
        """`players.current_rank` has no date. Counting it overstated this
        number -- 58.8% against the model's own 31.2% on the same fixtures --
        and a progress indicator that flatters what it tracks is worse than
        none. Here player 3 carries a `current_rank` but no as-of row."""
        from backend.services.multisport_exporter import _tennis_input_completeness

        with tempfile.TemporaryDirectory() as tmp:
            db = self._db(tmp)
            conn = sqlite3.connect(db)
            conn.execute("UPDATE players SET current_rank = 900 WHERE id = 3")
            conn.commit()
            conn.row_factory = sqlite3.Row
            cov = _tennis_input_completeness(conn, "2026-08-27")
            conn.close()
        # Fixture 2 must stay uncounted: player 3 has a rank today and had none
        # before the match.
        self.assertEqual(cov["both_players_ranked"], 1)

    def test_input_completeness_reports_both_sides_present(self):
        from backend.services.multisport_exporter import _tennis_input_completeness

        with tempfile.TemporaryDirectory() as tmp:
            conn = sqlite3.connect(self._db(tmp))
            conn.row_factory = sqlite3.Row
            cov = _tennis_input_completeness(conn, "2026-08-27")
            conn.close()
        # Fixture 1 has both ranked; fixture 2 has player C with no rank;
        # fixture 3 is doubles and must be out of the denominator entirely --
        # otherwise this number sits permanently low against fixtures the model
        # is right to ignore.
        self.assertEqual(cov["both_players_ranked"], 1)
        self.assertAlmostEqual(cov["both_players_ranked_ratio"], 0.5, places=4,
                               msg="denominator must be 2 singles, not 3 fixtures")
        self.assertEqual(cov["both_players_elo"], 1)

    def test_a_database_without_the_columns_degrades_quietly(self):
        """An OperationalError here is swallowed upstream and turns the whole
        tennis panel into "unavailable" -- a diagnostic taking down the thing
        it describes."""
        from backend.services.multisport_exporter import _tennis_input_completeness

        with tempfile.TemporaryDirectory() as tmp:
            conn = sqlite3.connect(self._db(tmp, with_columns=False))
            conn.row_factory = sqlite3.Row
            self.assertEqual(_tennis_input_completeness(conn, "2026-08-27"), {})
            conn.close()

    def test_a_tracker_without_the_point_in_time_column_reports_nothing(self):
        """Better to show no record than to average a real loss with an
        artefact, which is what the whole-table figure did (+2.86%)."""
        from backend.services.multisport_exporter import _tennis_verified_record

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "old.db"
            conn = sqlite3.connect(db)
            conn.executescript(
                "CREATE TABLE prop_tracker (id INTEGER PRIMARY KEY, stake_units REAL,"
                " profit_loss_units REAL, result_status TEXT, is_value INTEGER);"
                "INSERT INTO prop_tracker VALUES (1, 1.0, 0.9, 'WON', 1);"
            )
            conn.commit()
            conn.row_factory = sqlite3.Row
            self.assertEqual(_tennis_verified_record(conn), {})
            conn.close()
