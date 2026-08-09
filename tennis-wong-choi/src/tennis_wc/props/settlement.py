"""Prop settlement + results review.

Load-bearing half of the "ship it, validate live" plan: log every surfaced prop,
grade vs actual outcomes, and REVIEW performance two ways:

  1. Segmented ROI (by market / side / value-flag) -- needs bets to settle.
  2. Model-vs-market SCORECARD (Brier + log-loss + calibration table) -- needs
     only outcomes, so it tells us WHO is right (our model or the book) far
     sooner than ROI can, directly resolving the "book too tight vs model too
     low" question the ace over-pricing raised.

Outcomes:
  * match total aces  -> match_results.score_json (a+b), else paired history.
  * single-player aces -> that player's ace_count (score_json side, else history).
Win rule (works for both integer 'N+' and '.5' O/U lines):
  side 'over'  wins if actual >= line ;  side 'under' wins if actual < line.
"""
from __future__ import annotations

import json
import math
import re

from tennis_wc.features.common import utc_now


def actual_total_aces(conn, match_id: int) -> float | None:
    row = conn.execute(
        "SELECT score_json FROM match_results WHERE match_id = ? ORDER BY id DESC LIMIT 1",
        (match_id,),
    ).fetchone()
    if row and row["score_json"]:
        try:
            s = json.loads(row["score_json"])
            aa, ab = s.get("player_a_aces"), s.get("player_b_aces")
            if aa is not None and ab is not None:
                return float(aa) + float(ab)
        except (TypeError, ValueError, json.JSONDecodeError):
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
        row = conn.execute(
            "SELECT score_json FROM match_results WHERE match_id = ? ORDER BY id DESC LIMIT 1",
            (match_id,),
        ).fetchone()
        if row and row["score_json"]:
            try:
                s = json.loads(row["score_json"])
                if player_id == meta["player_a_id"] and s.get("player_a_aces") is not None:
                    return float(s["player_a_aces"])
                if player_id == meta["player_b_id"] and s.get("player_b_aces") is not None:
                    return float(s["player_b_aces"])
            except (TypeError, ValueError, json.JSONDecodeError):
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
    row = conn.execute(
        "SELECT score_json FROM match_results WHERE match_id = ? ORDER BY id DESC LIMIT 1",
        (match_id,),
    ).fetchone()
    if not meta or not row or not row["score_json"]:
        return None
    try:
        score = json.loads(row["score_json"])
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


def _actual_player_score_value(
    conn, match_id: int, player_id: int, field: str
) -> float | None:
    meta = conn.execute(
        "SELECT player_a_id, player_b_id FROM matches WHERE id = ?", (match_id,)
    ).fetchone()
    row = conn.execute(
        "SELECT score_json FROM match_results WHERE match_id = ? ORDER BY id DESC LIMIT 1",
        (match_id,),
    ).fetchone()
    if not meta or not row or not row["score_json"]:
        return None
    try:
        score = json.loads(row["score_json"])
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
    row = conn.execute(
        "SELECT score_json FROM match_results WHERE match_id = ? ORDER BY id DESC LIMIT 1",
        (match_id,),
    ).fetchone()
    if row and row["score_json"]:
        try:
            s = json.loads(row["score_json"])
            ga, gb = s.get("player_a_games"), s.get("player_b_games")
            if ga is not None and gb is not None:
                return float(ga) + float(gb)
        except (TypeError, ValueError, json.JSONDecodeError):
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
    row = conn.execute(
        """
        SELECT {column} AS value FROM player_match_history
        WHERE player_id = ? AND opponent_id = ? AND {column} IS NOT NULL
          AND match_date BETWEEN date(?, '-16 days') AND date(?, '+2 days')
        ORDER BY ABS(julianday(match_date) - julianday(?))
        LIMIT 1
        """.format(column=column),
        (player_id, opponent_id, day, day, day),
    ).fetchone()
    return float(row["value"]) if row else None


