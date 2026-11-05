"""Grade PENDING props from match results; void retirements, walkovers and
matches with no result 21 days on. A match whose result sources disagree is
held. Scores from several sources are merged only where they agree.
"""
from __future__ import annotations

import json
import re

from tennis_wc.model.features.common import utc_now
from tennis_wc.model.history import active_clause, measurement
from tennis_wc.store.results import conflicting_result_matches


_SCORE_ROWS_SQL = (
    "SELECT score_json FROM match_results WHERE match_id = ? "
    "ORDER BY (json_extract(score_json, '$.incomplete_scoreline') IS 1) ASC, "
    "(COALESCE(json_extract(score_json, '$.player_a_games'), 0) > 0 "
    " OR COALESCE(json_extract(score_json, '$.player_b_games'), 0) > 0 "
    " OR COALESCE(json_extract(score_json, '$.player_a_sets'), 0) > 0 "
    " OR COALESCE(json_extract(score_json, '$.player_b_sets'), 0) > 0 "
    " OR json_array_length(COALESCE(json_extract(score_json, '$.sets'), '[]')) > 0"
    ") DESC, id DESC"
)

_SCORELINE_KEYS = (
    "player_a_games", "player_b_games", "player_a_sets", "player_b_sets",
)


def _scoreline_agrees(base: dict, other: dict) -> bool:
    """Do two result rows describe the same match outcome?

    Filling a gap from a source that disagrees about the scoreline would not be
    completing a record, it would be blending two different claims about what
    happened. Only fields both sources state are compared: a row that is merely
    quieter is still a valid donor.
    """
    for key in _SCORELINE_KEYS:
        a, b = base.get(key), other.get(key)
        if a is None or b is None:
            continue
        try:
            if float(a) != float(b):
                return False
        except (TypeError, ValueError):
            return False
    return True


def _sanitise_score(score: dict) -> dict:
    """Drop figures that cannot describe a match that was played.

    A completed match has games in it. `player_a_games: 0` with
    `player_b_games: 0` is not a 0-0 scoreline, it is a parser that had nothing
    to say, and carrying it forward as a number is how "Under 18.5 total games"
    becomes a winner on no information. Ranking alone does not catch this: a row
    reading sets 1-0 and games 0-0 is not flagged incomplete, does not trip the
    "cannot end level on sets" void, and still outranks a row with only set
    counts.

    Only games are treated this way. Zero aces and zero double faults are
    ordinary things for a real match to contain, and blanking those would lose
    genuine settlements.
    """
    if score.get("player_a_games") == 0 and score.get("player_b_games") == 0:
        score = dict(score)
        score["player_a_games"] = None
        score["player_b_games"] = None
    return score


