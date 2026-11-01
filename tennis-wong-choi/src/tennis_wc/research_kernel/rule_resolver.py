"""Historical main-draw singles rules for explicit research use only.

Event identifiers are assertions by the caller, not fuzzy identity resolution.
This package neither authenticates fixtures nor qualifies training data clocks.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
from importlib.resources import files
import json

from .rule_kernel import SetRule, match_win_probability

REGISTRY_SHA256 = "8bd52b089ed026f5e43c79b9178266ec6009c1ba1fdc16a6ab86f04da634e247"
DRAW = "adult_singles_main"
CANCELLATION_SOURCE = "https://www.usta.com/en/home/stay-current/national/usta-statement-on-the-cancellation-of-2020-wimbledon.html"


class UnsupportedRules(ValueError):
    """A missing or excluded rule context must not inherit modern rules."""


@lru_cache(maxsize=1)
def _registry():
    raw = files(__package__).joinpath("slam_rules.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != REGISTRY_SHA256:
        raise RuntimeError("historical rule registry fingerprint mismatch")
    return json.loads(raw)


@dataclass(frozen=True)
class ResolvedRules:
    event: str
    year: int
    tour: str
    draw: str
    best_of: int
    ordinary: SetRule
    deciding: SetRule
    registry_sha256: str
    rule_id: str
    source_urls: tuple[str, ...]

    def match_probability(self, p_a: float, p_b: float, *, first_a: bool) -> float:
        """Pass explicit point skills to the research kernel without fitting."""
        return match_win_probability(p_a, p_b, best_of=self.best_of, first_a=first_a,
                                     ordinary_rule=self.ordinary, deciding_rule=self.deciding)


def resolve_slam_rules(*, event: str, year: int, tour: str, draw: str) -> ResolvedRules:
    """Resolve the pinned 2011–2024 registry; all inputs must be explicit."""
    if type(year) is not int or not 2011 <= year <= 2024:
        raise UnsupportedRules("unsupported edition year")
    if type(event) is not str or event not in {"ausopen", "frenchopen", "wimbledon", "usopen"}:
        raise UnsupportedRules("unsupported canonical event")
    if type(tour) is not str or tour not in {"ATP", "WTA"}:
        raise UnsupportedRules("unsupported explicit tour")
    if type(draw) is not str or draw != DRAW:
        raise UnsupportedRules("unsupported draw")
    # The registry states hypothetical laws across a year range. It does not
    # establish that every edition in that range actually took place.
    if event == "wimbledon" and year == 2020:
        raise UnsupportedRules("cancelled edition: Wimbledon 2020; " + CANCELLATION_SOURCE)
    registry = _registry()
    matches = [r for r in registry["deciding_set"][event] if r["first_year"] <= year <= r["last_year"]]
    if len(matches) != 1:
        raise RuntimeError("historical registry must resolve exactly one interval")
    law = matches[0]
    ordinary = registry["nondeciding_set"]
    return ResolvedRules(event, year, tour, draw, registry["best_of"][tour],
                         SetRule(ordinary["tiebreak_games"], ordinary["tiebreak_points"]),
                         SetRule(law["tiebreak_games"], law["tiebreak_points"]), REGISTRY_SHA256,
                         f"{event}:{law['first_year']}-{law['last_year']}:{tour}:{draw}",
                         tuple(s["url"] for s in registry["sources"]))
