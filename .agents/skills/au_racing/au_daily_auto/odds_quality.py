"""Evidence checks for captured/displayed prices; never used by scoring."""
from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo

SYDNEY = ZoneInfo("Australia/Sydney")


def valid_price(value: object) -> bool:
    if isinstance(value, bool):
        return False
    try:
        price = float(value)
    except (ValueError, TypeError, OverflowError):
        return False
    return math.isfinite(price) and price > 1.0


def has_prices(prices: object) -> bool:
    """A timestamp/empty object does not prove that any prices were captured."""
    return isinstance(prices, dict) and any(
        isinstance(pair, (list, tuple)) and len(pair) == 2
        and valid_price(pair[0]) and valid_price(pair[1])
        for pair in prices.values()
    )


def snapshot_day(key: object) -> str | None:
    raw, separator, tag = str(key).partition("|")
    if not separator or tag not in {"analysis", "morning-refresh", "morning-rebuild"}:
        return None
    try:
        stamp = datetime.fromisoformat(raw)
    except ValueError:
        return None
    # Historical naive keys were written in Sydney local time.
    if stamp.tzinfo is not None:
        stamp = stamp.astimezone(SYDNEY)
    return stamp.date().isoformat()


def has_snapshot(snapshots: object, *, day: str | None = None) -> bool:
    return isinstance(snapshots, dict) and any(
        snapshot_day(key) is not None
        and (day is None or snapshot_day(key) == day)
        and has_prices(prices)
        for key, prices in snapshots.items()
    )


def dashboard_odds_issues(payload: dict, day: str | None = None) -> list[str]:
    """Check the values actually transported to AU horse cards, per race."""
    issues = []
    for meeting in payload.get("meetings") or []:
        if str(meeting.get("region") or "").upper() != "AU":
            continue
        if day and meeting.get("date") != day:
            continue
        key = f"{meeting.get('date')}|{meeting.get('venue')}"
        entry = (payload.get("races") or {}).get(key) or {}
        listing = (entry.get("races_by_analyst") or {}).get("auto")
        if listing is None:
            listing = [race for races in (entry.get("races_by_analyst") or {}).values()
                       if isinstance(races, list) for race in races]
        seen = set()
        for race in listing:
            number = race.get("race_number")
            if number in seen:
                continue
            seen.add(number)
            horses = race.get("horses") or []
            priced = sum(valid_price(h.get("market_win_odds"))
                         and valid_price(h.get("market_place_odds")) for h in horses)
            if not horses or priced < len(horses):
                issues.append(f"{key} R{number}: dashboard win/place odds {priced}/{len(horses)} runners")
    return issues