def record_prop(conn, *, match_id: int, match_date: str, match_label: str,
                market_key: str, line: float, selection: str, side: str,
                prop_scope: str, subject_player_id: int | None, decimal_odds: float,
                model_prob: float, market_prob_fair: float, blended_prob: float,
                edge: float, ev: float, predicted_mean: float,
                stake_units: float, is_value: bool,
                model_prob_raw: float | None = None,
                temper_strength: float | None = None) -> None:
    """Upsert a surfaced prop as PENDING (idempotent per match+market+selection).
    All probabilities are OF THIS SIDE.

    model_prob      -- staking-side probability (tempered). Historical meaning.
    model_prob_raw  -- RAW odds-blind model probability. This is what the
                       model-vs-market scorecard grades; without it the scorecard
                       measures a risk-adjusted number and cannot tell us whether
                       the model itself has any skill.
    temper_strength -- haircut applied to get from raw to model_prob, recorded so
                       any row can be audited after the fact.
    """
    prop_key = f"{match_id}|{market_key}|{selection}"
    now = utc_now()
    conn.execute(
        """
        INSERT INTO prop_tracker (
            prop_key, match_id, match_date, match_label, market_key, line, selection,
            side, prop_scope, subject_player_id, decimal_odds, model_prob,
            model_prob_raw, temper_strength,
            market_prob_fair, blended_prob, edge, ev, predicted_mean, stake_units,
            is_value, result_status, profit_loss_units, actual_value,
            recorded_at, updated_at, settled_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'PENDING', NULL, NULL, ?, ?, NULL)
        ON CONFLICT(prop_key) DO UPDATE SET
            decimal_odds=excluded.decimal_odds, model_prob=excluded.model_prob,
            model_prob_raw=excluded.model_prob_raw,
            temper_strength=excluded.temper_strength,
            market_prob_fair=excluded.market_prob_fair, blended_prob=excluded.blended_prob,
            edge=excluded.edge, ev=excluded.ev, predicted_mean=excluded.predicted_mean,
            stake_units=excluded.stake_units, is_value=excluded.is_value,
            updated_at=excluded.updated_at
        WHERE prop_tracker.result_status = 'PENDING'
        """,
        (prop_key, match_id, match_date, match_label, market_key, line, selection,
         side, prop_scope, subject_player_id, decimal_odds, model_prob,
         model_prob_raw, temper_strength,
         market_prob_fair, blended_prob, edge, ev, predicted_mean, stake_units,
         1 if is_value else 0, now, now),
    )


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
    return None


def settle_props(conn) -> dict:
    # Legacy label migration: prop_tracker used WIN/LOSS while every other
    # tracker uses WON/LOST. Converge idempotently so cross-table stats need
    # only one vocabulary (also fixes rows written by machines on old code).
    conn.execute("UPDATE prop_tracker SET result_status='WON' WHERE result_status='WIN'")
    conn.execute("UPDATE prop_tracker SET result_status='LOST' WHERE result_status='LOSS'")
    pending = conn.execute("SELECT * FROM prop_tracker WHERE result_status = 'PENDING'").fetchall()
    graded = 0
    voided = 0
    for p in pending:
        void_reason = _match_void_reason(conn, int(p["match_id"]))
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
        "still_pending": len(pending) - graded - voided,
    }


