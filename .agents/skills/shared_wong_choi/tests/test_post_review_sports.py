"""NBA／網球自動覆盤（自學循環 L1）：分類、盤口類別、網球讀 DB（用未收縮模型機率）、NBA 組裝、排程接駁。"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

import post_review_sports as S  # noqa: E402

REPO = HERE.parents[4]


def test_family_strips_lines_and_ids():
    assert S._family("player_game_handicap_3.5") == "player_game_handicap"
    assert S._family("first_set_winner_20833") == "first_set_winner"
    assert S._family("total_games") == "total_games"


def test_nba_classify():
    assert S.nba_classify(0, 0.9, 0.9).startswith("上陣時間")
    assert S.nba_classify(30, 0.9, 0.7) == "市場都估錯"
    assert S.nba_classify(30, 0.9, 0.5) == "模型判錯"
    assert S.nba_classify(30, 0.9, None, raw=0.97) == "市場都估錯（未去水）"
    assert S.nba_classify(30, 0.9, None, raw=0.62) == "模型判錯"          # 單邊價要 ≥65% 先算


def test_tennis_classify():
    assert S.tennis_classify(0.8, 0.7, 65) == "市場都估錯"
    assert S.tennis_classify(0.8, 0.4, 40) == "輸入資料薄"
    assert S.tennis_classify(0.8, 0.4, 65) == "模型判錯"


def _tennis_db(path: Path):
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE prop_tracker (id INTEGER, match_id INTEGER, match_date TEXT, match_label TEXT, market_key TEXT, line REAL,
      selection TEXT, decimal_odds REAL, model_prob REAL, model_prob_raw REAL, market_prob_fair REAL, result_status TEXT,
      profit_loss_units REAL, pricing_evidence_json TEXT, is_point_in_time INTEGER);
    CREATE TABLE matches (id INTEGER, tournament_id INTEGER);
    CREATE TABLE tournaments (id INTEGER, name TEXT);
    CREATE TABLE featured_picks (id INTEGER, prop_id INTEGER, model_prob REAL, odds REAL);
    INSERT INTO tournaments VALUES (1, 'ITF W15 Somewhere'), (2, 'Challenger Lima');
    INSERT INTO matches VALUES (10, 1), (11, 2);
    """)
    rows = [(1, 10, "2026-11-25", "A vs B", "first_set_winner_99", 0.5, "A", 2.0, 0.5, 0.80, 0.5, "LOST", -1, '{"data_quality_score": 40}'),
            (2, 11, "2026-11-25", "C vs D", "player_game_handicap_3.5", 3.5, "C (+3.5)", 1.9, 0.55, 0.55, 0.55, "WON", 0.9, "{}"),
            (3, 11, "2026-11-24", "E vs F", "total_games", 22.5, "Over", 1.9, 0.5, 0.6, 0.5, "WON", 0.9, "{}"),
            (4, 11, "2026-11-25", "G vs H", "total_games", 22.5, "Over", 1.9, 0.5, 0.6, 0.5, "PENDING", 0, "{}")]
    con.executemany("INSERT INTO prop_tracker VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [(*r, 1) for r in rows])
    con.executemany("INSERT INTO featured_picks VALUES (?, ?, ?, ?)", [(1, 1, 0.75, 2.2), (2, 1, 0.70, 2.1)])
    con.commit()
    con.close()


def test_tennis_rows_use_raw_model_and_featured_frozen_prob(tmp_path):
    db = tmp_path / "t.db"
    _tennis_db(db)
    rows = S.tennis_rows("2026-11-25", 30, db)
    assert len(rows) == 3                    # PENDING、冇 model_prob_raw 唔計；精選兩行只計一次
    a = next(r for r in rows if r["key"] == 1)
    assert a["p_top3"] == 0.80 and a["m_top3"] == 0.5           # model_prob_raw，唔係收縮後 0.5
    assert a["tier"] == "ITF" and a["family"] == "首盤勝出" and a["featured"] and a["featured_prob"] == 0.75
    assert "featured:精選" in a["cohorts"] and "dq:資料質素 <50" in a["cohorts"]
    rv = S.tennis_review("2026-11-25", 30, db)
    assert rv["summary"]["props"] == 2
    (f,) = rv["featured"]
    assert f["p_model"] == 0.75 and f["odds"] == 2.2 and f["state"] == "lost" and f["miss"] == "輸入資料薄"
    assert rv["confident_total"] == 1 and rv["confident_miss_classes"] == {"輸入資料薄": 1}
    md = S.render_md(rv)
    assert "精選（紙上盤）：0/1 中" in md and "ITF" in md


def test_nba_review_assembles(monkeypatch):
    day = "2026-11-25"
    rows = [S._row(day, f"k{i}", 0.9, None, 0, ["market:得分"], game="DAL_DEN", player=f"P{i}", market="得分", line=5.0,
                   side="over", minutes=30.0, picked=False, raw_close=0.97) for i in range(3)]
    rows += [S._row("2026-11-20", f"o{i}", 0.5, 0.5, i % 2, ["market:得分"], game="X", player="Q", market="得分",
                    line=5.0, side="over", minutes=30.0, picked=False, raw_close=0.5) for i in range(40)]
    monkeypatch.setattr(S, "nba_rows", lambda d, t, root=None: (rows, {"counts": {}, "window": []}))
    monkeypatch.setattr(S, "nba_featured", lambda d: [{"event_name": "DAL @ DEN", "game_tag": "DAL_DEN", "odds": 1.8,
                                                       "p_model": 0.6, "p_fair": 0.52, "state": "lost", "profit": -1,
                                                       "legs": [{"player": "P0", "market": "pts", "stat": "PTS",
                                                                 "ou_line": 5.0, "side": "over"}]}])
    rv = S.nba_review(day, 30)
    assert rv["summary"]["legs"] == 3 and rv["confident_total"] == 3
    assert rv["confident_miss_classes"] == {"市場都估錯（未去水）": 3}
    assert rv["featured"][0]["miss"] == "模型判錯" and rv["featured_summary"]["pnl_units"] == -1
    assert rv["window"]["days"] == ["2026-11-20"]
    assert "NBA 自動覆盤" in S.render_md(rv) and "精選 0/1 中" in S.telegram_text(rv)


def test_scheduler_wiring():
    nba = (REPO / ".agents/skills/nba/nba_daily_auto/nba_daily_schedule.py").read_text(encoding="utf-8")
    assert "_post_review(target_date, log)" in nba and '"--domain", "nba"' in nba
    ten = (REPO / "tennis-wong-choi/scripts/tennis_daily_schedule.py").read_text(encoding="utf-8")
    assert "_post_review(yesterday)" in ten and '"--domain", "tennis"' in ten


def test_nba_featured_joins_ledger_leg_with_int_line(monkeypatch):
    day = "2026-11-25"
    leg = S._row(day, "k", 0.6, 0.55, 0, ["market:得分"], game="DAL_DEN", player="Daniel Gafford", market="得分",
                 line=9.5, side="under", minutes=8.0, picked=False, raw_close=0.55)
    leg5 = S._row(day, "k2", 0.6, 0.55, 0, ["market:助攻"], game="BOS_WAS", player="Paul George", market="助攻",
                  line=5.0, side="under", minutes=33.0, picked=False, raw_close=0.55)
    monkeypatch.setattr(S, "nba_rows", lambda d, t, root=None: ([leg, leg5], {"counts": {}, "window": []}))
    monkeypatch.setattr(S, "nba_featured", lambda d: [
        {"event_name": "DAL @ DEN", "game_tag": "DAL_DEN", "odds": 1.8, "p_model": 0.6, "p_fair": 0.52, "state": "lost",
         "profit": -1, "legs": [{"player": "Daniel Gafford ", "market": "pts", "ou_line": 9.5, "side": "under"}]},
        {"event_name": "BOS @ WAS", "game_tag": "BOS_WAS", "odds": 1.87, "p_model": 0.57, "p_fair": 0.5, "state": "lost",
         "profit": -1, "legs": [{"player": "Paul George", "market": "ast", "ou_line": 5, "side": "under"}]}])
    rv = S.nba_review(day, 30)
    assert rv["featured"][0]["minutes"] == 8.0 and rv["featured"][0]["miss"].startswith("上陣時間")   # 真配對到
    assert rv["featured"][1]["minutes"] == 33.0                                                       # 5 對 5.0


def test_nba_gap_uses_decision_price(monkeypatch):
    sys.path.insert(0, str(S.NBA_AUTO))
    import nba_market_ledger as ledger
    legs = [{"key": ("2026-11-25", "A", "P", "pts", 10, "over"), "p_final": 0.7,
             "market_devig_close": 0.68, "y": 1},
            {"key": ("2026-11-25", "A", "Q", "pts", 10, "over"), "p_final": 0.7,
             "market_devig_close": 0.68, "price_at_model": 2.0, "y": 0}]
    monkeypatch.setattr(ledger, "evaluate", lambda **kwargs: {"legs": legs})
    rows, _ = S.nba_rows("2026-11-25", 30)
    assert not any(c.startswith("gap:") for c in rows[0]["cohorts"])
    assert "gap:模型高過模型時隱含 ≥10pp" in rows[1]["cohorts"]
    assert rows[1]["m_top3"] == 0.68


def test_tennis_post_start_price_not_used_for_cohort(tmp_path):
    db = tmp_path / "t.db"
    _tennis_db(db)
    con = sqlite3.connect(db)
    con.execute("UPDATE prop_tracker SET is_point_in_time = 0 WHERE id = 1")
    con.commit()
    con.close()
    meta = {}
    rows = S.tennis_rows("2026-11-25", 30, db, meta=meta)
    assert all(r["key"] != 1 for r in rows)
    assert meta["excluded_non_point_in_time"] == 1
