"""Silent-failure alarms (warnings in the run payload, never blockers).

* a priced family that wrote rows most days of the last 28 and none in 3 days
  (2026-08-23 Sportsbet renamed the ace markets; seven weeks at zero, no error);
* a family with history that has written nothing in the whole window;
* event pages storing under 60% of the markets Sportsbet advertises.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import json

from tennis_wc.pricing.families import family_for_market

DEFAULT_LOOKBACK_DAYS = 28
DEFAULT_SILENT_DAYS = 3
DEFAULT_MIN_ACTIVE_DAYS = 5

# Withdrawn by the bookmaker, not broken here. Verified against the live
# market tabs on 2026-10-15 (every tab of three singles fixtures listed).
# Families no longer priced on purpose (Kelvin 2026-11-05 pause; match totals
# never bettable) and the one Sportsbet withdrew: their silence is expected.
NOT_PRICED = {"player_aces", "match_total_aces", "player_double_faults",
              "player_exact_set_score", "match_total_games"}
WITHDRAWN_FAMILIES = {
    "player_first_set_match": (
        "Sportsbet withdrew 'To win/lose 1st set and win match' on 2026-08-23; "
        "no market on any tab on 2026-10-15"
    ),
}

# Below this share of the advertised markets stored per event, the feed is
# dropping tabs. With the market-group fetch, singles events store ~all of them.
MIN_MARKET_COVERAGE = 0.6


def silent_prop_families(
    conn,
    as_of_date: str,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    silent_days: int = DEFAULT_SILENT_DAYS,
    min_active_days: int = DEFAULT_MIN_ACTIVE_DAYS,
) -> list[dict]:
    as_of = date.fromisoformat(as_of_date)
    start = (as_of - timedelta(days=lookback_days)).isoformat()
    silent_from = (as_of - timedelta(days=silent_days - 1)).isoformat()
    rows = conn.execute(
        """
        SELECT match_date, market_key, COUNT(*) AS n
        FROM prop_tracker
        WHERE match_date >= ? AND match_date <= ?
        GROUP BY match_date, market_key
        """,
        (start, as_of.isoformat()),
    ).fetchall()
    days: dict[str, set[str]] = defaultdict(set)
    recent_rows: dict[str, int] = defaultdict(int)
    in_window: set[str] = set()
    board_alive = False
    for row in rows:
        family = family_for_market(row["market_key"])
        in_window.add(family)
        if row["match_date"] >= silent_from:
            recent_rows[family] += int(row["n"])
            board_alive = True
        else:
            days[family].add(row["match_date"])
    if not board_alive:
        return []
    alerts = []
    for family, active in sorted(days.items()):
        if family in NOT_PRICED:
            continue
        if len(active) >= min_active_days and recent_rows.get(family, 0) == 0:
            alerts.append({
                "source": "prop_family_silent",
                "warning": f"{family}: 0 rows for {silent_days} days",
                "family": family,
                "baseline_active_days": len(active),
                "last_active_date": max(active),
                "silent_since": silent_from,
            })
    alerts.extend(_absent_families(conn, start, in_window))
    return alerts


def _absent_families(conn, window_start: str, in_window: set[str]) -> list[dict]:
    """Families with history before the window and nothing inside it."""
    history = conn.execute(
        """
        SELECT market_key, MAX(match_date) AS last_date, COUNT(*) AS n
        FROM prop_tracker
        WHERE match_date < ?
        GROUP BY market_key
        """,
        (window_start,),
    ).fetchall()
    last: dict[str, str] = {}
    total: dict[str, int] = defaultdict(int)
    for row in history:
        family = family_for_market(row["market_key"])
        total[family] += int(row["n"])
        if row["last_date"] and row["last_date"] > last.get(family, ""):
            last[family] = row["last_date"]
    alerts = []
    for family in sorted(last):
        if family in in_window or family in WITHDRAWN_FAMILIES or family in NOT_PRICED:
            continue
        alerts.append({
            "source": "prop_family_absent",
            "warning": f"{family}: 0 rows since {last[family]} (before the {window_start} window)",
            "family": family,
            "last_active_date": last[family],
            "historical_rows": total[family],
        })
    return alerts


def market_group_coverage(conn, as_of_date: str,
                          min_coverage: float = MIN_MARKET_COVERAGE) -> list[dict]:
    """Page-advertised vs stored markets for the day's event fetches.

    Reads the `market_coverage` block the scrape provider writes into each
    stored `/event-odds` response. Responses from before that block existed
    are ignored, so this is silent on history rather than wrong about it.
    """
    rows = conn.execute(
        """
        SELECT response_json FROM raw_api_responses
        WHERE endpoint = '/event-odds' AND substr(fetched_at, 1, 10) = ?
        """,
        (as_of_date,),
    ).fetchall()
    advertised = stored = events = failed_events = 0
    for row in rows:
        try:
            coverage = json.loads(row["response_json"]).get("market_coverage")
        except (TypeError, ValueError, AttributeError):
            continue
        if not isinstance(coverage, dict) or not coverage.get("num_markets"):
            continue
        events += 1
        advertised += int(coverage["num_markets"])
        stored += int(coverage.get("page_markets") or 0) + int(
            coverage.get("group_markets_added") or 0)
        if coverage.get("groups_failed"):
            failed_events += 1
    if not events or not advertised:
        return []
    ratio = stored / advertised
    if ratio >= min_coverage and failed_events * 2 < events:
        return []
    return [{
        "source": "sportsbet_market_coverage",
        "warning": (
            f"stored {stored}/{advertised} advertised markets ({ratio:.0%}) over "
            f"{events} event pages; {failed_events} with failed market tabs"
        ),
        "coverage": round(ratio, 3),
        "events": events,
        "events_with_failed_tabs": failed_events,
    }]


SERVE_STALE_DAYS = 30


def stale_serve_history(conn, as_of_date: str) -> list[dict]:
    """WTA serve stats stopped with the Sackmann file (2026-05); say how old they are."""
    from datetime import date

    from tennis_wc.model.history import active_clause

    latest = conn.execute(
        "SELECT MAX(match_date) FROM player_match_history "
        f"WHERE tour = 'WTA' AND ace_count IS NOT NULL AND match_date < ? AND {active_clause()}",
        (as_of_date,)).fetchone()[0]
    age = (date.fromisoformat(as_of_date) - date.fromisoformat(latest[:10])).days if latest else None
    if age is not None and age <= SERVE_STALE_DAYS:
        return []
    return [{"source": "wta_serve_stats", "warning": "wta_serve_profiles_stale",
             "model_serve_latest": latest, "model_serve_age_days": age}]
