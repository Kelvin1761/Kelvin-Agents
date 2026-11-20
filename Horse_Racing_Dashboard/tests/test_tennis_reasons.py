import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from services.tennis_reasons import _compare, pick_reasons
from services.tennis_tracking import export_tennis_tracking

MATCH = {"player_a_id": 1, "player_b_id": 2}
PLAYERS = {1: "Martineau", 2: "Gaston"}


def evidence(quality=65, matches=(25, 25)):
    def prof(hold, brk, elo, n):
        return {"serve": {"hold_rate": hold}, "returning": {"break_rate": brk},
                "opponent_elo_mean": elo, "matches": n, "surface": None}
    return json.dumps({"data_quality_score": quality, "profiles": {"serve_return": {
        "1": prof(0.84, 0.18, 1588, matches[0]), "2": prof(0.74, 0.33, 1711, matches[1])}}})


def handicap_prop(side="under"):
    # Both spread rows settle on player A's margin; B is picked on the 'under' row.
    return {"market_key": "player_game_handicap_2.5", "side": side, "line": -2.5,
            "subject_player_id": 1, "predicted_mean": -3.052, "pricing_evidence_json": evidence()}


FEATURED = {"market_key": "player_game_handicap_2.5", "selection": "Gaston (-2.5)",
            "odds": 1.83, "edge": 0.1721, "ev": 0.2224, "model_prob": 0.668,
            "featured_at": "2026-11-11T12:13:54Z"}


def test_handicap_pick_explains_price_margin_and_form_from_the_picked_side():
    pred = {"selection_player_id": 2, "model_probability": 0.617, "no_vig_market_probability": 0.59}
    reasons = pick_reasons(FEATURED, handicap_prop(), MATCH, PLAYERS, pred)
    text = "\n".join(reasons)
    assert "67%" in reasons[0] and "50%" in reasons[0] and "17.2 個百分點" in reasons[0]
    # A's margin is -3.05, so the picked B is projected to win by 3.1 and must give 2.5.
    assert "Gaston 全場平均贏多 3.1 局" in reasons[1] and "贏多 2.5 局以上先中" in reasons[1]
    assert "Gaston 贏嘅機會係 62%（市場估 59%）" in text
    assert "Martineau 發球強好多，Gaston 破發強好多" in text
    assert "Gaston 嘅數字係對住較強對手打出嚟" in text
    assert "數據完整度" not in text  # always 65 = the entry bar; said nothing


def test_unknown_court_is_named_and_a_known_one_is_not():
    unknown = "\n".join(pick_reasons(FEATURED, handicap_prop(), MATCH, PLAYERS, court=""))
    assert "場地未知" in unknown
    known = "\n".join(pick_reasons(FEATURED, handicap_prop(), MATCH, PLAYERS, court="Hard"))
    assert "場地未知" not in known


def test_receiving_handicap_reads_as_lose_by_less_than():
    featured = dict(FEATURED, selection="Martineau (+2.5)")
    reasons = pick_reasons(featured, handicap_prop(side="over"), MATCH, PLAYERS)
    assert "Martineau 全場平均輸 3.1 局" in reasons[1]
    assert "輸少過 2.5 局都中" in reasons[1]


def test_comparison_wording_has_level_and_big_gap_thresholds():
    assert _compare(0.01, 0.10, "A", "B") == "發球兩個差唔多，A 破發強好多。"
    assert _compare(-0.11, -0.11, "A", "B") == "B 發球同破發都強好多。模型揀 A 主要係覺得價錢開得太闊。"
    assert _compare(0.05, 0.04, "A", "B") == "A 發球同破發都較強。"


def test_thin_sample_is_flagged():
    prop = dict(handicap_prop(), pricing_evidence_json=evidence(matches=(25, 2)))
    assert "得 2 場紀錄，樣本少" in pick_reasons(FEATURED, prop, MATCH, PLAYERS)[-1]


