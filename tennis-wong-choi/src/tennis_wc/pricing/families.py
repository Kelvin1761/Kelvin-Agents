"""Prop families: classify a bookmaker market, and decide if a side is value.

Value is judged on the odds-blind model probability (EXP-20260801: judging on
the market-blended number multiplied every edge by the model weight). Limits
are per family; see docs/experiments for the measurements behind each.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

def _text(market_key: str, market_name: str) -> str:
    return re.sub(r"\s+", " ", f"{market_key} {market_name}".lower().replace("_", " ")).strip()


def family_for_market(market_key: str, market_name: str = "") -> str:
    key = str(market_key or "").lower()
    if key.startswith("player_double_faults_"):
        return "player_double_faults"
    if key.startswith("player_total_games_"):
        return "player_total_games"
    if key.startswith("player_win_a_set_"):
        return "player_win_a_set"
    if key.startswith("first_set_winner_"):
        return "first_set_winner"
    if key.startswith("player_first_set_match_"):
        return "player_first_set_match"
    if key.startswith("player_first_set_game_handicap_"):
        return "player_first_set_game_handicap"
    if key.startswith("player_game_handicap_"):
        return "player_game_handicap"
    if key.startswith("player_set_handicap_"):
        return "player_set_handicap"
    if key.startswith("player_exact_set_score_"):
        return "player_exact_set_score"
    if key.startswith("total_match_games"):
        return "match_total_games"
    name = str(market_name or "")
    text = _text(key, name)
    if key == "set_betting" and name.strip().lower() == "set betting":
        return "player_exact_set_score"
    if "double fault" in text:
        return "player_double_faults"
    if "to win at least one set" in text or "to win at least 1 set" in text:
        return "player_win_a_set"
    if (
        "first set winner" in text or "1st set winner" in text
        or "set 1 winner" in text
    ):
        return "first_set_winner"
    if key in {
        "to_win_1st_set_and_win_match", "to_lose_1st_set_and_win_match"
    }:
        return "player_first_set_match"
    if key == "set_handicap" or (
        "set handicap" in text and "game handicap" not in text
    ):
        return "player_set_handicap"
    if key == "game_handicap" and re.search(r"\b(?:set\s*1|1st\s+set)\b", text):
        return "player_first_set_game_handicap"
    if key == "game_handicap" and not re.search(r"\bset\s+[123]\b", text):
        return "player_game_handicap"
    if "break point" in text:
        return "micro_break_points"
    if "service game" in text:
        return "service_game_micro"
    if "aces" in text:
        if re.search(r"total\s+.+?\s+aces\s+\d", name, re.I):
            return "player_aces"
        if key.startswith("total_aces") or key == "total_aces_in_the_match":
            return "match_total_aces"
        if "_aces_" in key or key.endswith("_aces"):
            return "player_aces"
    if "total games" in text:
        lowered = name.lower()
        if not any(token in lowered for token in ("set ", "alternative", "match total")):
            if re.match(r"^.+?\s+total games(?:\s+\d|\s*$)", name, re.I):
                return "player_total_games"
        return "match_total_games"
    return key


@dataclass(frozen=True)
class ValueProfile:
    # 0.06: the 0.04-0.08 edge band was the only losing band (1,633 bets).
    min_edge: float = 0.06
    min_odds: float = 1.30
    max_odds: float = 2.25
    min_probability: float = 0.58


# Underdog-priced families: a 2.25 ceiling with a 0.58 floor excluded the
# whole profitable band (2026-08-09, 329 paper bets).
_UNDERDOG_PROFILE = ValueProfile(max_odds=6.0, min_probability=0.0)

# First set winner: ceiling 4.0; past it the model disagrees with the book
# by 25-37 points, the signature of a data error, not value.
_FIRST_SET_PROFILE = ValueProfile(max_odds=4.0, min_probability=0.0)

VALUE_PROFILES: dict[str, ValueProfile] = {
    "player_win_a_set": _UNDERDOG_PROFILE,
    "player_game_handicap": _UNDERDOG_PROFILE,
    "first_set_winner": _FIRST_SET_PROFILE,
}

DEFAULT_VALUE_PROFILE = ValueProfile()


def value_profile(market_key: str, market_name: str = "") -> ValueProfile:
    return VALUE_PROFILES.get(
        family_for_market(market_key, market_name), DEFAULT_VALUE_PROFILE
    )


def value_profile_for_family(family: str) -> ValueProfile:
    return VALUE_PROFILES.get(str(family or ""), DEFAULT_VALUE_PROFILE)


def is_value_selection(
    raw_probability: float,
    fair_probability: float,
    odds: float,
    profile: ValueProfile,
) -> bool:
    try:
        raw = float(raw_probability)
        fair = float(fair_probability)
        price = float(odds)
    except (TypeError, ValueError):
        return False
    return (
        raw - fair >= profile.min_edge
        and raw * price - 1.0 > 0
        and profile.min_odds <= price <= profile.max_odds
    )
