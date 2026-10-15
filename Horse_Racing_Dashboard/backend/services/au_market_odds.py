"""Transport captured market prices separately from model reports and scores."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def _price(raw):
    if isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (ValueError, TypeError, OverflowError):
        return None
    return value if math.isfinite(value) and value > 1 else None


def enrich_au_market_odds(meeting, races_by_analyst, *, now=None):
    """Read new morning prices even when the analysis markdown is unchanged.

    Only existing horse IDs receive prices. Market reference probabilities keep
    their original earliest-snapshot semantics; ranking fields are never touched.
    """
    if meeting.region.value != "au":
        return
    zone = ZoneInfo("Australia/Sydney")
    clock = now or datetime.now(zone)
    for analyst, races in races_by_analyst.items():
        folder = meeting.folder_paths.get(analyst)
        if not folder:
            continue
        try:
            history = json.loads((Path(folder) / "odds_history.json").read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(history, dict):
            continue
        for race in races:
            snapshots = history.get(str(race.race_number))
            if not isinstance(snapshots, dict):
                continue
            valid = []
            for key, prices in snapshots.items():
                raw, sep, tag = str(key).partition("|")
                if not sep or tag not in {"analysis", "morning-refresh", "morning-rebuild"}:
                    continue
                try:
                    captured = datetime.fromisoformat(raw)
                except ValueError:
                    continue
                captured = captured.replace(tzinfo=zone) if captured.tzinfo is None else captured.astimezone(zone)
                if captured > clock or captured.date().isoformat() > meeting.date:
                    continue
                if isinstance(prices, dict):
                    valid.append((captured, prices))
            if not valid:
                continue
            captured, prices = max(valid, key=lambda item: item[0])
            for horse in race.horses:
                pair = prices.get(str(horse.horse_number))
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    continue
                win, place = map(_price, pair)
                if win is None or place is None:
                    continue
                horse.market_win_odds = win
                horse.market_place_odds = place
                horse.market_odds_captured_at = captured.isoformat()