def test_malformed_evidence_still_gives_the_price_reason_and_never_raises():
    prop = dict(handicap_prop(), pricing_evidence_json="{not json", predicted_mean="x")
    reasons = pick_reasons(FEATURED, prop, MATCH, PLAYERS)
    assert len(reasons) == 1 and "17.2 個百分點" in reasons[0]
    assert pick_reasons({}, {}, {}, {}) == []


def _db(path):
    c = sqlite3.connect(path)
    c.executescript("""
    CREATE TABLE players(id INTEGER PRIMARY KEY,name TEXT);
    INSERT INTO players VALUES(1,'Martineau'),(2,'Gaston');
    CREATE TABLE matches(id INTEGER PRIMARY KEY,match_date TEXT,player_a_id INTEGER,player_b_id INTEGER,start_time_utc TEXT,fixture_status TEXT,tour TEXT);
    INSERT INTO matches VALUES(1,'2026-11-12',1,2,'2026-11-11T13:20:00Z','ACTIVE','ATP');
    CREATE TABLE prop_tracker(id INTEGER PRIMARY KEY,match_id INTEGER,match_date TEXT,is_value INTEGER,market_key TEXT,selection TEXT,decimal_odds REAL,stake_units REAL,result_status TEXT,profit_loss_units REAL,recorded_at TEXT,is_point_in_time INTEGER,side TEXT,line REAL,subject_player_id INTEGER,predicted_mean REAL,blended_prob REAL,pricing_evidence_json TEXT);
    CREATE TABLE prop_live_bets(id INTEGER PRIMARY KEY,prop_id INTEGER,odds_taken REAL,stake_aud REAL,placed_at TEXT,currency TEXT);
    CREATE TABLE featured_picks(id INTEGER PRIMARY KEY,prop_id INTEGER,match_id INTEGER,match_date TEXT,rank INTEGER,run_label TEXT,market_key TEXT,selection TEXT,match_label TEXT,feed_market_name TEXT,feed_selection_name TEXT,start_time_utc TEXT,odds REAL,edge REAL,ev REAL,model_prob REAL,featured_at TEXT);
    CREATE TABLE predictions(id INTEGER PRIMARY KEY,match_id INTEGER,selection_player_id INTEGER,model_probability REAL,no_vig_market_probability REAL,created_at TEXT);
    """)
    c.execute("INSERT INTO prop_tracker VALUES(1,1,'2026-11-12',1,'player_game_handicap_2.5','Gaston (-2.5)',1.83,1,'PENDING',NULL,"
              "'2026-11-11T12:13:00Z',1,'under',-2.5,1,-3.052,0.4959,?)", (evidence(),))
    c.execute("INSERT INTO featured_picks VALUES(1,1,1,'2026-11-12',6,'23:00','player_game_handicap_2.5','Gaston (-2.5)',"
              "'Martineau vs Gaston','Game Handicap','Gaston -2.5','2026-11-11T13:20:00Z',1.83,0.1721,0.2224,0.668,"
              "'2026-11-11T12:13:54Z')")
    c.execute("INSERT INTO predictions VALUES(1,1,2,0.617,0.59,'2026-11-11T12:12:59Z')")
    c.execute("INSERT INTO predictions VALUES(2,1,2,0.99,0.99,'2026-11-11T13:00:00Z')")  # after the pick
    c.commit()
    c.close()


def test_export_attaches_reasons_and_the_odds_blind_model_probability(tmp_path):
    path = tmp_path / "db"
    _db(path)
    (pick,) = [r for r in export_tennis_tracking(path)["records"] if r["kind"] == "featured"]
    assert pick["model_probability"] == 0.668  # not the market-weighted 0.4959
    text = "\n".join(pick["reasons"])
    assert "贏嘅機會係 62%" in text and "99%" not in text  # a later prediction is never used
    (prop,) = [r for r in export_tennis_tracking(path)["records"] if r["kind"] == "prop"]
    assert "reasons" not in prop
