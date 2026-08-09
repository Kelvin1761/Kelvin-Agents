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


@dataclass(frozen=True)
class ValueProfile:
    """Pre-registered per-family limits for turning a priced prop into a bet.

    One definition, read by both the pricing layer (which decides *whether* a
    prop is a value selection) and :mod:`tennis_wc.props.strategy` /
    :mod:`tennis_wc.props.settlement` (which decide whether the family may bet
    and score the evidence).  Keeping them in one place is not tidiness: when
    the pricing limits and the gate's ``formal_profile`` disagreed, the gate
    demanded 50 settled bets inside a window the pricer never produced, so six
    of eight families sat permanently at 0/50.

    ``min_edge`` is applied to the ODDS-BLIND model edge, not the
    market-blended one.  ``min_probability`` is a sizing/gate floor only --
    applying it to selection is what excluded the underdog segment.
    """
    min_edge: float = 0.04
    min_odds: float = 1.30
    max_odds: float = 2.25
    min_probability: float = 0.58


# `player_win_a_set` and `player_game_handicap` are priced on underdogs, so a
# 2.25 ceiling and a 0.58 probability floor are mutually contradictory with
# betting them at all: a 6.0 shot is a 16.7% chance by construction.  Measured
# 2026-08-09 over 329 settled paper bets, the >=2.20 band returned +16.2%
# (n=165) while the 1.60-1.89 band inside the old ceiling returned -16.2%
# (n=87), i.e. the global limits kept the losing half and discarded the rest.
_UNDERDOG_PROFILE = ValueProfile(max_odds=6.0, min_probability=0.0)

VALUE_PROFILES: dict[str, ValueProfile] = {
    "player_win_a_set": _UNDERDOG_PROFILE,
    "player_game_handicap": _UNDERDOG_PROFILE,
}

DEFAULT_VALUE_PROFILE = ValueProfile()

# There is deliberately no tour restriction on recommendations.  One was
# planned while ITF and UTR results never arrived, but with those tiers now
# settling at ~95% they carry evidence like any other, and the per-family
# profit gate is the thing that decides what may be bet.


def value_profile(market_key: str, market_name: str = "") -> ValueProfile:
    """Return the pre-registered value limits for a market's family."""
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
    """Select on the odds-blind model; the market blend only sizes the bet.

    The blended probability is ``market + w*(raw - market)``, so measuring the
    edge on it multiplies every edge by ``w`` -- 0.23 for ``player_win_a_set``
    in August 2026 -- and a 0.04 minimum silently becomes 0.17.  When this
    landed on 2026-08-01 the value count fell from 472 to 42 and the daily
    report went quiet, while the raw model's disagreement with the market
    actually grew (0.10 -> 0.11).  The blend still decides *how much*; it no
    longer decides *whether*.
    """
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


def family_metadata(key: str) -> PropFamily | None:
    return FAMILIES.get(str(key or ""))


def supported_player_families() -> tuple[str, ...]:
    return tuple(
        key for key, family in FAMILIES.items()
        if family.model_available and family.result_scope.startswith("player_")
    )
