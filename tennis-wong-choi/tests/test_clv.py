from __future__ import annotations


def test_clv_placeholder_imports():
    from tennis_wc.betting.clv import calculate_clv, clv_label

    assert round(calculate_clv(2.1, 2.0), 3) == 0.05
    assert clv_label(0.01) == "POSITIVE"


def test_prop_value_bets_reach_the_clv_tracker(tmp_path, monkeypatch):
    """Props were the one thing CLV did not cover, and the only thing staked.

    Measured 2026-08-11: clv_tracker held 420 MARKET_LEG rows and 307
    MATCH_PREDICTION rows and ZERO props, while that day's card produced 33
    value props. CLV is the only read available before results arrive, so during
    a go-live period it is the instrument -- if the picks do not beat the close,
    the replayed ROI will not survive contact with the book.
    """
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.betting.ledger import get_connection, sync_clv_tracker_for_date

    init_db()
    conn = get_connection()
    conn.execute(
        """INSERT INTO players (id, name, tour, source_provider, created_at, updated_at)
           VALUES (1,'A','ATP','test','now','now'), (2,'B','ATP','test','now','now')"""
    )
    conn.execute(
        """INSERT INTO matches (id, provider_match_id, tour, match_date, tournament_id,
               player_a_id, player_b_id, round, source_provider, created_at,
               updated_at, start_time_utc)
           VALUES (7,'M7','ATP','2026-08-11',1,1,2,'R1','test','now','now',
                   '2026-08-11T12:00:00Z')"""
    )
    # The bet we took, carrying the FEED's own identifiers.
    conn.execute(
        """INSERT INTO prop_tracker
           (prop_key, match_id, match_date, match_label, market_key, line, selection,
            side, prop_scope, subject_player_id, decimal_odds, model_prob,
            model_prob_raw, market_prob_fair, blended_prob, edge, ev, predicted_mean,
            stake_units, is_value, result_status, recorded_at, updated_at,
            feed_market_key, feed_market_name, feed_selection_name, feed_line)
           VALUES ('7|player_win_a_set_1|Yes',7,'2026-08-11','A vs B',
                   'player_win_a_set_1',0.5,'Yes','over','player_win_set',1,
                   2.00,0.55,0.56,0.50,0.54,0.06,0.12,0.0,1.0,1,'PENDING',
                   'now','now','win_a_set','To Win At Least One Set',
                   'A To Win At Least One Set',NULL)"""
    )
    # A bet with no feed identity: must be counted, never guessed at.
    conn.execute(
        """INSERT INTO prop_tracker
           (prop_key, match_id, match_date, match_label, market_key, line, selection,
            side, prop_scope, subject_player_id, decimal_odds, model_prob,
            model_prob_raw, market_prob_fair, blended_prob, edge, ev, predicted_mean,
            stake_units, is_value, result_status, recorded_at, updated_at)
           VALUES ('7|player_game_handicap_2.5|A (+2.5)',7,'2026-08-11','A vs B',
                   'player_game_handicap_2.5',-2.5,'A (+2.5)','over',
                   'player_game_margin',1,1.90,0.58,0.59,0.52,0.57,0.07,0.12,0.0,
                   1.0,1,'PENDING','now','now')"""
    )
    # Two snapshots of the same selection; the LATEST is the close.
    for fetched, odds in (("2026-08-11T00:00:00Z", 2.00),
                          ("2026-08-11T09:00:00Z", 1.70)):
        conn.execute(
            """INSERT INTO market_odds_snapshots
               (match_id, event_id, bookmaker, market_key, market_name,
                selection_name, line, odds, source_provider, raw_response_id,
                fetched_at, created_at)
               VALUES (7,'E7','sportsbet','win_a_set','To Win At Least One Set',
                       'A To Win At Least One Set',NULL,?,'sportsbet',0,?,?)""",
            (odds, fetched, fetched),
        )
    conn.commit()

    summary = sync_clv_tracker_for_date("2026-08-11")
    assert summary["props_synced"] == 1
    assert summary["props_without_feed_identity"] == 1, (
        "a bet with no bookmaker identifier must be reported, not resolved by guesswork"
    )

    row = get_connection().execute(
        "SELECT * FROM clv_tracker WHERE recommendation_type='PROP_RECOMMENDATION'"
    ).fetchone()
    assert row is not None
    assert row["odds_taken"] == 2.00
    # Took 2.00, closed 1.70 -- the price shortened, so the bet beat the close.
    assert row["closing_odds"] == 1.70
    assert row["clv"] is not None and row["clv"] > 0


