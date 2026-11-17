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


def _bf_name(value):
    import re
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _latest_betfair(folder, meeting_date, clock, zone):
    """`betfair_odds_history.json` 最新一個（唔遲過而家、唔遲過賽日）快照 → (時間, {馬名: [贏, 位]})。"""
    try:
        history = json.loads((Path(folder) / "betfair_odds_history.json").read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(history, dict):
        return None
    valid = []
    for key, prices in history.items():
        raw, sep, _tag = str(key).partition("|")
        if not sep or not isinstance(prices, dict):
            continue
        try:
            captured = datetime.fromisoformat(raw)
        except ValueError:
            continue
        captured = captured.replace(tzinfo=zone) if captured.tzinfo is None else captured.astimezone(zone)
        if captured > clock or captured.date().isoformat() > meeting_date:
            continue
        valid.append((captured, prices))
    return max(valid, key=lambda item: item[0]) if valid else None


def enrich_betfair_odds(meeting, races_by_analyst, *, now=None):
    """Betfair 價只做顯示：按馬名貼 `betfair_*`，唔郁 Sportsbet 嘅 `market_*`。"""
    if meeting.region.value != "au":
        return
    zone = ZoneInfo("Australia/Sydney")
    clock = now or datetime.now(zone)
    for analyst, races in races_by_analyst.items():
        folder = meeting.folder_paths.get(analyst)
        latest = _latest_betfair(folder, meeting.date, clock, zone) if folder else None
        if not latest:
            continue
        captured, prices = latest
        for race in races:
            for horse in race.horses:
                pair = None
                for name in (horse.horse_name_en, horse.horse_name):
                    pair = prices.get(_bf_name(name)) if name else None
                    if pair:
                        break
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    continue
                win, place = map(_price, pair)
                if win is None and place is None:
                    continue
                horse.betfair_win_odds = win
                horse.betfair_place_odds = place
                horse.betfair_odds_captured_at = captured.isoformat()


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