def _merged_score(conn, match_id: int) -> dict | None:
    """One result view for a match, filled in from every agreeing source.

    The highest-priority row is the base and never gets overwritten; later rows
    only supply keys the base is missing, and only when their scoreline does not
    contradict it. So games and sets still come from the row the old ordering
    chose, and aces stop being lost to whichever source happened to win on id.
    """
    merged: dict | None = None
    for row in conn.execute(_SCORE_ROWS_SQL, (match_id,)).fetchall():
        if not row["score_json"]:
            continue
        try:
            score = json.loads(row["score_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(score, dict):
            continue
        score = _sanitise_score(score)
        if merged is None:
            merged = dict(score)
            continue
        if not _scoreline_agrees(merged, score):
            continue
        for key, value in score.items():
            if value is not None and merged.get(key) is None:
                merged[key] = value
    return merged


def actual_total_aces(conn, match_id: int) -> float | None:
    s = _merged_score(conn, match_id)
    if s:
        try:
            aa, ab = s.get("player_a_aces"), s.get("player_b_aces")
            if aa is not None and ab is not None:
                return float(aa) + float(ab)
        except (TypeError, ValueError):
            pass
    meta = conn.execute(
        "SELECT player_a_id, player_b_id, match_date FROM matches WHERE id = ?", (match_id,)
    ).fetchone()
    if not meta:
        return None
    a = _history_aces(conn, match_id, meta["player_a_id"])
    b = _history_aces(conn, match_id, meta["player_b_id"])
    return (a + b) if (a is not None and b is not None) else None


def actual_player_aces(conn, match_id: int, player_id: int) -> float | None:
    """Actual aces for one player in a match."""
    meta = conn.execute(
        "SELECT player_a_id, player_b_id FROM matches WHERE id = ?", (match_id,)
    ).fetchone()
    if meta:
        s = _merged_score(conn, match_id)
        if s:
            try:
                if player_id == meta["player_a_id"] and s.get("player_a_aces") is not None:
                    return float(s["player_a_aces"])
                if player_id == meta["player_b_id"] and s.get("player_b_aces") is not None:
                    return float(s["player_b_aces"])
            except (TypeError, ValueError):
                pass
    return _history_aces(conn, match_id, player_id)


def actual_player_double_faults(conn, match_id: int, player_id: int) -> float | None:
    value = _actual_player_score_value(conn, match_id, player_id, "double_faults")
    return value if value is not None else _history_count(
        conn, match_id, player_id, "double_fault_count"
    )


def actual_player_games(conn, match_id: int, player_id: int) -> float | None:
    return _actual_player_score_value(conn, match_id, player_id, "games")


def actual_player_sets(conn, match_id: int, player_id: int) -> float | None:
    return _actual_player_score_value(conn, match_id, player_id, "sets")


def actual_player_margin(
    conn, match_id: int, player_id: int, field: str
) -> float | None:
    """Actual named-player margin over the opponent for games or sets."""
    if field not in {"games", "sets"}:
        raise ValueError(f"unsupported margin field: {field}")
    meta = conn.execute(
        "SELECT player_a_id, player_b_id FROM matches WHERE id = ?", (match_id,)
    ).fetchone()
    if not meta or player_id not in {meta["player_a_id"], meta["player_b_id"]}:
        return None
    opponent_id = (
        meta["player_b_id"] if player_id == meta["player_a_id"] else meta["player_a_id"]
    )
    player_value = _actual_player_score_value(conn, match_id, player_id, field)
    opponent_value = _actual_player_score_value(conn, match_id, opponent_id, field)
    if player_value is None or opponent_value is None:
        return None
    return player_value - opponent_value


def actual_player_exact_set_score(
    conn, match_id: int, player_id: int, sets_lost: int
) -> float | None:
    """Binary outcome for a named player winning a completed BO3 match 2-x."""
    if sets_lost not in {0, 1}:
        return None
    meta = conn.execute(
        "SELECT player_a_id, player_b_id FROM matches WHERE id = ?", (match_id,)
    ).fetchone()
    if not meta or player_id not in {meta["player_a_id"], meta["player_b_id"]}:
        return None
    opponent_id = (
        meta["player_b_id"] if player_id == meta["player_a_id"] else meta["player_a_id"]
    )
    won_sets = actual_player_sets(conn, match_id, player_id)
    lost_sets = actual_player_sets(conn, match_id, opponent_id)
    if won_sets is None or lost_sets is None:
        return None
    return 1.0 if int(won_sets) == 2 and int(lost_sets) == sets_lost else 0.0


def actual_player_first_set_win(conn, match_id: int, player_id: int) -> float | None:
    meta = conn.execute(
        "SELECT player_a_id, player_b_id FROM matches WHERE id = ?", (match_id,)
    ).fetchone()
    score = _merged_score(conn, match_id)
    if not meta or not score:
        return None
    try:
        sets = score.get("sets")
        if not isinstance(sets, list) or not sets:
            return None
        a_games = sets[0].get("player_a_games")
        b_games = sets[0].get("player_b_games")
        if a_games is None or b_games is None or int(a_games) == int(b_games):
            return None
        a_won = int(a_games) > int(b_games)
        if player_id == meta["player_a_id"]:
            return 1.0 if a_won else 0.0
        if player_id == meta["player_b_id"]:
            return 0.0 if a_won else 1.0
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return None


def actual_player_first_set_margin(
    conn, match_id: int, player_id: int
) -> float | None:
    """Named player's game margin in the completed first set."""
    meta = conn.execute(
        "SELECT player_a_id, player_b_id FROM matches WHERE id = ?", (match_id,)
    ).fetchone()
    score = _merged_score(conn, match_id)
    if not meta or not score:
        return None
    try:
        sets = score.get("sets")
        if not isinstance(sets, list) or not sets:
            return None
        a_games = sets[0].get("player_a_games")
        b_games = sets[0].get("player_b_games")
        if a_games is None or b_games is None:
            return None
        margin_a = float(a_games) - float(b_games)
        if player_id == meta["player_a_id"]:
            return margin_a
        if player_id == meta["player_b_id"]:
            return -margin_a
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return None


def actual_player_first_set_and_match(
    conn,
    match_id: int,
    player_id: int,
    first_set_won: bool,
) -> float | None:
    """Binary first-set result crossed with the completed match winner."""
    first = actual_player_first_set_win(conn, match_id, player_id)
    meta = conn.execute(
        "SELECT player_a_id, player_b_id FROM matches WHERE id = ?", (match_id,)
    ).fetchone()
    if first is None or not meta or player_id not in {
        meta["player_a_id"], meta["player_b_id"]
    }:
        return None
    opponent_id = (
        meta["player_b_id"] if player_id == meta["player_a_id"]
        else meta["player_a_id"]
    )
    player_sets = actual_player_sets(conn, match_id, player_id)
    opponent_sets = actual_player_sets(conn, match_id, opponent_id)
    if player_sets is None or opponent_sets is None or player_sets == opponent_sets:
        return None
    match_won = player_sets > opponent_sets
    first_matches = bool(first) is bool(first_set_won)
    return 1.0 if match_won and first_matches else 0.0


def _actual_player_score_value(
    conn, match_id: int, player_id: int, field: str
) -> float | None:
    meta = conn.execute(
        "SELECT player_a_id, player_b_id FROM matches WHERE id = ?", (match_id,)
    ).fetchone()
    score = _merged_score(conn, match_id)
    if not meta or not score:
        return None
    try:
        if player_id == meta["player_a_id"]:
            value = score.get(f"player_a_{field}")
        elif player_id == meta["player_b_id"]:
            value = score.get(f"player_b_{field}")
        else:
            return None
        return float(value) if value is not None else None
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def actual_total_games(conn, match_id: int) -> float | None:
    """Actual total match games from match_results.score_json (a+b games)."""
    s = _merged_score(conn, match_id)
    if s:
        try:
            ga, gb = s.get("player_a_games"), s.get("player_b_games")
            if ga is not None and gb is not None:
                return float(ga) + float(gb)
        except (TypeError, ValueError):
            pass
    return None


def _history_aces(conn, match_id: int, player_id: int) -> float | None:
    """Ace count from ingested season files, matched by OPPONENT within the
    event window. History rows carry the tournament START date (Sackmann/TML
    tourney_date convention) while matches.match_date is the actual day, so an
    exact-date join almost never hit (only day-1 matches). Requiring the same
    opponent within [-16d, +2d] pins the row to this specific match; the same
    pairing recurring inside one window is rare enough to accept (closest date
    wins)."""
    return _history_count(conn, match_id, player_id, "ace_count")


def _history_count(conn, match_id: int, player_id: int, column: str) -> float | None:
    if column not in {"ace_count", "double_fault_count"}:
        raise ValueError(f"unsupported history count: {column}")
    meta = conn.execute(
        "SELECT match_date, player_a_id, player_b_id FROM matches WHERE id = ?", (match_id,)
    ).fetchone()
    if not meta:
        return None
    if player_id == meta["player_a_id"]:
        opponent_id = meta["player_b_id"]
    elif player_id == meta["player_b_id"]:
        opponent_id = meta["player_a_id"]
    else:
        return None
    day = (meta["match_date"] or "")[:10]
    if not day:
        return None
    rows = conn.execute(
        """
        SELECT {column} AS value FROM player_match_history
        WHERE player_id = ? AND opponent_id = ? AND {column} IS NOT NULL AND {active}
          AND match_date BETWEEN date(?, '-16 days') AND date(?, '+2 days')
        ORDER BY ABS(julianday(match_date) - julianday(?))
        """.format(column=column,active=active_clause()),
        (player_id, opponent_id, day, day, day),
    ).fetchall()
    values = {measurement(row["value"]) for row in rows}
    return values.pop() if len(values) == 1 else None


def _actual_for(conn, p) -> float | None:
    scope = p["prop_scope"] or "match"
    if scope == "match_games":
        return actual_total_games(conn, p["match_id"])
    if scope == "player_games":
        return actual_player_games(conn, p["match_id"], p["subject_player_id"])
    if scope == "player_win_set":
        return actual_player_sets(conn, p["match_id"], p["subject_player_id"])
    if scope == "player_first_set":
        return actual_player_first_set_win(
            conn, p["match_id"], p["subject_player_id"]
        )
    if scope == "player_first_set_match":
        first_set_won = not str(p["market_key"] or "").endswith("_lose_first")
        return actual_player_first_set_and_match(
            conn, p["match_id"], p["subject_player_id"], first_set_won
        )
    if scope == "player_first_set_game_margin":
        return actual_player_first_set_margin(
            conn, p["match_id"], p["subject_player_id"]
        )
    if scope == "player_double_faults":
        return actual_player_double_faults(
            conn, p["match_id"], p["subject_player_id"]
        )
    if scope == "player_game_margin":
        return actual_player_margin(
            conn, p["match_id"], p["subject_player_id"], "games"
        )
    if scope == "player_set_margin":
        return actual_player_margin(
            conn, p["match_id"], p["subject_player_id"], "sets"
        )
    if scope == "player_exact_set_score":
        parsed = re.search(r"\b2-([01])\s*$", str(p["selection"] or ""))
        if not parsed:
            return None
        return actual_player_exact_set_score(
            conn, p["match_id"], p["subject_player_id"], int(parsed.group(1))
        )
    if scope == "match":
        return actual_total_aces(conn, p["match_id"])
    return actual_player_aces(conn, p["match_id"], p["subject_player_id"])


def _match_void_reason(conn, match_id: int) -> str | None:
    """Return a conservative void reason from any recorded match result."""
    rows = conn.execute(
        "SELECT score_json FROM match_results WHERE match_id = ?",
        (match_id,),
    ).fetchall()
    for row in rows:
        if not row["score_json"]:
            continue
        try:
            score = json.loads(row["score_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if score.get("retired"):
            return "retired"
        if score.get("walkover"):
            return "walkover"
        # A completed match cannot end level on sets. Unparseable score strings
        # became 0-0 and mid-match retirements became 1-1, and both were stored
        # as finished results: 9 existed and 22 props had been graded against
        # them. Checked here rather than in each parser because every provider
        # can produce the shape and settlement is the one place they all meet.
        a_sets, b_sets = score.get("player_a_sets"), score.get("player_b_sets")
        if a_sets is not None and b_sets is not None and int(a_sets) == int(b_sets):
            return "incomplete_scoreline"
    return None


# How long a prop may sit PENDING before its match is treated as never having
# produced a result.
#
# Measured, not chosen. Over the 771 matches since 2026-08-10 -- after the
# TennisExplorer source was wired in, so the daily flow rather than a history
# backfill -- the lag from match_date to the first result row is p50 6 days,
# p99 10 days, longest observed 11. (The same measurement over 2026-06-01
# onwards reads p90 32 days, which is the backfill's `created_at`, not how long
# a result actually takes. Do not re-derive this threshold from that window.)
#
# 21 days is roughly twice the longest real arrival. It is deliberately loose:
# the cost of waiting an extra week is a number on a health line, and the cost
# of voiding a prop whose result was merely slow is a fabricated void in the
# evidence base the family gate reads.
#
# This exists because there was no such rule. 28 value props from 2026-05-11,
# 06-16, 06-23, 06-24 and 07-14 -- including ATP Halle and WTA Nottingham main
# draw -- sat PENDING for up to 106 days against matches with no result row of
# any kind, quietly inflating the daily "未結算" counter until it meant nothing
# and could no longer show a real settlement backlog.
ABANDONED_AFTER_DAYS = 21


def _days_since_match(conn, match_id: int, today: str | None) -> int:
    import datetime

    row = conn.execute("SELECT match_date FROM matches WHERE id = ?", (match_id,)).fetchone()
    try:
        played = datetime.date.fromisoformat(str(row["match_date"])[:10])
        reference = datetime.date.fromisoformat(str(today)[:10]) if today else datetime.date.today()
    except (TypeError, ValueError):
        return 0
    return (reference - played).days


def _abandoned_reason(conn, match_id: int, today: str | None = None) -> str | None:
    """A match old enough that no result is coming, and none ever arrived.

    Deliberately narrow: it fires only when there is NO result row at all. A
    match with a partial result is a settlement problem to be fixed, not an
    abandonment -- that distinction is what separated these 28 props from the
    30 that turned out to be readable all along.
    """
    import datetime

    row = conn.execute(
        "SELECT match_date FROM matches WHERE id = ?", (match_id,)
    ).fetchone()
    if not row or not row["match_date"]:
        return None
    try:
        played = datetime.date.fromisoformat(str(row["match_date"])[:10])
        reference = (
            datetime.date.fromisoformat(str(today)[:10]) if today
            else datetime.date.today()
        )
    except (TypeError, ValueError):
        return None
    age = (reference - played).days
    if age < ABANDONED_AFTER_DAYS:
        return None
    if conn.execute(
        "SELECT 1 FROM match_results WHERE match_id = ? LIMIT 1", (match_id,)
    ).fetchone():
        return None
    return f"no result {age} days after the match"


def settle_props(conn, today: str | None = None) -> dict:
    conflicts = conflicting_result_matches(conn)
    # Legacy label migration: prop_tracker used WIN/LOSS while every other
    # tracker uses WON/LOST. Converge idempotently so cross-table stats need
    # only one vocabulary (also fixes rows written by machines on old code).
    conn.execute("UPDATE prop_tracker SET result_status='WON' WHERE result_status='WIN'")
    conn.execute("UPDATE prop_tracker SET result_status='LOST' WHERE result_status='LOSS'")
    pending = conn.execute("SELECT * FROM prop_tracker WHERE result_status = 'PENDING'").fetchall()
    graded = 0
    voided = 0
    held_out = 0
    # Self-heal rows graded before a void reason was recognised. 22 props had
    # been settled against a scoreline that cannot have happened; leaving them
    # WON/LOST keeps fiction in the evidence base that the gate then reads.
    regraded = 0
    for row in conn.execute(
        "SELECT id, match_id FROM prop_tracker WHERE result_status IN ('WON', 'LOST')"
    ).fetchall():
        if int(row["match_id"]) in conflicts:
            continue
        if _match_void_reason(conn, int(row["match_id"])):
            conn.execute(
                "UPDATE prop_tracker SET result_status='VOID', actual_value=NULL, "
                "profit_loss_units=0, settled_at=?, updated_at=? WHERE id=?",
                (utc_now(), utc_now(), row["id"]),
            )
            regraded += 1
    # And the reverse, so an abandonment void is a judgement that can be taken
    # back rather than a one-way door. A result arriving on day 25 for a prop
    # voided on day 21 puts it back in the queue to be graded properly. Checked
    # against the tracker before shipping: of 417 existing VOID props, zero have
    # a result and no recognised void reason, so this resurrects nothing that
    # was voided for a real reason.
    revived = 0
    for row in conn.execute(
        "SELECT id, match_id FROM prop_tracker WHERE result_status = 'VOID'"
    ).fetchall():
        match_id = int(row["match_id"])
        if match_id in conflicts:
            continue
        if _match_void_reason(conn, match_id):
            continue
        if not conn.execute(
            "SELECT 1 FROM match_results WHERE match_id = ? LIMIT 1", (match_id,)
        ).fetchone():
            continue
        conn.execute(
            "UPDATE prop_tracker SET result_status='PENDING', settled_at=NULL, "
            "updated_at=? WHERE id=?", (utc_now(), row["id"]),
        )
        revived += 1
    if revived:
        pending = conn.execute(
            "SELECT * FROM prop_tracker WHERE result_status = 'PENDING'"
        ).fetchall()
    abandoned = 0
    for p in pending:
        if int(p["match_id"]) in conflicts:
            # Sources still disagree 21 days on: no consensus is coming, so the
            # prop is excluded explicitly (VOID) instead of pending forever
            # (plan 2026-11-05 stage 5; 115 such rows on 2026-11-06).
            if _days_since_match(conn, int(p["match_id"]), today) >= ABANDONED_AFTER_DAYS:
                conn.execute("UPDATE prop_tracker SET result_status='VOID', actual_value=NULL, "
                             "profit_loss_units=0, settled_at=?, updated_at=? WHERE id=?",
                             (utc_now(), utc_now(), p["id"]))
                voided += 1
                held_out += 1
            continue
        void_reason = _match_void_reason(conn, int(p["match_id"]))
        if not void_reason:
            void_reason = _abandoned_reason(conn, int(p["match_id"]), today)
            if void_reason:
                abandoned += 1
        if void_reason:
            conn.execute(
                "UPDATE prop_tracker SET result_status='VOID', actual_value=NULL, "
                "profit_loss_units=0, settled_at=?, updated_at=? WHERE id=?",
                (utc_now(), utc_now(), p["id"]),
            )
            voided += 1
            continue
        actual = _actual_for(conn, p)
        if actual is None:
            continue
        won = actual >= p["line"] if (p["side"] or "over") == "over" else actual < p["line"]
        stake = p["stake_units"] or 0.0
        pl = stake * (p["decimal_odds"] - 1.0) if won else -stake
        conn.execute(
            "UPDATE prop_tracker SET result_status=?, actual_value=?, profit_loss_units=?, "
            "settled_at=?, updated_at=? WHERE id=?",
            ("WON" if won else "LOST", actual, round(pl, 4), utc_now(), utc_now(), p["id"]),
        )
        graded += 1
    conn.commit()
    return {
        "graded": graded,
        "voided": voided,
        # Broken out rather than folded into `voided`: a retirement void and a
        # "no result ever arrived" void say different things about the pipeline,
        # and only the second one is a number that should stay near zero.
        "voided_abandoned": abandoned,
        "regraded_to_void": regraded,
        "revived_from_void": revived,
        "still_pending": len(pending) - graded - voided,
        "voided_disputed": held_out,
        "held_conflicting_results": sum(int(p["match_id"]) in conflicts for p in pending) - held_out,
        "conflicting_result_match_ids": sorted(conflicts),
    }


# --------------------------------------------------------------------------- #
# Review 1: segmented ROI
# --------------------------------------------------------------------------- #
