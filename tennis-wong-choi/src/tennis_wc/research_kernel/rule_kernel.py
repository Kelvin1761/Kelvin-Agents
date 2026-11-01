"""Explicit iid point/rule oracle, not a fitted player model.

Uses the audited point oracle pinned at 69f7674f. No live caller, rule inference,
inverse hold-to-point inference, dispersion fit or market calibration is added.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math

from .reference import hold_probability, tiebreak_probability


@dataclass(frozen=True)
class SetRule:
    trigger_games: int | None
    target_points: int | None

    def __post_init__(self):
        if any(x is not None and type(x) is not int for x in (self.trigger_games, self.target_points)):
            raise ValueError("integer rule parameters required")
        if (self.trigger_games, self.target_points) not in {(6, 7), (6, 10), (12, 7), (None, None)}:
            raise ValueError("unsupported explicit set rule")


@dataclass(frozen=True)
class AdvantageTail:
    """At 6-all: n split pairs then AA/BB yields (8+n,6+n)/(6+n,8+n)."""
    mass: float
    a_pair: float
    b_pair: float
    split_pair: float

    def winner_mass(self, a_wins: bool) -> float:
        return self.mass * (self.a_pair if a_wins else self.b_pair) / (self.a_pair + self.b_pair)

    def score_mass(self, n: int, a_wins: bool) -> float:
        if type(n) is not int or n < 0:
            raise ValueError("nonnegative split-pair count required")
        return self.mass * self.split_pair ** n * (self.a_pair if a_wins else self.b_pair)

    def games_over(self, line: float) -> float:
        n = max(0, math.floor((line - 14) / 2) + 1)
        return self.mass * self.split_pair ** n


@dataclass(frozen=True)
class SetLaw:
    first_a: bool
    scores: tuple[tuple[int, int, float], ...]
    tail: AdvantageTail | None

    def total_mass(self) -> float:
        return sum(p for _, _, p in self.scores) + (self.tail.mass if self.tail else 0.0)

    def winner_server_masses(self) -> dict[tuple[bool, bool], float]:
        result = {}
        for a, b, mass in self.scores:
            next_a = self.first_a if (a+b) % 2 == 0 else not self.first_a
            key = (a > b, next_a)
            result[key] = result.get(key, 0.0) + mass
        if self.tail:
            # Every advantage tail terminal has an even number of games.
            for a_wins in (False, True):
                key = (a_wins, self.first_a)
                result[key] = result.get(key, 0.0) + self.tail.winner_mass(a_wins)
        return result

    def games_over(self, line: float) -> float:
        if not math.isfinite(line):
            raise ValueError("finite line required")
        return sum(p for a, b, p in self.scores if a+b > line) + (self.tail.games_over(line) if self.tail else 0.0)


def _validate(p_a, p_b, first_a):
    if any(isinstance(p, bool) or not isinstance(p, (float, int)) or not math.isfinite(p) or not 0 < p < 1
           for p in (p_a, p_b)):
        raise ValueError("finite nondegenerate service-point probabilities required")
    if type(first_a) is not bool:
        raise ValueError("explicit boolean first server required")


def set_law(p_a: float, p_b: float, *, first_a: bool, rule: SetRule) -> SetLaw:
    _validate(p_a, p_b, first_a)
    if not isinstance(rule, SetRule):
        raise ValueError("explicit SetRule required")
    return _set_law(float(p_a), float(p_b), first_a, rule)


@lru_cache(maxsize=512)
def _set_law(p_a, p_b, first_a, rule):
    h_a, h_b = hold_probability(p_a), hold_probability(p_b)
    if not 0 < h_a < 1 or not 0 < h_b < 1:
        raise ValueError("hold probability reached a numerical boundary")
    frontier = {(0, 0): 1.0}
    terminal = {}
    tail = None
    while frontier:
        following = {}
        for (a, b), mass in frontier.items():
            if max(a, b) >= 6 and abs(a-b) >= 2:
                terminal[(a, b)] = terminal.get((a, b), 0.0) + mass
                continue
            if rule.trigger_games is None and a == b == 6:
                wa, wb = h_a*(1-h_b), (1-h_a)*h_b
                split = h_a*h_b + (1-h_a)*(1-h_b)
                if wa+wb <= 0 or split >= 1:
                    raise ValueError("nonabsorbing or numerically unresolved advantage tail")
                tail = AdvantageTail(mass, wa, wb, split)
                continue
            if rule.trigger_games is not None and a == b == rule.trigger_games:
                tb = tiebreak_probability(p_a, p_b, first_a=first_a, target=rule.target_points)
                terminal[(a+1, b)] = terminal.get((a+1, b), 0.0) + mass*tb
                terminal[(a, b+1)] = terminal.get((a, b+1), 0.0) + mass*(1-tb)
                continue
            serving_a = first_a if (a+b) % 2 == 0 else not first_a
            chance = h_a if serving_a else 1-h_b
            for score, p in (((a+1, b), chance), ((a, b+1), 1-chance)):
                following[score] = following.get(score, 0.0) + mass*p
        frontier = following
    law = SetLaw(first_a, tuple((a, b, p) for (a, b), p in sorted(terminal.items())), tail)
    if abs(law.total_mass()-1.0) > 1e-8:
        raise ArithmeticError("set law lost probability mass")
    return law


def match_win_probability(p_a: float, p_b: float, *, best_of: int, first_a: bool,
                          deciding_rule: SetRule, ordinary_rule: SetRule) -> float:
    _validate(p_a, p_b, first_a)
    if type(best_of) is not int or best_of not in (3, 5):
        raise ValueError("explicit BO3/BO5 required")
    if not isinstance(deciding_rule, SetRule) or not isinstance(ordinary_rule, SetRule):
        raise ValueError("both set rules must be explicit")
    need = best_of//2+1

    @lru_cache(None)
    def value(a, b, server):
        if a == need:
            return 1.0
        if b == need:
            return 0.0
        rule = deciding_rule if a == b == need-1 else ordinary_rule
        result = 0.0
        for (winner_a, next_a), mass in set_law(p_a, p_b, first_a=server, rule=rule).winner_server_masses().items():
            result += mass * value(a+int(winner_a), b+int(not winner_a), next_a)
        return result

    return value(0, 0, first_a)
