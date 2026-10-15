"""Ingest WTA per-match serve statistics into `wta_match_stats`.

Deliberately a table of its own, NOT rows in player_match_history:

  * About a dozen feature readers (head_to_head, pressure, big_match,
    round_performance, bo_format, tournament_level, ...) count every
    player_match_history row with no provider filter. composite and
    TennisExplorer already hold these WTA results, so a third copy would
    silently re-weight WTA match-winner features.
  * Feeding the serve readers (ace_model, serve_return / hold_model) is a
    model change: it re-prices every WTA set/games prop that today runs on
    serve rows last dated 2026-05-18. That needs the regression gate on a
    backfilled corpus first (docs/model-evaluation-contract.md), not a
    side effect of an ingestion commit.

So this lands the data with full provenance and health visibility; wiring it
into the serve readers is a separate, evaluated change.

Column meanings match player_match_history (derived by the same `_metrics`
used for the Sackmann files) so the later wiring is a join, not a re-derive.
"""
from __future__ import annotations

import time
from datetime import date

from tennis_wc.database.db import get_connection
from tennis_wc.ingestion.ingest_sackmann import _metrics
from tennis_wc.ingestion.raw_response_store import store_raw_response, utc_now
from tennis_wc.providers.wta_stats_provider import WtaStatsProvider

PROVIDER_NAME = WtaStatsProvider.provider_name
# ITF events are listed but their match feed is empty (measured 2026-10-14);
# skipping them saves ~85 pointless requests per 4.5 months.
SKIP_LEVELS = {"ITF"}


def ensure_wta_stats_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wta_match_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id TEXT NOT NULL,
            year INTEGER NOT NULL,
            wta_match_id TEXT NOT NULL,
            side TEXT NOT NULL,
            wta_player_id TEXT,
            player_name TEXT NOT NULL,
            opponent_wta_id TEXT,
            opponent_name TEXT NOT NULL,
            player_id INTEGER,
            opponent_id INTEGER,
            match_date TEXT NOT NULL,
            tournament_name TEXT,
            tournament_level TEXT,
            surface TEXT,
            draw_level TEXT,
            round_id TEXT,
            won INTEGER,
            score TEXT,
            stats_status TEXT NOT NULL,
            ace_count REAL,
            double_fault_count REAL,
            serve_points REAL,
            first_serves_in REAL,
            first_serve_points_won REAL,
            second_serve_points_won REAL,
            service_games_played REAL,
            break_points_saved REAL,
            break_points_faced REAL,
            break_points_converted REAL,
            break_points_chances REAL,
            hold_rate REAL,
            break_rate REAL,
            first_serve_points_won_pct REAL,
            second_serve_points_won_pct REAL,
            return_points_won_pct REAL,
            source_provider TEXT NOT NULL,
            raw_response_id INTEGER NOT NULL,
            fetched_at TEXT NOT NULL,
            UNIQUE(tournament_id, year, wta_match_id, side)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_wta_match_stats_player "
        "ON wta_match_stats(player_id, match_date)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_wta_match_stats_date "
        "ON wta_match_stats(match_date, stats_status)"
    )