# --------------------------------------------------------------------------- #
# Review 1: segmented ROI
# --------------------------------------------------------------------------- #
def prop_roi_report(conn, value_only: bool = True,
                    as_of_date: str | None = None) -> dict:
    """Realised ROI over settled BET props, split into decision-useful segments.

    Besides market family and side, report odds, confidence, tour, surface and
    source-quality bands.  The fixed bands make it harder to cherry-pick a
    profitable-looking slice after seeing the results.
    """
    where = "result_status IN ('WON','LOST') AND stake_units > 0"
    if value_only:
        where += " AND is_value = 1"
    params: list = []
    if as_of_date:
        where += " AND p.match_date < ?"
        params.append(as_of_date)
    rows = conn.execute(
        f"""
        WITH quality AS (
            SELECT match_id, MIN(data_quality_score) AS data_quality_score
            FROM feature_snapshots
            GROUP BY match_id
        )
        SELECT p.*,
               m.tour,
               COALESCE(
                   (SELECT tl.surface FROM tournament_levels tl
                    WHERE tl.tournament_id = m.tournament_id
                    ORDER BY tl.id DESC LIMIT 1),
                   'UNKNOWN'
               ) AS surface,
               quality.data_quality_score
        FROM prop_tracker p
        LEFT JOIN matches m ON m.id = p.match_id
        LEFT JOIN quality ON quality.match_id = p.match_id
        WHERE p.{where}
        ORDER BY p.match_date, p.id
        """
        , tuple(params)
    ).fetchall()

    def agg(rs):
        n = len(rs)
        if not n:
            return {"settled": 0, "wins": 0, "hit_rate": None, "staked": 0.0, "pnl": 0.0, "roi": None}
        wins = sum(1 for r in rs if r["result_status"] == "WON")
        staked = sum((r["stake_units"] or 0.0) for r in rs)
        pnl = sum((r["profit_loss_units"] or 0.0) for r in rs)
        return {"settled": n, "wins": wins, "hit_rate": round(wins / n, 4),
                "staked": round(staked, 2), "pnl": round(pnl, 3),
                "roi": round(pnl / staked, 4) if staked else None}

    def family(mk: str) -> str:
        from tennis_wc.props.registry import family_for_market
        return family_for_market(mk)

    def odds_band(value) -> str:
        odds = float(value or 0)
        if odds < 1.60:
            return "<1.60"
        if odds < 1.90:
            return "1.60-1.89"
        if odds < 2.20:
            return "1.90-2.19"
        return "2.20+"

    def probability_band(value) -> str:
        probability = float(value or 0)
        if probability < 0.55:
            return "<55%"
        if probability < 0.65:
            return "55-64%"
        if probability < 0.75:
            return "65-74%"
        return "75%+"

    def quality_band(value) -> str:
        if value is None:
            return "UNKNOWN"
        from tennis_wc.props.strategy import normalise_data_quality
        quality = normalise_data_quality(value)
        if quality < 0.60:
            return "<60%"
        if quality < 0.65:
            return "60-64%"
        return "65%+"

    by_side, by_family, by_odds, by_probability = {}, {}, {}, {}
    by_tour, by_surface, by_quality = {}, {}, {}
    for r in rows:
        by_side.setdefault(r["side"] or "over", []).append(r)
        by_family.setdefault(family(r["market_key"]), []).append(r)
        by_odds.setdefault(odds_band(r["decimal_odds"]), []).append(r)
        by_probability.setdefault(probability_band(r["blended_prob"]), []).append(r)
        by_tour.setdefault(str(r["tour"] or "UNKNOWN").upper(), []).append(r)
        by_surface.setdefault(str(r["surface"] or "UNKNOWN").upper(), []).append(r)

    # Gate evidence must match the bets the live strategy is actually allowed
    # to place.  In particular, research longshots above 2.25 cannot make a
    # family look profitable and thereby graduate lower-odds recommendations.
    from tennis_wc.props import strategy

    def live_quality(row) -> float:
        market_family = family(row["market_key"])
        if market_family not in {
            "player_aces", "match_total_aces", "player_double_faults"
        }:
            return strategy.normalise_data_quality(row["data_quality_score"])
        match = conn.execute(
            "SELECT player_a_id,player_b_id FROM matches WHERE id=?",
            (row["match_id"],),
        ).fetchone()
        if not match:
            return 0.0
        if market_family == "match_total_aces":
            player_ids = (match["player_a_id"], match["player_b_id"])
            column = "ace_count"
        elif market_family == "player_aces":
            subject = row["subject_player_id"]
            opponent = (
                match["player_b_id"]
                if subject == match["player_a_id"] else match["player_a_id"]
            )
            player_ids = (subject, opponent)
            column = "ace_count"
        else:
            player_ids = (row["subject_player_id"],)
            column = "double_fault_count"
        counts = [
            conn.execute(
                f"SELECT COUNT(*) FROM (SELECT 1 FROM player_match_history "
                f"WHERE player_id=? AND match_date<? AND {column} IS NOT NULL "
                "ORDER BY match_date DESC LIMIT 15)",
                (player_id, row["match_date"]),
            ).fetchone()[0]
            for player_id in player_ids if player_id is not None
        ]
        return min(counts, default=0) / 15.0

    for row in rows:
        by_quality.setdefault(quality_band(live_quality(row)), []).append(row)

    formal_profile_rows = [
        row for row in rows
        if strategy.MIN_LEG_PROBABILITY <= float(row["blended_prob"] or 0) <= 1.0
        and strategy.MIN_LEG_ODDS <= float(row["decimal_odds"] or 0) <= strategy.MAX_LEG_ODDS
        and live_quality(row) >= strategy.MIN_DATA_QUALITY
        and float(row["edge"] or 0) > 0
        and float(row["ev"] or 0) > 0
    ]
    formal_by_family: dict[str, list] = {}
    for row in formal_profile_rows:
        formal_by_family.setdefault(family(row["market_key"]), []).append(row)
    player_prop_rows = [
        row for row in rows
        if family(row["market_key"]) in strategy.RECOMMENDABLE_PLAYER_FAMILIES
    ]
    formal_player_prop_rows = [
        row for row in formal_profile_rows
        if family(row["market_key"]) in strategy.RECOMMENDABLE_PLAYER_FAMILIES
    ]

    running = peak = max_drawdown = 0.0
    for row in rows:
        running += float(row["profit_loss_units"] or 0)
        peak = max(peak, running)
        max_drawdown = min(max_drawdown, running - peak)
    return {
        "overall": agg(rows),
        "by_side": {k: agg(v) for k, v in by_side.items()},
        "by_family": {k: agg(v) for k, v in by_family.items()},
        "by_family_formal_profile": {
            k: agg(v) for k, v in formal_by_family.items()
        },
        "formal_profile": agg(formal_profile_rows),
        "player_prop_overall": agg(player_prop_rows),
        "formal_player_prop_profile": agg(formal_player_prop_rows),
        "by_odds_band": {k: agg(v) for k, v in by_odds.items()},
        "by_probability_band": {k: agg(v) for k, v in by_probability.items()},
        "by_tour": {k: agg(v) for k, v in by_tour.items()},
        "by_surface": {k: agg(v) for k, v in by_surface.items()},
        "by_data_quality": {k: agg(v) for k, v in by_quality.items()},
        "max_drawdown_units": round(max_drawdown, 3),
    }


