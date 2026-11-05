"""The ledger's write rules, readiness, and what reaches Telegram / the report."""
from __future__ import annotations

import json

import pytest

from conftest import configure_test_db

START = "2026-11-07T10:00:00Z"


@pytest.fixture
def conn(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.store.db import get_connection
    from tennis_wc.store.migrations import init_db

    init_db()
    c = get_connection()
    c.execute("INSERT INTO players (id,name,tour,source_provider,created_at,updated_at) "
              "VALUES (1,'Ann','WTA','t','now','now'),(2,'Bea','WTA','t','now','now')")
    c.execute("INSERT INTO matches (id,provider_match_id,tour,match_date,tournament_id,player_a_id,"
              "player_b_id,round,source_provider,created_at,updated_at,start_time_utc) "
              "VALUES (1,'m','WTA','2026-11-07',1,1,2,'R1','t','now','now',?)", (START,))
    c.commit()
    yield c
    c.close()


def _row(**over):
    row = dict(match_id=1, match_date="2026-11-07", match_label="Ann vs Bea",
               market_key="first_set_winner_1", line=0.5, selection="Ann", side="over",
               prop_scope="player_first_set", subject_player_id=1, decimal_odds=2.2,
               model_prob=0.47, model_prob_raw=0.55, temper_strength=0.9, market_prob_fair=0.45,
               blended_prob=0.47, edge=0.1, ev=0.21, predicted_mean=0.55, stake_units=1.0,
               is_value=True, feed_market_key="winner_related", feed_market_name="Set 1 Winner",
               feed_selection_name="Ann", feed_line=None,
               pricing_evidence_json=json.dumps({"version": 1, "source_quality": 0.8}))
    row.update(over)
    return row


def test_a_post_start_write_never_replaces_a_pre_match_price(conn):
    from tennis_wc.store.ledger import record_rows

    record_rows(conn, [_row()], "2026-11-07T08:00:00Z")
    record_rows(conn, [_row(decimal_odds=1.5)], "2026-11-07T11:00:00Z")
    row = conn.execute("SELECT decimal_odds, is_point_in_time FROM prop_tracker").fetchone()
    assert (row[0], row[1]) == (2.2, 1)


def test_a_settled_row_is_never_repriced(conn):
    from tennis_wc.store.ledger import record_rows

    record_rows(conn, [_row()], "2026-11-07T08:00:00Z")
    conn.execute("UPDATE prop_tracker SET result_status='WON'")
    record_rows(conn, [_row(decimal_odds=1.5)], "2026-11-07T09:00:00Z")
    assert conn.execute("SELECT decimal_odds FROM prop_tracker").fetchone()[0] == 2.2


@pytest.mark.parametrize("bad", [dict(subject_player_id=99), dict(match_id=42)])
def test_rows_outside_the_fixture_are_refused(conn, bad):
    from tennis_wc.store.ledger import record_rows

    with pytest.raises(ValueError):
        record_rows(conn, [_row(**bad)], "2026-11-07T08:00:00Z")


def test_family_weight_learns_only_from_point_in_time_quality_rows_before_the_date(conn):
    from tennis_wc.model.market import DEFAULT_MODEL_WEIGHT, family_weight
    from tennis_wc.store.ledger import record_rows

    rows = [_row(selection=f"Ann {i}", model_prob_raw=0.7, market_prob_fair=0.5) for i in range(25)]
    record_rows(conn, rows, "2026-11-07T08:00:00Z")
    conn.execute("UPDATE prop_tracker SET result_status='WON', settled_at='2026-11-07T20:00:00Z'")
    assert family_weight(conn, "first_set_winner", "2026-11-07") == DEFAULT_MODEL_WEIGHT  # not before the date
    learnt = family_weight(conn, "first_set_winner", "2026-11-08")
    assert learnt == pytest.approx(1.0 * 25 / 125)  # all won: slope clipped at 1, shrunk by n/(n+100)
    conn.execute("UPDATE prop_tracker SET pricing_evidence_json=NULL")
    assert family_weight(conn, "first_set_winner", "2026-11-08") == DEFAULT_MODEL_WEIGHT


@pytest.mark.parametrize("payload,horizon,severity", [
    ({"odds_coverage": {"fixtures": 30, "priced_matches": 25}, "matches_analysed": 25, "valid_feature_snapshots": 25}, "same_day", "ok"),
    ({"odds_coverage": {"fixtures": 30, "priced_matches": 2}, "matches_analysed": 2, "valid_feature_snapshots": 2}, "next_day", "expected_empty"),
    ({"odds_coverage": {"fixtures": 30, "priced_matches": 2}, "matches_analysed": 2, "valid_feature_snapshots": 2}, "same_day", "retry"),
    ({"odds_coverage": {"fixtures": 30, "priced_matches": 0}, "matches_analysed": 0, "valid_feature_snapshots": 0}, "same_day", "error"),
    ({"odds_coverage": {"fixtures": 30, "priced_matches": 25}, "matches_analysed": 25, "valid_feature_snapshots": 25,
      "source_errors": [{"source": "odds", "error": "dns"}]}, "next_day", "error"),
])
def test_readiness(payload, horizon, severity):
    from tennis_wc.run import readiness

    assert readiness(payload, horizon=horizon)["severity"] == severity


def _featured(conn, n=1, status="PENDING"):
    from tennis_wc.store.ledger import record_rows

    record_rows(conn, [_row(selection=f"Ann {i}", match_id=1) for i in range(n)], "2026-11-06T10:00:00Z")
    conn.execute("UPDATE prop_tracker SET result_status=?", (status,))
    conn.commit()


def test_main_card_is_sent_even_with_no_picks(conn, monkeypatch):
    from tennis_wc.publish import telegram

    sent = []
    monkeypatch.setenv("TENNIS_NOTIFY_BETS", "1")
    monkeypatch.setattr(telegram, "notify", lambda text, audience="primary": sent.append((audience, text)))
    assert telegram.publish_featured("2026-11-07", "21:00", main=True) == []
    assert sent and sent[0][0] == "content" and "暫時無精選" in sent[0][1]


def test_top_up_sends_only_when_new_picks_and_respects_the_switch(conn, monkeypatch):
    from tennis_wc.publish import telegram
    from tennis_wc.select import featured

    sent = []
    monkeypatch.setattr(telegram, "notify", lambda text, audience="primary": sent.append(text))
    monkeypatch.setattr(featured, "record", lambda c, d, label, now=None: [])
    monkeypatch.setenv("TENNIS_NOTIFY_BETS", "1")
    telegram.publish_featured("2026-11-07", "23:00", main=False)
    assert sent == [], "no new picks, no message"
    monkeypatch.setattr(featured, "record", lambda c, d, label, now=None: [{"prop_id": 1}])
    monkeypatch.delenv("TENNIS_NOTIFY_BETS")
    telegram.publish_featured("2026-11-07", "23:00", main=False)
    assert sent == [], "TENNIS_NOTIFY_BETS off: nothing is sent"


def test_forward_milestone_is_sent_once(conn, monkeypatch, tmp_path):
    from tennis_wc.publish import telegram
    from tennis_wc.select import featured

    sent = []
    monkeypatch.setattr(telegram, "notify", lambda text, audience="primary": sent.append(audience) or True)
    monkeypatch.setattr(featured, "picks_with_results", lambda c, **k: [])
    monkeypatch.setattr(featured, "performance",
                        lambda rows: {"settled": 251, "wins": 130, "roi": 0.05, "ci_low": -0.02, "ci_high": 0.12})
    assert telegram.forward_milestone(tmp_path) == "CONTINUE_TO_600"
    assert telegram.forward_milestone(tmp_path) is None
    assert sent == ["primary"]


def test_report_lists_featured_first_and_value_props(conn, monkeypatch, tmp_path):
    from tennis_wc.publish import report

    _featured(conn)
    conn.execute("INSERT INTO featured_picks (prop_id,match_id,match_date,rank,run_label,market_key,selection,"
                 "match_label,feed_market_name,feed_selection_name,start_time_utc,odds,edge,featured_at) "
                 "VALUES (1,1,'2026-11-07',1,'21:00','first_set_winner_1','Ann','Ann vs Bea','Set 1 Winner',"
                 "'Ann',?,2.2,0.1,'now')", (START,))
    conn.commit()
    text = report.render("2026-11-07")
    assert text.index("精選 1／10") < text.index("其他 value props")
    assert "#1 Ann vs Bea｜Set 1 Winner → Ann｜賠率 2.20" in text
    assert "首盤勝方" in text


def test_weekly_counts_picks_by_run_and_price_move(conn):
    from tennis_wc.publish.weekly import weekly_text

    _featured(conn, n=1)
    conn.execute("INSERT INTO featured_picks (prop_id,match_id,match_date,rank,run_label,market_key,selection,"
                 "match_label,feed_market_name,feed_selection_name,start_time_utc,odds,featured_at) "
                 "VALUES (1,1,'2026-11-07',1,'21:00','first_set_winner_1','Ann','Ann vs Bea','Set 1 Winner',"
                 "'Ann',?,2.2,'now')", (START,))
    conn.execute("INSERT INTO market_odds_snapshots (event_id,match_id,bookmaker,market_key,market_name,"
                 "selection_name,line,odds,source_provider,raw_response_id,fetched_at,created_at) "
                 "VALUES ('e',1,'sportsbet','winner_related','Set 1 Winner','Ann',NULL,2.0,'sportsbet',0,"
                 "'2026-11-07T09:00:00Z','now')")
    conn.commit()
    text = weekly_text("2026-11-08")
    assert "21:00 1" in text and "21:00 佔 100%" in text
    assert "平均 -9.1%" in text


def test_a_priced_family_going_silent_is_flagged_but_paused_ones_are_not(conn):
    from tennis_wc.monitor import silent_prop_families

    for day in range(1, 10):
        for key in ("first_set_winner_1", "player_aces_1_5.5"):
            conn.execute("INSERT INTO prop_tracker (prop_key,match_id,match_date,match_label,market_key,line,"
                         "selection,decimal_odds,stake_units,is_value,result_status,recorded_at,updated_at) "
                         "VALUES (?,1,?,'x',?,0.5,'s',2.0,0,0,'PENDING','now','now')",
                         (f"{key}-{day}", f"2026-10-{day:02d}", key))
    conn.execute("INSERT INTO prop_tracker (prop_key,match_id,match_date,match_label,market_key,line,selection,"
                 "decimal_odds,stake_units,is_value,result_status,recorded_at,updated_at) "
                 "VALUES ('alive',1,'2026-10-14','x','player_set_handicap_1.5',0.5,'s',2.0,0,0,'PENDING','now','now')")
    alerts = silent_prop_families(conn, "2026-10-14")
    assert [a["family"] for a in alerts] == ["first_set_winner"]