def test_the_feed_market_key_alone_is_not_an_identity(tmp_path, monkeypatch):
    """`winner_related` is several markets, and matching on it alone lied.

    On 2026-08-11 the closing-price lookup matched (match_id, market_key,
    selection_name) and found "Marco Cecchinato" in a DIFFERENT market of the
    same fixture -- eight snapshots shared that name, four on one timestamp --
    reporting +74.66% CLV on a bet whose price had not moved. Caught only
    because a number too good to be true is treated as a bug until shown
    otherwise. The market NAME is part of the identity.
    """
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.betting.ledger import get_connection, sync_clv_tracker_for_date

    init_db()
    conn = get_connection()
    conn.execute(
        """INSERT INTO players (id, name, tour, source_provider, created_at, updated_at)
           VALUES (1,'Marco','ATP','test','now','now'), (2,'B','ATP','test','now','now')"""
    )
    conn.execute(
        """INSERT INTO matches (id, provider_match_id, tour, match_date, tournament_id,
               player_a_id, player_b_id, round, source_provider, created_at,
               updated_at, start_time_utc)
           VALUES (9,'M9','ATP','2026-08-11',1,1,2,'R1','test','now','now',
                   '2026-08-11T12:00:00Z')"""
    )
    conn.execute(
        """INSERT INTO prop_tracker
           (prop_key, match_id, match_date, match_label, market_key, line, selection,
            side, prop_scope, subject_player_id, decimal_odds, model_prob,
            model_prob_raw, market_prob_fair, blended_prob, edge, ev, predicted_mean,
            stake_units, is_value, result_status, recorded_at, updated_at,
            feed_market_key, feed_market_name, feed_selection_name, feed_line)
           VALUES ('9|first_set_winner_1|Marco',9,'2026-08-11','Marco vs B',
                   'first_set_winner_1',0.5,'Marco','over','player_first_set',1,
                   2.55,0.42,0.43,0.39,0.41,0.04,0.09,0.0,1.0,1,'PENDING','now','now',
                   'winner_related','Set 1 Winner','Marco',NULL)"""
    )
    # Same key, same selection name, two DIFFERENT markets. Only one is ours.
    for market_name, odds in (("Set 1 Winner", 2.50), ("Match Winner", 1.46)):
        conn.execute(
            """INSERT INTO market_odds_snapshots
               (match_id, event_id, bookmaker, market_key, market_name,
                selection_name, line, odds, source_provider, raw_response_id,
                fetched_at, created_at)
               VALUES (9,'E9','sportsbet','winner_related',?,'Marco',NULL,?,
                       'sportsbet',0,'2026-08-11T09:00:00Z','2026-08-11T09:00:00Z')""",
            (market_name, odds),
        )
    conn.commit()

    sync_clv_tracker_for_date("2026-08-11")
    row = get_connection().execute(
        "SELECT closing_odds FROM clv_tracker "
        "WHERE recommendation_type='PROP_RECOMMENDATION'"
    ).fetchone()
    assert row["closing_odds"] == 2.50, (
        "matched the match-winner price instead of the first-set price we bet"
    )


