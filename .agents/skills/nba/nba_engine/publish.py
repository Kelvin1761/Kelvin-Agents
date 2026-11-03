"""Publication firewall: may this game's formal banker be shown as a bet right now?

Checks only what can actually go wrong, all against the sidecar (the report is bound to it
by hash):
  1. the sidecar belongs to this report;
  2. every formal combo has a live, legs-bound Sportsbet SGM quote >= 2.0 whose price is the
     one the report prints, and every leg is an over on a line Sportsbet is offering;
  3. the availability / statistics source is current and every player is on the roster.
A report without a formal combo (NO BET) passes: there is nothing to publish.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from nba_availability import availability_current
from nba_data_contract import statistics_current
from nba_identity import player_name_key
from nba_sgm_quote import quote_valid

HEADING = re.compile(r"^### .*?組合\s+(\d+|X).*?組合賠率\s*@\s*(\d+(?:\.\d+)?)", re.MULTILINE)
CATEGORY = {"pts": "points", "reb": "rebounds", "ast": "assists", "fg3m": "threes_made"}
MIN_PRICE = 2.0


def _offered(odds, leg):
    entry = ((odds.get("player_props") or {}).get(CATEGORY.get(leg.get("market"), "")) or {})
    key = player_name_key(leg.get("player", ""))
    lines = next((e.get("lines") or {} for n, e in entry.items() if player_name_key(n) == key), {})
    return any(math.isclose(float(line), float(leg["line"])) for line in lines)


def validate(report_path, odds_path, *, now=None) -> tuple[bool, list[str]]:
    report_path = Path(report_path)
    try:
        content = report_path.read_text(encoding="utf-8")
        payload = json.loads(Path(str(report_path) + ".market_legs.json").read_text(encoding="utf-8"))
        odds = json.loads(Path(odds_path).read_text(encoding="utf-8")) if odds_path else None
    except (OSError, ValueError) as exc:
        return False, [f"unreadable: {type(exc).__name__}"]
    if payload.get("report_sha256") != hashlib.sha256(content.encode()).hexdigest():
        return False, ["sidecar does not belong to this report"]
    headings = {key: float(price) for key, price in HEADING.findall(content)}
    combos = payload.get("combos") or []
    if set(headings) != {str(c.get("combo_id")) for c in combos}:
        return False, ["report and sidecar list different combos"]
    if not combos:
        return True, []
    if odds is None:
        return False, ["no Sportsbet odds to check against"]
    blocks = []
    for combo in combos:
        legs, quote = combo.get("legs") or [], combo.get("sgm_quote") or {}
        price = quote.get("decimal_odds")
        if not quote_valid(quote, odds, legs, now=now):
            blocks.append(f"combo {combo['combo_id']}: SGM quote missing, expired or not bound to these legs")
        elif not (isinstance(price, (int, float)) and price >= MIN_PRICE
                  and math.isclose(price, headings[str(combo["combo_id"])], rel_tol=1e-9)):
            blocks.append(f"combo {combo['combo_id']}: quote {price} below {MIN_PRICE} or not the printed price")
        for leg in legs:
            if leg.get("side", "over") != "over" or not _offered(odds, leg):
                blocks.append(f"combo {combo['combo_id']}: {leg.get('desc')} is not an offered milestone over")
    packet = payload.get("availability") or {}
    meta = packet.get("meta") or {}
    try:
        if not availability_current(packet, now=now) or not statistics_current(meta):
            blocks.append("availability or statistics source stale / unverified")
        else:
            rosters = meta["availability"]["rosters"]
            for combo in combos:
                for leg in combo["legs"]:
                    if player_name_key(leg["player"]) not in {player_name_key(n) for n in rosters[leg["team"]]}:
                        blocks.append(f"{leg['player']} not on the verified {leg['team']} roster")
    except (KeyError, TypeError, AttributeError) as exc:
        blocks.append(f"availability packet malformed: {type(exc).__name__}")
    return not blocks, blocks