def _num(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _side_columns(total: dict, own: str, opp: str) -> dict:
    """Sackmann-shaped columns for one side from the API's match-total row.

    Break points: `breakptsplayed{x}` are the chances x had on RETURN and
    `breakptsconv{x}` the ones x converted -- checked on a 6-4 6-3 match where
    the totals only reconcile that way (games won = holds + breaks per side).
    So what x FACED on serve is the opponent's played/converted.
    """
    svpt = _num(total.get(f"totservplayed{own}"))
    first_in = _num(total.get(f"ptsplayed1stserv{own}"))
    first_won = _num(total.get(f"ptswon1stserv{own}"))
    serve_won = _num(total.get(f"ptstotwonserv{own}"))
    second_won = serve_won - first_won if None not in (serve_won, first_won) else None
    faced = _num(total.get(f"breakptsplayed{opp}"))
    broken = _num(total.get(f"breakptsconv{opp}"))
    saved = faced - broken if None not in (faced, broken) else None
    return {
        "ace": _num(total.get(f"aces{own}")),
        "df": _num(total.get(f"dblflt{own}")),
        "svpt": svpt,
        "1stIn": first_in,
        "1stWon": first_won,
        "2ndWon": second_won,
        "SvGms": _num(total.get(f"servgamesplayed{own}")),
        "bpSaved": saved,
        "bpFaced": faced,
    }


def _sackmann_row(total: dict, winner_side: str) -> dict:
    loser_side = "b" if winner_side == "a" else "a"
    row = {}
    for prefix, own, opp in (("w", winner_side, loser_side), ("l", loser_side, winner_side)):
        for key, value in _side_columns(total, own, opp).items():
            row[f"{prefix}_{key}"] = None if value is None else str(value)
    return row


def _winner_side(match: dict) -> str | None:
    """'a' / 'b' from the result string ("[2]V. Hruncakova d J. Daniel 6-4,6-3").

    The `Winner` field is not a side flag (it read "2" on a match player A
    won), so the name left of " d " decides; set counts are the fallback."""
    result = str(match.get("ResultString") or "")
    if " d " in result:
        left = result.split(" d ", 1)[0].lower()
        last_a = str(match.get("PlayerNameLastA") or "").lower()
        last_b = str(match.get("PlayerNameLastB") or "").lower()
        if last_a and last_a in left and not (last_b and last_b in left):
            return "a"
        if last_b and last_b in left and not (last_a and last_a in left):
            return "b"
    sets_a = sets_b = 0
    for n in range(1, 6):
        a, b = _num(match.get(f"ScoreSet{n}A")), _num(match.get(f"ScoreSet{n}B"))
        if a is None or b is None:
            continue
        sets_a += a > b
        sets_b += b > a
    if sets_a != sets_b:
        return "a" if sets_a > sets_b else "b"
    return None


def _resolve_player(conn, full_name: str) -> int | None:
    """Unique WTA player by exact (case-insensitive) name, else None.

    Read-only on purpose: creating players from this feed is the wiring step's
    decision, and a wrong merge is worse than an unresolved row."""
    rows = conn.execute(
        "SELECT id FROM players WHERE tour = 'WTA' AND lower(trim(name)) = lower(trim(?)) LIMIT 2",
        (full_name,),
    ).fetchall()
    return int(rows[0]["id"]) if len(rows) == 1 else None


def _match_date(match: dict, tournament: dict) -> str:
    stamp = str(match.get("MatchTimeStamp") or "")[:10]
    try:
        return date.fromisoformat(stamp).isoformat()
    except ValueError:
        return str(tournament.get("startDate") or "")[:10]


def ingest_wta_match_stats(
    start_date: str,
    end_date: str,
    *,
    provider: WtaStatsProvider | None = None,
    pause_seconds: float = 0.5,
    sleeper=None,
    max_matches: int | None = None,
) -> dict:
    """Finished WTA/125/Slam singles (main + qualifying) in [start, end].

    Idempotent: a match already stored with OK stats is not fetched again, so
    the daily job re-reads only the open window and new matches. NO_STATS
    rows (walkovers, a feed gap) are retried on the next run.
    """
    provider = provider or WtaStatsProvider()
    sleep = sleeper or time.sleep
    summary = {
        "provider": PROVIDER_NAME, "start": start_date, "end": end_date,
        "tournaments": 0, "tournaments_skipped_itf": 0, "matches_seen": 0,
        "matches_with_stats": 0, "matches_without_stats": 0,
        "already_stored": 0, "players_unresolved": 0, "errors": [],
    }
    with get_connection() as conn:
        ensure_wta_stats_schema(conn)
    try:
        tournaments = provider.list_tournaments(start_date, end_date)
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append({"stage": "list_tournaments", "error": str(exc)[:300]})
        return summary
    fetched = 0
    for tournament in tournaments:
        group = tournament.get("tournamentGroup") or {}
        level = str(group.get("level") or tournament.get("level") or "")
        if level in SKIP_LEVELS:
            summary["tournaments_skipped_itf"] += 1
            continue
        tid, year = str(group.get("id") or ""), int(tournament.get("year") or 0)
        if not tid or not year:
            continue
        summary["tournaments"] += 1
        try:
            matches = provider.fetch_matches(tid, year)
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append({"tournament": tid, "error": str(exc)[:300]})
            continue
        singles = [
            m for m in matches
            if m.get("DrawMatchType") == "S" and m.get("MatchState") == "F"
            and m.get("PlayerIDA") and m.get("PlayerIDB")
        ]
        stats_by_match: dict[str, dict | None] = {}
        for match in singles:
            match_date = _match_date(match, tournament)
            if not (start_date <= match_date <= end_date):
                continue
            summary["matches_seen"] += 1
            with get_connection() as conn:
                done = conn.execute(
                    "SELECT 1 FROM wta_match_stats WHERE tournament_id = ? AND year = ? "
                    "AND wta_match_id = ? AND stats_status = 'OK' LIMIT 1",
                    (tid, year, match["MatchID"]),
                ).fetchone()
            if done:
                summary["already_stored"] += 1
                continue
            if max_matches is not None and fetched >= max_matches:
                break
            if fetched:
                sleep(pause_seconds)
            fetched += 1
            try:
                stats_by_match[match["MatchID"]] = provider.fetch_match_stats(tid, year, match["MatchID"])
            except Exception as exc:  # noqa: BLE001
                summary["errors"].append({"match": f"{tid}/{match['MatchID']}", "error": str(exc)[:200]})
                stats_by_match[match["MatchID"]] = None
        if not stats_by_match:
            continue
        raw_id = store_raw_response(
            PROVIDER_NAME, "/tennis/tournaments/{id}/{year}/matches[/stats]",
            {"tournament_id": tid, "year": year},
            {"tournament": tournament,
             "matches": [m for m in singles if m["MatchID"] in stats_by_match],
             "stats": stats_by_match},
            200, "wta_match_stats", f"{tid}-{year}",
        )
        now = utc_now()
        with get_connection() as conn:
            for match in singles:
                if match["MatchID"] not in stats_by_match:
                    continue
                total = stats_by_match[match["MatchID"]]
                winner = _winner_side(match)
                ok = bool(total and _num(total.get("totservplayeda")) and winner)
                summary["matches_with_stats" if ok else "matches_without_stats"] += 1
                metrics = {}
                if ok:
                    row = _sackmann_row(total, winner)
                    metrics = {
                        "a": _metrics(row, "w" if winner == "a" else "l", "l" if winner == "a" else "w"),
                        "b": _metrics(row, "w" if winner == "b" else "l", "l" if winner == "b" else "w"),
                    }
                names = {
                    side: f"{match.get(f'PlayerNameFirst{side.upper()}') or ''} "
                          f"{match.get(f'PlayerNameLast{side.upper()}') or ''}".strip()
                    for side in ("a", "b")
                }
                ids = {side: _resolve_player(conn, names[side]) for side in ("a", "b")}
                for side, opp in (("a", "b"), ("b", "a")):
                    if ids[side] is None:
                        summary["players_unresolved"] += 1
                    cols = _side_columns(total, side, opp) if ok else {}
                    m = metrics.get(side, {})
                    conn.execute(
                        """
                        INSERT INTO wta_match_stats (
                            tournament_id, year, wta_match_id, side, wta_player_id,
                            player_name, opponent_wta_id, opponent_name, player_id,
                            opponent_id, match_date, tournament_name, tournament_level,
                            surface, draw_level, round_id, won, score, stats_status,
                            ace_count, double_fault_count, serve_points, first_serves_in,
                            first_serve_points_won, second_serve_points_won,
                            service_games_played, break_points_saved, break_points_faced,
                            break_points_converted, break_points_chances, hold_rate,
                            break_rate, first_serve_points_won_pct,
                            second_serve_points_won_pct, return_points_won_pct,
                            source_provider, raw_response_id, fetched_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(tournament_id, year, wta_match_id, side) DO UPDATE SET
                            player_id = excluded.player_id,
                            opponent_id = excluded.opponent_id,
                            won = excluded.won,
                            stats_status = excluded.stats_status,
                            ace_count = excluded.ace_count,
                            double_fault_count = excluded.double_fault_count,
                            serve_points = excluded.serve_points,
                            first_serves_in = excluded.first_serves_in,
                            first_serve_points_won = excluded.first_serve_points_won,
                            second_serve_points_won = excluded.second_serve_points_won,
                            service_games_played = excluded.service_games_played,
                            break_points_saved = excluded.break_points_saved,
                            break_points_faced = excluded.break_points_faced,
                            break_points_converted = excluded.break_points_converted,
                            break_points_chances = excluded.break_points_chances,
                            hold_rate = excluded.hold_rate,
                            break_rate = excluded.break_rate,
                            first_serve_points_won_pct = excluded.first_serve_points_won_pct,
                            second_serve_points_won_pct = excluded.second_serve_points_won_pct,
                            return_points_won_pct = excluded.return_points_won_pct,
                            raw_response_id = excluded.raw_response_id,
                            fetched_at = excluded.fetched_at
                        """,
                        (
                            tid, year, match["MatchID"], side.upper(),
                            str(match.get(f"PlayerID{side.upper()}") or ""), names[side],
                            str(match.get(f"PlayerID{opp.upper()}") or ""), names[opp],
                            ids[side], ids[opp], _match_date(match, tournament),
                            tournament.get("title"), level, tournament.get("surface"),
                            match.get("DrawLevelType"), str(match.get("RoundID") or ""),
                            None if winner is None else int(winner == side),
                            match.get("ScoreString"), "OK" if ok else "NO_STATS",
                            cols.get("ace"), cols.get("df"), cols.get("svpt"),
                            cols.get("1stIn"), cols.get("1stWon"), cols.get("2ndWon"),
                            cols.get("SvGms"), m.get("break_points_saved"),
                            m.get("break_points_faced"), m.get("break_points_converted"),
                            m.get("break_points_chances"), m.get("hold_rate"),
                            m.get("break_rate"), m.get("first_serve_points_won_pct"),
                            m.get("second_serve_points_won_pct"),
                            m.get("return_points_won_pct"), PROVIDER_NAME, raw_id, now,
                        ),
                    )
        if max_matches is not None and fetched >= max_matches:
            break
    return summary


def wta_serve_stats_health(conn, as_of_date: str) -> dict:
    """What the serve models READ for WTA vs what this feed HOLDS.

    Two dates on purpose: until the wiring change ships, ace_model and
    serve_return still read player_match_history, so a fresh feed here does
    not make the WTA serve profiles fresh. Printing both keeps that visible.
    """
    used = conn.execute(
        "SELECT MAX(match_date) FROM player_match_history "
        "WHERE tour = 'WTA' AND ace_count IS NOT NULL AND match_date < ?",
        (as_of_date,),
    ).fetchone()[0]
    held = None
    try:
        held = conn.execute(
            "SELECT MAX(match_date) FROM wta_match_stats WHERE stats_status = 'OK' "
            "AND match_date < ?",
            (as_of_date,),
        ).fetchone()[0]
    except Exception:  # noqa: BLE001 -- table absent before the first ingest
        held = None

    def age(value):
        if not value:
            return None
        return (date.fromisoformat(as_of_date) - date.fromisoformat(value[:10])).days

    return {
        "model_serve_latest": used,
        "model_serve_age_days": age(used),
        "feed_latest": held,
        "feed_age_days": age(held),
    }
