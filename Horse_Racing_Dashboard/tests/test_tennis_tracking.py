import json
import sqlite3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from services.tennis_tracking import export_tennis_tracking


def database(path):
    c = sqlite3.connect(path)
    c.executescript("""
    CREATE TABLE players(id INTEGER PRIMARY KEY,name TEXT);
    INSERT INTO players VALUES(1,'Player A'),(2,'Player B');
    CREATE TABLE matches(id INTEGER PRIMARY KEY,match_date TEXT,player_a_id INTEGER,player_b_id INTEGER,start_time_utc TEXT,fixture_status TEXT,tour TEXT);
    INSERT INTO matches VALUES(1,'2026-10-26',1,2,'2026-10-26T22:00:00Z','ACTIVE','ATP');
    CREATE TABLE prop_tracker(id INTEGER PRIMARY KEY,match_id INTEGER,match_date TEXT,is_value INTEGER,market_key TEXT,selection TEXT,decimal_odds REAL,stake_units REAL,result_status TEXT,profit_loss_units REAL,recorded_at TEXT,is_point_in_time INTEGER);
    CREATE TABLE clv_tracker(id INTEGER PRIMARY KEY,recommendation_type TEXT,source_id INTEGER,match_id INTEGER,match_date TEXT,selection_name TEXT,odds_taken REAL,result_status TEXT,recorded_at TEXT);
    CREATE TABLE combo_tracker(id INTEGER PRIMARY KEY,combo_key TEXT,match_id INTEGER,match_date TEXT,match_label TEXT,legs_json TEXT,combo_odds REAL,result_status TEXT,recorded_at TEXT);
    CREATE TABLE predictions(id INTEGER PRIMARY KEY,match_id INTEGER,match_date TEXT,selection_name TEXT,current_market_odds REAL,decision TEXT,created_at TEXT);
    CREATE TABLE market_predictions(id INTEGER PRIMARY KEY,match_id INTEGER,selection_name TEXT,odds REAL,decision TEXT,created_at TEXT);
    CREATE TABLE prop_live_bets(id INTEGER PRIMARY KEY,prop_id INTEGER,odds_taken REAL,stake_aud REAL,placed_at TEXT,currency TEXT);
    """)
    return c


def prop(c, i=1, recorded="2026-10-26T20:00:00Z", pit=1):
    c.execute(
        "INSERT INTO prop_tracker VALUES(?,1,?,1,?,?,?,?,?,?,?,?)",
        (i, "2026-10-26", "aces", "Player A Over 3.5", 2.0, 0.5, "WON", 0.5, recorded, pit),
    )


def test_exports_every_value_single_and_combo_without_top_two_cap(tmp_path):
    path = tmp_path / "db"
    c = database(path)
    for i in range(1, 8):
        prop(c, i)
    for i in range(1, 5):
        c.execute(
            "INSERT INTO combo_tracker VALUES(?,?,1,?,?,?,?,?,?)",
            (
                i,
                str(i),
                "2026-10-26",
                "A + B",
                json.dumps([{"match_id": 1, "selection": "A"}]),
                3.0,
                "PENDING",
                "2026-10-26T20:00:00Z",
            ),
        )
    c.commit()
    c.close()
    out = export_tennis_tracking(path)
    assert out["status"] == "valid"
    assert len(out["records"]) == 11
    assert len({r["id"] for r in out["records"]}) == 11
    assert out["source_counts"]["prop_tracker"] == 7
    assert {r["day"] for r in out["records"]} == {"2026-10-27"}  # Sydney, not source UTC date


def test_late_disputed_unknown_and_void_stay_visible(tmp_path):
    path = tmp_path / "db"
    c = database(path)
    prop(c, 1, recorded="2026-10-26T23:00:00Z")
    prop(c, 2, pit=None)
    prop(c, 3)
    c.execute("UPDATE prop_tracker SET result_status='VOID',profit_loss_units=0 WHERE id=3")
    c.commit()
    c.close()
    rows = export_tennis_tracking(path)["records"]
    assert len(rows) == 3
    assert rows[0]["point_in_time"] is False
    assert rows[1]["point_in_time"] is True  # exact clocks establish timing even without old flag
    assert rows[2]["state"] == "void" and rows[2]["unit_profit"] == 0
    c = sqlite3.connect(path)
    c.execute("UPDATE matches SET fixture_status='DISPUTED'")
    c.commit()
    c.close()
    rows = export_tennis_tracking(path)["records"]
    assert all(r["state"] == "unverified" and not r["point_in_time"] for r in rows)


def test_prop_clv_mirror_deduplicated_but_other_market_preserved(tmp_path):
    path = tmp_path / "db"
    c = database(path)
    prop(c)
    c.executemany(
        "INSERT INTO clv_tracker VALUES(?,?,?,?,?,?,?,?,?)",
        [
            (1, "PROP_RECOMMENDATION", 1, 1, "2026-10-26", "A", 2.0, "WON", "2026-10-26T20:00:00Z"),
            (2, "MARKET_LEG", 2, 1, "2026-10-26", "B", 3.0, "PENDING", "2026-10-26T20:00:00Z"),
        ],
    )
    c.commit()
    c.close()
    rows = export_tennis_tracking(path)["records"]
    assert len(rows) == 2 and {r["kind"] for r in rows} == {"prop", "market"}


def test_native_actual_bets_are_separate_and_use_taken_odds(tmp_path):
    path = tmp_path / "db"
    c = database(path)
    prop(c)
    c.execute("INSERT INTO prop_live_bets VALUES(1,1,2.2,25,'2026-10-26T20:00:00Z','AUD')")
    c.commit()
    c.close()
    out = export_tennis_tracking(path)
    assert len(out["actual_bets"]) == 1 and len(out["records"]) == 1
    assert out["actual_bets"][0]["odds"] == 2.2
    assert out["actual_bets"][0]["stake_aud"] == 25
    assert "unit_profit" not in out["actual_bets"][0]


def test_missing_combo_leg_or_naive_timestamp_never_counts_as_pit(tmp_path):
    path = tmp_path / "db"
    c = database(path)
    prop(c, recorded="2026-10-26 20:00:00", pit=None)
    legs = json.dumps([{"match_id": 1, "selection": "A"}, {"match_id": 999, "selection": "B"}])
    c.execute("INSERT INTO combo_tracker VALUES(1,'c',1,'2026-10-26','A+B',?,3.,'WON','2026-10-26T20:00:00Z')", (legs,))
    c.commit()
    c.close()
    out = export_tennis_tracking(path)
    assert len(out["records"]) == 2
    assert all(not r["point_in_time"] for r in out["records"])


def test_repricing_does_not_resurrect_old_bet_when_latest_is_no_bet(tmp_path):
    path = tmp_path / "db"
    c = database(path)
    c.executemany(
        "INSERT INTO predictions VALUES(?,?,?,?,?,?,?)",
        [
            (1, 1, "2026-10-26", "A", 2.0, "BET", "2026-10-26T20:00:00Z"),
            (2, 1, "2026-10-26", "A", 2.0, "NO_BET", "2026-10-26T21:00:00Z"),
        ],
    )
    c.commit()
    c.close()
    assert export_tennis_tracking(path)["records"] == []


def test_read_only_and_missing_db_does_not_create_file(tmp_path):
    path = tmp_path / "missing.db"
    assert export_tennis_tracking(path)["status"] == "unavailable"
    assert not path.exists()
    c = database(path)
    prop(c)
    c.commit()
    c.close()
    before = path.read_bytes()
    export_tennis_tracking(path)
    assert before == path.read_bytes()