# --------------------------------------------------------------------------- #
# Review 2: model-vs-market scorecard (needs only outcomes, not bets)
# --------------------------------------------------------------------------- #
def model_vs_market_scorecard(conn, use_raw: bool = True,
                              as_of_date: str | None = None) -> dict:
    """On every settled prop, compare the MODEL's probability of the recorded
    side vs the MARKET's de-vigged probability, via Brier + log-loss. Lower is
    better. If the model beats the market, our edge is real; if the market wins,
    the model is the weak link (as with match-winner). Also a calibration table:
    predicted-prob bucket vs realised hit.

    Grades `model_prob_raw` -- the odds-blind model output -- because that is the
    only column that answers "does the model have skill". `model_prob` is the
    tempered/staking number: grading it flattered the model (pulling a probability
    toward 0.5 lowers Brier whenever the model is overconfident) AND fed a loop,
    since the temper strength is itself picked from this scorecard. Rows written
    before 2026-07-25 have no raw column and are reported separately rather than
    silently mixed in. Pass use_raw=False for the legacy tempered view.
    """
    column = "model_prob_raw" if use_raw else "model_prob"
    date_clause = " AND p.match_date < ?" if as_of_date else ""
    params = (as_of_date,) if as_of_date else ()
    rows = conn.execute(
        f"SELECT p.match_id, p.{column} AS prob, p.market_prob_fair, p.result_status, "
        "p.market_key FROM prop_tracker p JOIN matches m ON m.id=p.match_id "
        f"WHERE p.result_status IN ('WON','LOST') AND p.{column} IS NOT NULL "
        "AND p.market_prob_fair IS NOT NULL AND p.side='over' "
        "AND (p.prop_scope!='player_first_set' "
        "OR p.subject_player_id=m.player_a_id)" + date_clause,
        params,
    ).fetchall()
    legacy_only = conn.execute(
        "SELECT COUNT(*) FROM prop_tracker p JOIN matches m ON m.id=p.match_id "
        "WHERE p.result_status IN ('WON','LOST') "
        "AND p.model_prob_raw IS NULL AND p.model_prob IS NOT NULL "
        "AND p.side='over' AND (p.prop_scope!='player_first_set' "
        "OR p.subject_player_id=m.player_a_id)" + date_clause,
        params,
    ).fetchone()[0]
    n = len(rows)
    if not n:
        return {"settled": 0, "model": None, "market": None,
                "verdict": ("no settled props with a raw model probability yet — "
                            f"{legacy_only} older rows only stored the tempered value"),
                "calibration": [], "graded_on": column, "legacy_rows_excluded": legacy_only}

    def clamp(p):
        return min(1 - 1e-9, max(1e-9, p))

    def metrics(sample):
        m_brier = mk_brier = m_ll = mk_ll = 0.0
        cal = {}
        for r in sample:
            y = 1.0 if r["result_status"] == "WON" else 0.0
            mp, kp = clamp(r["prob"]), clamp(r["market_prob_fair"])
            m_brier += (mp - y) ** 2
            mk_brier += (kp - y) ** 2
            m_ll += -(y * math.log(mp) + (1 - y) * math.log(1 - mp))
            mk_ll += -(y * math.log(kp) + (1 - y) * math.log(1 - kp))
            b = round(mp * 10) / 10
            cal.setdefault(b, [0.0, 0, 0])
            cal[b][0] += mp; cal[b][1] += int(y); cal[b][2] += 1
        size = len(sample)
        model_stats = {
            "brier": round(m_brier / size, 4),
            "log_loss": round(m_ll / size, 4),
        }
        market_stats = {
            "brier": round(mk_brier / size, 4),
            "log_loss": round(mk_ll / size, 4),
        }
        calibration = [
            {"pred": round(s / c, 3), "realised": round(w / c, 3), "n": c}
            for _b, (s, w, c) in sorted(cal.items()) if c >= 5
        ]
        return model_stats, market_stats, calibration

    model, market, calibration = metrics(rows)
    if model["brier"] < market["brier"] - 0.005:
        verdict = "MODEL beats market (edge plausibly real) — keep validating"
    elif market["brier"] < model["brier"] - 0.005:
        verdict = "MARKET beats model (model is the weak link, like match-winner)"
    else:
        verdict = "model ≈ market (no clear edge either way)"
    from tennis_wc.props.registry import family_for_market
    grouped = {}
    for row in rows:
        grouped.setdefault(family_for_market(row["market_key"]), []).append(row)
    by_family = {}
    for family, sample in grouped.items():
        family_model, family_market, _ = metrics(sample)
        settled = (
            len({int(row["match_id"]) for row in sample})
            if family == "player_exact_set_score"
            else len(sample)
        )
        by_family[family] = {
            "settled": settled,
            "model": family_model,
            "market": family_market,
        }
    return {"settled": n, "model": model, "market": market, "verdict": verdict,
            "calibration": calibration, "graded_on": column,
            "legacy_rows_excluded": legacy_only if use_raw else 0,
            "by_family": by_family}
