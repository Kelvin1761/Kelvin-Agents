"""Read a date's prop quotes and pair them into priceable markets.

Every reader matches a selection to player A or B by normalised name; a name
that matches neither (or both) is dropped rather than guessed, because a guess
mirror-flips the price.
"""
from __future__ import annotations

import logging
import re
from collections import Counter

from tennis_wc.pricing.families import family_for_market
from tennis_wc.store.markets import current_market_clause

_LOGGER = logging.getLogger(__name__)

_BRACKETED_HANDICAP = re.compile(r"\s*\([+-]?\d+(?:\.\d+)?\)\s*$")
_TRAILING_HANDICAP = re.compile(r"\s+[+-]\d+(?:\.\d+)?\s*$")
FIRST_SET_MATCH_KEYS = ("to_win_1st_set_and_win_match", "to_lose_1st_set_and_win_match")


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def rows_for_date(conn, match_date: str) -> list:
    """Current quotes for the priced families, minus any whose event page failed
    its source check (wrong event id, unreadable body)."""
    from tennis_wc.store.odds_source_reads import OddsSourceReader

    selected = conn.execute(f"""
        SELECT mo.match_id, mo.market_key, mo.market_name, mo.selection_name,
               mo.line, mo.odds, mo.id, mo.bookmaker, mo.source_provider,
               mo.raw_response_id, mo.fetched_at
        FROM market_odds_snapshots mo JOIN matches m ON m.id = mo.match_id
        WHERE m.match_date = ? AND {current_market_clause()} AND m.fixture_status='ACTIVE' AND (
            lower(mo.market_name) LIKE '%total games%'
            OR lower(mo.market_name) LIKE '%win at least %set%'
            OR lower(mo.market_name) IN ('set 1 winner', 'first set winner', '1st set winner')
            OR mo.market_key IN ('game_handicap', 'set_handicap')
            OR mo.market_key IN ('to_win_1st_set_and_win_match', 'to_lose_1st_set_and_win_match')
        )
        ORDER BY mo.id ASC""", (match_date,)).fetchall()
    reader = OddsSourceReader(conn)
    counts: Counter = Counter()
    kept = []
    for row in selected:
        status, blocked = reader.assess(row["raw_response_id"])
        counts[status] += 1
        if not blocked:
            kept.append(row)
    warnings = {k: v for k, v in counts.items()
                if k not in {"matched_event_id", "outside_direct_event_scope"}}
    if warnings:
        _LOGGER.warning("market source identity %s: %s", match_date, warnings)
    return kept


def two_way(rows) -> dict:
    """(market_key, market_name, line) -> {over, under, over_name, under_name, market_name}."""
    out: dict = {}
    for r in rows:
        name = str(r["selection_name"] or "")
        low = name.lower()
        if r["line"] is None:
            continue
        side = "over" if low.startswith("over") else "under" if low.startswith("under") else None
        if side is None:
            continue
        bucket = out.setdefault((r["market_key"], r["market_name"], float(r["line"])),
                                {"market_name": r["market_name"]})
        bucket[side] = float(r["odds"])
        bucket[f"{side}_name"] = name
    return out


def yes_no(rows) -> dict:
    """(market_key, market_name) -> {yes, no, yes_name, no_name, market_name}."""
    out: dict = {}
    for r in rows:
        tokens = str(r["selection_name"] or "").lower().split()
        if not tokens or tokens[-1] not in {"yes", "no"}:
            continue
        bucket = out.setdefault((r["market_key"], r["market_name"]), {"market_name": r["market_name"]})
        bucket[tokens[-1]] = float(r["odds"])
        bucket[f"{tokens[-1]}_name"] = str(r["selection_name"] or "")
    return out


def _side(selection: str, meta) -> str | None:
    a, b = norm(meta["a_name"]), norm(meta["b_name"])
    s = norm(selection)
    return "a" if s == a else "b" if s == b else None


def first_set_winner(rows, meta) -> dict:
    """(market_key, market_name) -> {a, b, a_name, b_name, market_name}."""
    out: dict = {}
    for row in rows:
        if family_for_market(row["market_key"], row["market_name"]) != "first_set_winner":
            continue
        side = _side(row["selection_name"], meta)
        if side is None:
            continue
        bucket = out.setdefault((row["market_key"], row["market_name"]), {"market_name": row["market_name"]})
        bucket[side] = float(row["odds"])
        bucket[f"{side}_name"] = str(row["selection_name"] or "")
    return out


def first_set_match(rows, meta) -> dict | None:
    """{a_win, a_lose, b_win, b_lose} -> quote, only when all four are listed."""
    out: dict = {}
    for row in rows:
        market_key = str(row["market_key"] or "")
        if market_key not in FIRST_SET_MATCH_KEYS:
            continue
        raw_name = str(row["selection_name"] or "")
        side = _side(re.sub(r"\s+yes\s*$", "", raw_name, flags=re.I), meta)
        if side is None:
            continue
        result = "win" if market_key.startswith("to_win_") else "lose"
        out[f"{side}_{result}"] = {"odds": float(row["odds"]), "selection_name": raw_name,
                                   "market_key": market_key, "market_name": str(row["market_name"] or "")}
    return out if set(out) == {"a_win", "a_lose", "b_win", "b_lose"} else None


def spreads(rows, meta, family: str) -> dict:
    """abs(line) -> {a: {odds, handicap}, b: {...}, a_name, b_name, market_key, market_name}.

    Half-point lines only (no pushes). Bracketed selections ("Name (+2.5)") win;
    otherwise the main market's trailing-handicap pair closest to even money.
    """
    out: dict = {}
    unbracketed: dict = {}
    for row in rows:
        if family_for_market(row["market_key"], row["market_name"]) != family or row["line"] is None:
            continue
        handicap = float(row["line"])
        if abs(abs(handicap) % 1.0 - 0.5) > 1e-9:
            continue
        raw_selection = str(row["selection_name"] or "")
        if not _BRACKETED_HANDICAP.search(raw_selection):
            player_text = _TRAILING_HANDICAP.sub("", raw_selection)
            if player_text == raw_selection:
                continue
            side = _side(player_text, meta)
            if side is None:
                continue
            a_handicap = handicap if side == "a" else -handicap
            pair = unbracketed.setdefault(abs(handicap), {}).setdefault(
                (str(row["market_name"] or ""), a_handicap),
                {"market_name": row["market_name"], "market_key": row["market_key"]})
            pair[f"{side}_name"] = raw_selection
            pair[side] = {"odds": float(row["odds"]), "handicap": handicap}
            continue
        side = _side(_BRACKETED_HANDICAP.sub("", raw_selection), meta)
        if side is None:
            continue
        bucket = out.setdefault(abs(handicap), {"market_name": row["market_name"]})
        bucket["market_name"] = row["market_name"]
        bucket["market_key"] = row["market_key"]
        bucket[f"{side}_name"] = raw_selection
        bucket[side] = {"odds": float(row["odds"]), "handicap": handicap}

    def paired(value):
        return "a" in value and "b" in value and abs(value["a"]["handicap"] + value["b"]["handicap"]) < 1e-9

    result = {line: value for line, value in out.items() if paired(value)}
    for line, pairs in unbracketed.items():
        if line in result:
            continue
        complete = [pair for pair in pairs.values() if paired(pair)]
        if not complete:
            continue
        complete.sort(key=lambda pair: ("alternative" in str(pair["market_name"] or "").lower(),
                                        abs(1.0 / pair["a"]["odds"] - 1.0 / pair["b"]["odds"]),
                                        pair["a"]["handicap"]))
        result[line] = complete[0]
    return result
