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


def _mk_sgm_leg(player, market, line, state, actual, model_p, price, p_market=None, exp_min=28.0, l10=0.8):
    return {
        "player": player, "team": "MIL", "market": market, "category": market.upper(),
        "stat": market.upper(), "line": line, "side": "over", "state": state, "actual": actual,
        "model_probability": model_p, "price": price, "odds": price, "l10_hit_rate": l10,
        "selection": f"{player} (MIL) {market.upper()} {int(line)}+",
        "why": {
            "price": price,
            "p_market": p_market if p_market is not None else round(1.0 / price, 4),
            "p_final": model_p,
            "expect": {"minutes": exp_min},
        },
    }


def test_nba_sgm_review_combos_diagnosis_and_join():
    day = "2026-11-26"
    legs_by_key = {
        S._leg_key("A_B", "P1", "得分", 15, "over"): {"date": day, "minutes": 32.0, "m_top3": 0.75},
        S._leg_key("A_B", "P2", "籃板", 6, "over"): {"date": day, "minutes": 30.0, "m_top3": 0.65},
        S._leg_key("C_D", "P3", "三分", 1, "over"): {"date": day, "minutes": 10.0, "m_top3": 0.82},
        S._leg_key("C_D", "P4", "得分", 10, "over"): {"date": day, "minutes": 34.0, "m_top3": 0.70},
        S._leg_key("E_F", "P5", "助攻", 4, "over"): {"date": day, "minutes": 28.0, "m_top3": 0.52},
        S._leg_key("E_F", "P6", "pts", 20, "over"): {"date": day, "minutes": 36.0, "m_top3": 0.55},
    }
    records = [
        # 1) Won formal combo + morning update changed (21h version had line 3.0 -> would have lost since actual=2)
        {
            "id": "c1", "day": day, "event_name": "A @ B", "game_tag": "A_B",
            "tracking_kind": "formal", "odds": 2.4, "model_probability": 0.5, "state": "won", "profit": 1.4,
            "legs": [
                _mk_sgm_leg("P1", "pts", 15.0, "won", 18, 0.72, 1.5),
                _mk_sgm_leg("P2", "reb", 6.0, "won", 7, 0.68, 1.6),
            ],
            "morning_update": {
                "at": f"{day}T08:30:00+11:00",
                "from": {
                    "odds": 3.0,
                    "legs": [
                        {"player": "P1", "market": "pts", "line": 20.0},
                        {"player": "P2", "market": "reb", "line": 6.0},
                    ],
                },
            },
        },
        # 2) One-leg-away loss (P3 >= 0.80 busted on <15 min; weakest link P4 won -> bust_was_weakest_link=False)
        {
            "id": "c2", "day": day, "event_name": "C @ D", "game_tag": "C_D",
            "tracking_kind": "research", "odds": 2.1, "model_probability": 0.55, "state": "lost", "profit": -1.0,
            "legs": [
                _mk_sgm_leg("P3", "3pm", 1.0, "lost", 0, 0.84, 1.2, p_market=0.83, exp_min=25.0),
                _mk_sgm_leg("P4", "pts", 10.0, "won", 14, 0.70, 1.8, p_market=0.55, exp_min=30.0),
            ],
        },
        # 3) Two-leg bust (weakest link P5 lost on model error; P6 lost on market miss)
        {
            "id": "c3", "day": day, "event_name": "E @ F", "game_tag": "E_F",
            "tracking_kind": "research", "odds": 3.2, "model_probability": 0.35, "state": "lost", "profit": -1.0,
            "legs": [
                _mk_sgm_leg("P5", "ast", 4.0, "lost", 2, 0.62, 1.9, p_market=0.52),
                _mk_sgm_leg("P6", "pts", 20.0, "lost", 15, 0.75, 1.6, p_market=0.63),
            ],
        },
        # 4) Void combo (excluded from settled, counted in void)
        {
            "id": "c4", "day": day, "event_name": "G @ H", "game_tag": "G_H",
            "tracking_kind": "research", "odds": 2.5, "model_probability": 0.45, "state": "void", "profit": None,
            "legs": [_mk_sgm_leg("P7", "pts", 12.0, "void", "void", 0.70, 1.4)],
        },
        # 5) Trailing in-window formal win (10 days ago)
        {
            "id": "t1", "day": "2026-11-16", "event_name": "X @ Y", "game_tag": "X_Y",
            "tracking_kind": "formal", "odds": 2.0, "model_probability": 0.6, "state": "won", "profit": 1.0,
            "legs": [_mk_sgm_leg("PX", "pts", 10.0, "won", 12, 0.76, 1.4)],
        },
        # 6) Out-of-window record (40 days ago -> must NOT enter trailing_summary)
        {
            "id": "old1", "day": "2026-10-10", "event_name": "O @ P", "game_tag": "O_P",
            "tracking_kind": "formal", "odds": 5.0, "model_probability": 0.3, "state": "won", "profit": 4.0,
            "legs": [_mk_sgm_leg("PO", "pts", 10.0, "won", 15, 0.76, 1.4)],
        },
    ]

    sgm = S.nba_sgm_review(day, records, legs_by_key, trail_days=30)
    assert sgm["join"]["joined_legs"] == 6 and sgm["join"]["total_legs"] == 7
    assert sgm["join"]["join_rate"] == round(6 / 7, 4)

    c1, c2, c3, c4 = sgm["combos"]
    # c1 checks
    assert c1["kind_label"] == "正式"
    assert c1["implied_p"] == round(1 / 2.4, 4)
    assert c1["ev"] == round(0.5 * 2.4 - 1, 4)
    assert c1["product_leg_prices"] == round(1.5 * 1.6, 4)
    assert c1["correlation_discount"] == round(2.4 / (1.5 * 1.6), 4)
    assert c1["diagnosis"]["morning_update_changed"] is True
    assert c1["diagnosis"]["would_21h_version_have_won"] is False
    assert c1["diagnosis"]["bust_was_weakest_link"] is None
    assert c1["legs"][0]["margin"] == 3.0 and c1["legs"][0]["act_minutes"] == 32.0
    assert c1["legs"][0]["minutes_ratio"] == round(32.0 / 28.0, 3)

    # c2 checks: one-leg-away, weakest link (P4, 0.70) won while P3 (0.84) busted on minutes
    assert c2["kind_label"] == "紙上"
    assert c2["diagnosis"]["busted_legs"] == 1 and c2["diagnosis"]["one_leg_away"] is True
    assert c2["diagnosis"]["weakest_link"]["player"] == "P4"
    assert c2["diagnosis"]["bust_was_weakest_link"] is False
    assert c2["legs"][0]["miss"].startswith("上陣時間")
    assert c2["legs"][0]["minutes_ratio"] == round(10.0 / 25.0, 3)

    # c3 checks: two-leg bust, weakest link P5 busted
    assert c3["diagnosis"]["busted_legs"] == 2 and c3["diagnosis"]["one_leg_away"] is False
    assert c3["diagnosis"]["weakest_link"]["player"] == "P5"
    assert c3["diagnosis"]["bust_was_weakest_link"] is True
    assert c3["legs"][0]["miss"] == "模型判錯"
    # 去水市場 0.55（<0.60）先算；單邊含抽水 0.63 唔可以當去水用（Hydrogen 2026-11-27）
    assert c3["legs"][1]["miss"] == "模型判錯"

    # day summary arithmetic (settled = c1, c2, c3; c4 void excluded from settled)
    ds = sgm["day_summary"]
    assert ds["combos"] == 4 and ds["settled"] == 3 and ds["won"] == 1 and ds["lost"] == 2 and ds["void"] == 1
    assert ds["hit_rate"] == round(1 / 3, 4)
    assert ds["pnl_units"] == round(1.4 - 1.0 - 1.0, 2)
    assert ds["roi"] == round(-0.6 / 3, 4)
    assert ds["one_leg_away"] == 1 and ds["one_leg_away_share"] == 0.5
    assert ds["bust_legs_total"] == 3 and ds["bust_p80_plus"] == 1
    assert ds["bust_by_market"] == {"三分": 1, "助攻": 1, "得分": 1}
    assert ds["bust_by_p_band"] == {"<70%": 1, "70–80%": 1, "≥80%": 1}
    assert ds["formal"]["combos"] == 1 and ds["formal"]["won"] == 1 and ds["formal"]["pnl_units"] == 1.4
    assert ds["research"]["combos"] == 3 and ds["research"]["settled"] == 2 and ds["research"]["void"] == 1

    # trailing summary excludes old1 (40 days ago) and includes t1 + day
    ts = sgm["trailing_summary"]
    assert ts["combos"] == 5 and ts["settled"] == 4 and ts["won"] == 2 and ts["lost"] == 2 and ts["void"] == 1
    assert ts["pnl_units"] == round(1.4 - 1.0 - 1.0 + 1.0, 2)
    assert ts["formal"]["settled"] == 2 and ts["formal"]["won"] == 2 and ts["formal"]["pnl_units"] == 2.4


