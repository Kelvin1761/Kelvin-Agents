"""2026-08-23 ace market rename (EXP-20261015-01 finding E). Temp DB only.

Sportsbet replaced `total_aces_in_the_match` with `total_aces` and the player
Over/Under markets with per-player N+ ladders (`<player>_aces`). The pricer
knew only the old keys, so the ace families went to zero rows silently.
"""
from __future__ import annotations

import pytest

DATE = "2026-09-10"


@pytest.fixture()
def db(tmp_path, monkeypatch):
    from conftest import configure_test_db

    configure_test_db(tmp_path, monkeypatch)
    from tennis_wc.database.db import get_connection
    from tennis_wc.database.migrations import init_db

    init_db()
    conn = get_connection()
    conn.execute(
        """INSERT INTO players (id, name, tour, source_provider, created_at, updated_at)
           VALUES (1,'Ben Shelton','ATP','t','now','now'),
                  (2,'Karen Khachanov','ATP','t','now','now'),
                  (3,'Opp One','ATP','t','now','now')"""
    )
    conn.execute(
        """INSERT INTO matches (id, provider_match_id, tour, match_date, tournament_id,
               player_a_id, player_b_id, round, source_provider, created_at,
               updated_at, start_time_utc)
           VALUES (50,'M50','ATP',?,1,1,2,'R1','t','now','now','2026-09-10T08:00:00Z')""",
        (DATE,),
    )
    for i in range(12):
        for pid, aces in ((1, 14), (2, 8)):
            conn.execute(
                """INSERT INTO player_match_history (provider_match_id, player_id,
                       opponent_id, tour, match_date, surface, tournament_external_id,
                       tournament_level, round, format, won, ace_count,
                       service_games_played, source_provider, raw_response_id, created_at)
                   VALUES (?, ?, 3, 'ATP', ?, 'Hard', 'T', 'A', 'R1', 'BO3', 1, ?, 12,
                           'jeff_sackmann', 0, 'now')""",
                (f"h{pid}-{i}", pid, f"2026-08-{10 + i:02d}", aces),
            )
    rungs = [("total_aces", "Total Aces", "Zero", None, 34.0)] + [
        ("total_aces", "Total Aces", f"{n}+", float(n), odds)
        for n, odds in ((15, 1.6), (19, 2.4), (23, 4.0), (40, 51.0))
    ] + [("ben_shelton_aces", "Ben Shelton Aces", "Zero", None, 41.0)] + [
        ("ben_shelton_aces", "Ben Shelton Aces", f"{n}+", float(n), odds)
        for n, odds in ((9, 1.5), (13, 2.6), (17, 5.0))
    ] + [("set_1_aces", "Set 1 Aces", "3+", 3.0, 1.7)]
    for key, name, sel, line, odds in rungs:
        conn.execute(
            """INSERT INTO market_odds_snapshots (event_id, match_id, bookmaker, market_key,
                   market_name, selection_name, selection_side, line, odds,
                   source_provider, raw_response_id, fetched_at, created_at)
               VALUES ('E50', 50, 'sportsbet', ?, ?, ?, NULL, ?, ?, 'sportsbet', 0,
                       '2026-09-09T23:00:00Z', '2026-09-09T23:00:00Z')""",
            (key, name, sel, line, odds),
        )
    conn.commit()
    return conn


def test_new_ladders_are_priced_model_only_and_logged(db):
    from tennis_wc.database.db import get_connection
    from tennis_wc.props.daily import price_ace_props_for_date
    from tennis_wc.props.registry import family_for_market

    conn = get_connection()
    boards = price_ace_props_for_date(conn, DATE, log=True)
    legs = [leg for b in boards for leg in b.unvalidated_ladder_legs]
    assert {leg["scope"] for leg in legs} == {"match", "player"}
    assert all(leg["line"] != 40.0 for leg in legs), "longshot rung outside the trust range"
    assert not any(leg["feed_market_key"] == "set_1_aces" for leg in legs)
    match = sorted((leg for leg in legs if leg["scope"] == "match"), key=lambda l: l["line"])
    probs = [leg["model_prob"] for leg in match]
    assert probs == sorted(probs, reverse=True), "P(X >= N) must fall as N rises"
    player = [leg for leg in legs if leg["scope"] == "player"]
    assert {leg["subject_player_id"] for leg in player} == {1}

    rows = conn.execute(
        "SELECT * FROM prop_tracker WHERE market_key LIKE '%aces_ladder%'").fetchall()
    assert len(rows) == len(legs)
    for row in rows:
        assert row["stake_units"] == 0 and row["is_value"] == 0, "never staked"
        assert row["market_prob_fair"] is None, "no validated ladder de-vig"
        assert row["side"] == "over" and row["selection"].endswith("+")
        assert row["feed_market_key"] in {"total_aces", "ben_shelton_aces"}
        assert family_for_market(row["market_key"]) in {"match_total_aces", "player_aces"}


def test_ladder_rows_settle_as_at_least_n(db):
    from tennis_wc.database.db import get_connection
    from tennis_wc.props.daily import price_ace_props_for_date

    conn = get_connection()
    price_ace_props_for_date(conn, DATE, log=True)
    row = conn.execute(
        "SELECT line, side FROM prop_tracker WHERE market_key='total_aces_ladder' "
        "ORDER BY line LIMIT 1").fetchone()
    # settle_props grades `actual >= line` for side 'over': exactly P(X >= N).
    assert row["side"] == "over" and float(row["line"]).is_integer()


def test_negative_binomial_rung_is_p_at_least_n():
    import math

    from tennis_wc.props.ace_model import PLAYER_ACE_NB_SIZE as r
    from tennis_wc.props.ace_model import negative_binomial_over_probability as over

    mean = 5.0
    p = r / (r + mean)

    def pmf(k):
        return math.gamma(k + r) / (math.gamma(r) * math.factorial(k)) * p ** r * (1 - p) ** k

    for n in (1, 3, 7):
        at_least_n = 1 - sum(pmf(k) for k in range(n))
        assert over(n - 0.5, mean) == pytest.approx(at_least_n, abs=1e-9)


def test_silent_family_alert(db):
    from tennis_wc.database.db import get_connection
    from tennis_wc.props.family_health import silent_prop_families

    conn = get_connection()

    def row(day, key, i):
        conn.execute(
            """INSERT INTO prop_tracker (prop_key, match_id, match_date, match_label,
                   market_key, line, selection, decimal_odds, stake_units, recorded_at,
                   updated_at)
               VALUES (?, 50, ?, 'x', ?, 1.5, 'Over', 2.0, 0, 'now', 'now')""",
            (f"{day}|{key}|{i}", day, key),
        )

    for d in range(1, 21):
        day = f"2026-09-{d:02d}"
        row(day, "player_win_a_set_1", d)
        if d <= 17:
            row(day, "total_aces_2_5", d)       # aces stop after 09-17
    conn.commit()
    alerts = silent_prop_families(conn, "2026-09-20")
    assert [a["family"] for a in alerts] == ["match_total_aces"]
    assert alerts[0]["last_active_date"] == "2026-09-17"
    # A dead board (nothing at all recently) is a different alarm, not N of these.
    assert silent_prop_families(conn, "2026-10-30") == []
