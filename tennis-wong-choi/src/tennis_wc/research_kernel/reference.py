"""Independent exact research oracle for fixed iid point/game probabilities.

Rules: ITF Rules of Tennis 2026, rules 5(b), 6, 7 and 14.
This mathematical oracle does not establish that real players are iid or that
hold probabilities identify their point-level skills. No production imports it.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np


def hold_probability(point_probability: float) -> float:
    p = float(point_probability)
    if not 0 < p < 1:
        raise ValueError('point probability must be strictly between zero and one')
    q = 1-p
    return p**4*(1+4*q+10*q*q)+20*p**3*q**3*p*p/(p*p+q*q)


def server_is_a(point_index: int, first_a: bool) -> bool:
    if point_index < 0:
        raise ValueError('negative point index')
    return first_a if point_index % 4 in (0, 3) else not first_a


def tiebreak_probability(p_a: float, p_b: float, *, first_a: bool = True, target: int = 7) -> float:
    if not 0 < p_a < 1 or not 0 < p_b < 1 or target not in (7, 10):
        raise ValueError('valid iid service-point probabilities and explicit 7/10-point target required')
    # Beyond target-1 each, score difference and serving phase are sufficient.
    # Solve the infinite win-by-two tail exactly as an absorbing Markov chain.
    states = [(difference, phase) for difference in (-1, 0, 1) for phase in range(4)]
    index = {state: i for i, state in enumerate(states)}
    matrix, rhs = np.eye(len(states)), np.zeros(len(states))
    for i, (difference, phase) in enumerate(states):
        probability = p_a if server_is_a(phase, first_a) else 1-p_b
        for delta, mass in ((1, probability), (-1, 1-probability)):
            new_difference = difference+delta
            if new_difference == 2:
                rhs[i] += mass
            elif new_difference != -2:
                matrix[i, index[(new_difference, (phase+1) % 4)]] -= mass
    tail = np.linalg.solve(matrix, rhs)

    @lru_cache(None)
    def value(a, b):
        if a >= target and a-b >= 2:
            return 1.
        if b >= target and b-a >= 2:
            return 0.
        if a >= target-1 and b >= target-1:
            return float(tail[index[(a-b, (a+b) % 4)]])
        p = p_a if server_is_a(a+b, first_a) else 1-p_b
        return p*value(a+1, b)+(1-p)*value(a, b+1)
    return value(0, 0)


@lru_cache(None)
def set_distribution(hold_a: float, hold_b: float, first_a: bool, tb_a: float) -> tuple:
    """Exhaustive set score masses; a tie-break counts as the thirteenth game."""
    frontier = {(0, 0): 1.}
    terminal = {}
    while frontier:
        following = {}
        for (a, b), mass in frontier.items():
            if max(a, b) >= 6 and abs(a-b) >= 2:
                terminal[(a, b)] = terminal.get((a, b), 0.)+mass
                continue
            if (a, b) == (6, 6):
                terminal[(7, 6)] = terminal.get((7, 6), 0.)+mass*tb_a
                terminal[(6, 7)] = terminal.get((6, 7), 0.)+mass*(1-tb_a)
                continue
            serving_a = first_a if (a+b) % 2 == 0 else not first_a
            p = hold_a if serving_a else 1-hold_b
            for score, chance in (((a+1, b), p), ((a, b+1), 1-p)):
                following[score] = following.get(score, 0.)+mass*chance
        frontier = following
    return tuple(sorted(terminal.items()))


def match_probability(hold_a: float, hold_b: float, *, best_of: int = 3,
                      tb_probability=None) -> float:
    if best_of not in (3, 5) or not 0 < hold_a < 1 or not 0 < hold_b < 1:
        raise ValueError('explicit BO3/BO5 and nondegenerate holds required')
    need = best_of//2+1
    # Default deliberately mirrors the CURRENT simplified tie-break law, so
    # legacy MC-vs-DP parity does not pretend to validate a point-level model.
    tb_probability = tb_probability or (lambda first_a, deciding: hold_a/(hold_a+hold_b))

    @lru_cache(None)
    def value(a, b, first_a):
        if a == need:
            return 1.
        if b == need:
            return 0.
        deciding = a == b == need-1
        distribution = set_distribution(hold_a, hold_b, first_a, tb_probability(first_a, deciding))
        result = 0.
        for (games_a, games_b), mass in distribution:
            next_first = first_a if (games_a+games_b) % 2 == 0 else not first_a
            result += mass*value(a+int(games_a > games_b), b+int(games_b > games_a), next_first)
        return result
    return value(0, 0, True)
