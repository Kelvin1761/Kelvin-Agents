"""Alert when a prop family that normally produces rows goes silent.

"Empty output is not an error" is this repo's most expensive failure mode:
on 2026-08-23 Sportsbet renamed every ace market, the pricer stopped
recognising them, and the ace families wrote zero prop_tracker rows for seven
weeks while every run reported success. An empty family looks exactly like a
quiet day unless something compares it to its own history.

A family is SILENT on `as_of_date` when it produced rows on at least
`min_active_days` of the baseline window [as_of - lookback, as_of - silent_days)
and on none of the last `silent_days` dates -- while the board as a whole was
alive (other families produced rows in that window), so an off-season or a
dead feed does not raise one alarm per family.

A family is ABSENT when it produced rows at some point BEFORE the lookback
window and none inside it, on a live board. SILENT alone cannot see this: a
family that died more than `lookback - silent_days` days ago has no baseline
left, so the alarm stops by itself -- the same 2026-08-23 rename also took
game handicaps, player/match total games, set handicaps and first-set
handicaps to ~0, and by October none of them was in anyone's baseline.
Families the bookmaker has withdrawn are listed in `WITHDRAWN_FAMILIES`
with the evidence, so the permanent ones do not train people to ignore this.

`market_group_coverage` is the feed-side half: how many of the markets an
event page advertises (`numMarkets`) we actually stored. That ratio fell from
62-73% to 27-38% on 2026-08-23 when Sportsbet stopped server-rendering the
market tabs, and nothing counted it.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import json

from tennis_wc.props.registry import family_for_market

DEFAULT_LOOKBACK_DAYS = 28
DEFAULT_SILENT_DAYS = 3
DEFAULT_MIN_ACTIVE_DAYS = 5

# Withdrawn by the bookmaker, not broken here. Verified against the live
# market tabs on 2026-10-15 (every tab of three singles fixtures listed).
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
        if family in in_window or family in WITHDRAWN_FAMILIES:
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