def test_an_in_running_price_is_never_the_close(tmp_path, monkeypatch):
    """The close is the last snapshot BEFORE the match started.

    Nothing enforced that until 2026-08-11. Measured on the live database:
    2,919 of 120,004 snapshots (2.4%) were fetched after the match DATE, and 257
    selections swing more than threefold inside their own history -- 1.19 ->
    67.00, 1.26 -> 41.00 -- which is the middle of a set, not pre-match drift.
    `weekly_review` had already disabled CLV as a gate for exactly this reason,
    and the audit traced a +58% ROI result to the same prices.

    The provider sends `start_time_utc` in both the listing and the per-event
    payload; nothing stored it. Now it does, and no start time means no CLV --
    reporting nothing beats reporting a price from the second set, because the
    only value CLV has during a go-live period is being believed.
    """
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.betting.ledger import get_connection, sync_clv_tracker_for_date

    init_db()
    conn = get_connection()
    conn.execute(
        """INSERT INTO players (id, name, tour, source_provider, created_at, updated_at)
           VALUES (1,'A','ATP','test','now','now'), (2,'B','ATP','test','now','now')"""
    )
    conn.execute(
        """INSERT INTO matches (id, provider_match_id, tour, match_date, tournament_id,
               player_a_id, player_b_id, round, source_provider, created_at,
               updated_at, start_time_utc)
           VALUES (11,'M11','ATP','2026-08-11',1,1,2,'R1','test','now','now',
                   '2026-08-11T12:00:00Z')"""
    )
    conn.execute(
        """INSERT INTO prop_tracker
           (prop_key, match_id, match_date, match_label, market_key, line, selection,
            side, prop_scope, subject_player_id, decimal_odds, model_prob,
            model_prob_raw, market_prob_fair, blended_prob, edge, ev, predicted_mean,
            stake_units, is_value, result_status, recorded_at, updated_at,
            feed_market_key, feed_market_name, feed_selection_name, feed_line)
           VALUES ('11|player_win_a_set_1|Yes',11,'2026-08-11','A vs B',
                   'player_win_a_set_1',0.5,'Yes','over','player_win_set',1,
                   2.00,0.55,0.56,0.50,0.54,0.06,0.12,0.0,1.0,1,'PENDING','now','now',
                   'win_a_set','To Win At Least One Set','A Yes',NULL)"""
    )
    for fetched, odds in (
        ("2026-08-11T09:00:00Z", 2.00),   # pre-match
        ("2026-08-11T11:30:00Z", 1.80),   # the real close
        ("2026-08-11T13:15:00Z", 21.00),  # a set down: in-running
    ):
        conn.execute(
            """INSERT INTO market_odds_snapshots
               (match_id, event_id, bookmaker, market_key, market_name,
                selection_name, line, odds, source_provider, raw_response_id,
                fetched_at, created_at)
               VALUES (11,'E11','sportsbet','win_a_set','To Win At Least One Set',
                       'A Yes',NULL,?,'sportsbet',0,?,?)""",
            (odds, fetched, fetched),
        )
    conn.commit()

    sync_clv_tracker_for_date("2026-08-11")
    row = get_connection().execute(
        "SELECT closing_odds FROM clv_tracker "
        "WHERE recommendation_type='PROP_RECOMMENDATION'"
    ).fetchone()
    assert row["closing_odds"] == 1.80, (
        "took the 21.00 in-running price as the close" if row["closing_odds"] == 21.00
        else f"unexpected close {row['closing_odds']}"
    )

    # And with no start time there is no close at all, rather than a guess.
    conn = get_connection()
    conn.execute("UPDATE matches SET start_time_utc = NULL WHERE id = 11")
    conn.execute("DELETE FROM clv_tracker")
    conn.commit()
    sync_clv_tracker_for_date("2026-08-11")
    row = get_connection().execute(
        "SELECT closing_odds, clv FROM clv_tracker "
        "WHERE recommendation_type='PROP_RECOMMENDATION'"
    ).fetchone()
    assert row is not None, "the bet is still tracked"
    assert row["closing_odds"] is None and row["clv"] is None, (
        "no start time must mean no close, not a guess at one"
    )


