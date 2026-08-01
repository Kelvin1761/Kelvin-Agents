"""Canonical tennis player-prop market registry.

The bookmaker feed is deliberately treated as an inventory, not as permission
to bet.  A market may be recognised and priced while its family remains
``RESEARCH_ONLY`` until the evidence gate in :mod:`tennis_wc.props.strategy`
graduates it.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


VALIDATED_SINGLE = "VALIDATED_SINGLE"
VALIDATED_2_LEG = "VALIDATED_2_LEG"
RESEARCH_ONLY = "RESEARCH_ONLY"


@dataclass(frozen=True)
class PropFamily:
    key: str
    label: str
    result_scope: str
    combo_group: str
    model_available: bool
    reason: str = ""


FAMILIES = {
    "player_aces": PropFamily(
        "player_aces", "Player Aces", "player_aces", "serve_count", True
    ),
    "match_total_aces": PropFamily(
        "match_total_aces", "Match Total Aces", "match_aces", "serve_count", True
    ),
    "player_double_faults": PropFamily(
        "player_double_faults", "Player Double Faults", "player_double_faults",
        "serve_error", True,
    ),
    "player_total_games": PropFamily(
        "player_total_games", "Player Total Games Won", "player_games",
        "player_games", True,
    ),
    "player_win_a_set": PropFamily(
        "player_win_a_set", "Player To Win At Least One Set", "player_win_set",
        "set_outcome", True,
    ),
    "first_set_winner": PropFamily(
        "first_set_winner", "First Set Winner", "first_set_winner",
        "set_outcome", True,
    ),
    "player_game_handicap": PropFamily(
        "player_game_handicap", "Player Game Handicap", "player_game_margin",
        "game_margin", True,
    ),
    "player_set_handicap": PropFamily(
        "player_set_handicap", "Player Set Handicap", "player_set_margin",
        "set_outcome", True,
    ),
    "player_exact_set_score": PropFamily(
        "player_exact_set_score", "Player Exact Set Score",
        "player_exact_set_score", "set_outcome", True,
    ),
    "micro_break_points": PropFamily(
        "micro_break_points", "Conditional Break Points", "unsupported",
        "in_play_micro", False, "conditional single-game/in-play market",
    ),
    "service_game_micro": PropFamily(
        "service_game_micro", "Service Game Micro Market", "unsupported",
        "in_play_micro", False, "single-game score market is not a stable pre-match player total",
    ),
}


def _text(market_key: str, market_name: str) -> str:
    return re.sub(r"\s+", " ", f"{market_key} {market_name}".lower().replace("_", " ")).strip()


def family_for_market(market_key: str, market_name: str = "") -> str:
    """Return one canonical family for a Sportsbet market."""
    key = str(market_key or "").lower()
    if key.startswith("player_double_faults_"):
        return "player_double_faults"
    if key.startswith("player_total_games_"):
        return "player_total_games"
    if key.startswith("player_win_a_set_"):
        return "player_win_a_set"
    if key.startswith("first_set_winner_"):
        return "first_set_winner"
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
    if key == "set_handicap" or (
        "set handicap" in text and "game handicap" not in text
    ):
        return "player_set_handicap"
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
        # A named player's full-match total is a player prop.  Set totals,
        # alternatives and the plain match total stay outside this family.
        lowered = name.lower()
        if not any(token in lowered for token in ("set ", "alternative", "match total")):
            if re.match(r"^.+?\s+total games\s+\d", name, re.I):
                return "player_total_games"
        return "match_total_games"
    return key


def family_metadata(key: str) -> PropFamily | None:
    return FAMILIES.get(str(key or ""))


def supported_player_families() -> tuple[str, ...]:
    return tuple(
        key for key, family in FAMILIES.items()
        if family.model_available and family.result_scope.startswith("player_")
    )