def test_nba_review_wires_sgm_cohort_md_and_no_telegram(monkeypatch):
    day = "2026-11-26"
    rows = [
        S._row(day, f"k{i}", 0.75, 0.70, i % 2, ["market:得分"], game="DAL_DEN", player=f"P{i}",
               market="得分", line=10.0, side="over", minutes=30.0, raw_close=0.70)
        for i in range(4)
    ] + [
        S._row(f"2026-11-{10 + d}", f"t{d}_{i}", 0.85, 0.70, 0, ["market:得分"], game="DAL_DEN", player=f"P{i}",
               market="得分", line=10.0, side="over", minutes=30.0, raw_close=0.70)
        for d in range(8) for i in range(4)
    ]
    sgm_recs = [
        {
            "id": "s1", "day": day, "event_name": "DAL @ DEN", "game_tag": "DAL_DEN",
            "tracking_kind": "research", "odds": 2.2, "model_probability": 0.48, "state": "lost", "profit": -1.0,
            "legs": [_mk_sgm_leg(f"P{i}", "pts", 10.0, "won" if i % 2 else "lost", 12 if i % 2 else 8, 0.75, 1.3)
                     for i in range(4)],
        }
    ] + [
        {
            "id": f"st{d}", "day": f"2026-11-{10 + d}", "event_name": "DAL @ DEN", "game_tag": "DAL_DEN",
            "tracking_kind": "research", "odds": 2.2, "model_probability": 0.50, "state": "lost", "profit": -1.0,
            "legs": [_mk_sgm_leg(f"P{i}", "pts", 10.0, "lost", 8, 0.85, 1.2) for i in range(4)],
        }
        for d in range(8)
    ]
    monkeypatch.setattr(S, "nba_rows", lambda d, t, root=None: (rows, {"counts": {}, "window": []}))
    monkeypatch.setattr(S, "nba_featured", lambda d: [])

    rv = S.nba_review(day, 30, sgm_loader=lambda: sgm_recs)
    assert "sgm" in rv and rv["sgm"]["day_summary"]["combos"] == 1
    picked_cohorts = [c for c in rv["cohorts"] if c["cohort"].startswith("picked:")]
    assert len(picked_cohorts) == 1
    assert picked_cohorts[0]["cohort"] == "picked:SGM 組合腿"
    assert picked_cohorts[0]["today_n"] == 4 and picked_cohorts[0]["trail_n"] == 32

    md = S.render_md(rv)
    assert "SGM 組合覆盤（正式停損中＝紙上）" in md
    assert "DAL @ DEN" in md and "✓" in md and "✗" in md
    tg = S.telegram_text(rv)
    assert "SGM" not in tg and "組合腿" not in tg


def test_sgm_loader_not_called_under_pytest_without_injection(monkeypatch):
    import types
    called = []
    fake_mod = types.ModuleType("services.nba_tracking")
    fake_mod.export_tracking = lambda root: called.append(root) or {"records": []}
    fake_pkg = types.ModuleType("services")
    fake_pkg.nba_tracking = fake_mod
    monkeypatch.setitem(sys.modules, "services", fake_pkg)
    monkeypatch.setitem(sys.modules, "services.nba_tracking", fake_mod)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_sgm_loader_not_called")

    assert S.nba_sgm_records() == []
    assert called == []