def test_prop_settlement_is_copied_to_its_clv_row(tmp_path, monkeypatch):
    """The prop tracker is the settlement authority for PROP_RECOMMENDATION.

    The live database held 265 rows where the linked prop was already
    WON/LOST/VOID but the CLV row was still PENDING.  Re-deriving a player prop
    from the feed identity loses the synthetic prop scope/subject orientation;
    the tracker row already contains the exact graded selection and P/L.
    """
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.betting.ledger import get_connection, settle_clv_tracker_for_date

    init_db()
    conn = get_connection()
    conn.execute(
        """INSERT INTO prop_tracker
           (id, prop_key, match_id, match_date, match_label, market_key, line,
            selection, decimal_odds, model_prob, market_prob_fair, blended_prob,
            edge, ev, predicted_mean, stake_units, is_value, result_status,
            profit_loss_units, recorded_at, updated_at, settled_at, side,
            prop_scope, subject_player_id)
           VALUES (41,'41|game_handicap|A +2.5',7,'2026-08-20','A vs B',
                   'player_game_handicap_2.5',-2.5,'A (+2.5)',2.10,0.55,0.48,
                   0.53,0.07,0.15,1.5,1.0,1,'WON',1.10,'now','now','now',
                   'over','player_game_margin',1)"""
    )
    conn.execute(
        """INSERT INTO clv_tracker
           (recommendation_type, source_id, match_id, match_date, selection_name,
            selection_side, market_key, market_name, market_line, tier,
            model_probability, edge, confidence, odds_taken, result_status,
            profit_loss_units, recorded_at, updated_at)
           VALUES ('PROP_RECOMMENDATION',41,7,'2026-08-20','A (+2.5)','over',
                   'game_handicap','Game Handicap',-2.5,'PROP',0.55,0.07,NULL,
                   2.10,'PENDING',NULL,'now','now')"""
    )
    conn.commit()

    summary = settle_clv_tracker_for_date('2026-08-20')
    row = get_connection().execute(
        "SELECT result_status,profit_loss_units FROM clv_tracker "
        "WHERE recommendation_type='PROP_RECOMMENDATION' AND source_id=41"
    ).fetchone()

    assert summary["prop_linked_settled"] == 1
    assert (row["result_status"], row["profit_loss_units"]) == ("WON", 1.10)


def test_void_prop_is_copied_to_its_clv_row(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.migrations import init_db
    from tennis_wc.betting.ledger import get_connection, settle_clv_tracker_for_date

    init_db()
    conn = get_connection()
    conn.execute(
        """INSERT INTO prop_tracker
           (id, prop_key, match_id, match_date, match_label, market_key, line,
            selection, decimal_odds, stake_units, is_value, result_status,
            profit_loss_units, recorded_at, updated_at, settled_at, side,
            prop_scope)
           VALUES (42,'42|first_set|A',8,'2026-08-20','A vs B',
                   'first_set_winner_1',0.5,'A',1.90,1.0,1,'VOID',0.0,
                   'now','now','now','over','player_first_set')"""
    )
    conn.execute(
        """INSERT INTO clv_tracker
           (recommendation_type, source_id, match_id, match_date, selection_name,
            market_key, market_name, tier, odds_taken, result_status,
            recorded_at, updated_at)
           VALUES ('PROP_RECOMMENDATION',42,8,'2026-08-20','A',
                   'winner_related','Set 1 Winner','PROP',1.90,'PENDING',
                   'now','now')"""
    )
    conn.commit()

    summary = settle_clv_tracker_for_date('2026-08-20')
    row = get_connection().execute(
        "SELECT result_status,profit_loss_units FROM clv_tracker "
        "WHERE recommendation_type='PROP_RECOMMENDATION' AND source_id=42"
    ).fetchone()

    assert summary["prop_linked_voided"] == 1
    assert (row["result_status"], row["profit_loss_units"]) == ("VOID", 0.0)
