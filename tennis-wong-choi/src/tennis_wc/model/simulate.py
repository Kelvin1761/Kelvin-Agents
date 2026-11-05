"""Seeded Monte Carlo of a best-of-three match from two per-game hold rates.

Each trial draws one match-level shift of the hold gap (sigma
``FITTED_HOLD_GAP_DISPERSION``) so blowouts and tight matches both appear;
fixed holds alone produce far too few 6-0/6-1 sets. The seed is fixed, so the
same holds always give the same distribution.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

SEED = 20260810
FITTED_HOLD_GAP_DISPERSION = 0.06


@dataclass(frozen=True)
class MatchDistribution:
    trials: int
    games_a: list[int]
    games_b: list[int]
    sets_a: list[int]
    first_set_a: list[int]
    sets_b: list[int]
    first_set_games_a: list[int]
    first_set_games_b: list[int]

    def first_set_winner_a(self) -> float:
        return sum(self.first_set_a) / self.trials

    def first_set_match_outcomes(self) -> dict[str, float]:
        counts = {"a_win": 0, "a_lose": 0, "b_win": 0, "b_lose": 0}
        for first_a, sets_a, sets_b in zip(self.first_set_a, self.sets_a, self.sets_b):
            if sets_a > sets_b:
                counts["a_win" if first_a else "a_lose"] += 1
            else:
                counts["b_lose" if first_a else "b_win"] += 1
        return {key: value / self.trials for key, value in counts.items()}

    def first_set_game_handicap_cover_a(self, handicap: float) -> float:
        won = sum(1 for a, b in zip(self.first_set_games_a, self.first_set_games_b) if a - b + handicap > 0)
        return won / self.trials

    def expected_first_set_margin(self) -> float:
        return sum(a - b for a, b in zip(self.first_set_games_a, self.first_set_games_b)) / self.trials

    def player_games_over_a(self, line: float) -> float:
        return sum(1 for value in self.games_a if value > line) / self.trials

    def game_handicap_cover_a(self, handicap: float) -> float:
        return sum(1 for a, b in zip(self.games_a, self.games_b) if a - b + handicap > 0) / self.trials

    def expected_margin(self) -> float:
        return sum(a - b for a, b in zip(self.games_a, self.games_b)) / self.trials


def _play_set(rng: random.Random, hold_a: float, hold_b: float, a_serves_first: bool):
    """(games_a, games_b); a 6-6 tie-break goes to the stronger server overall."""
    a = b = 0
    a_serving = a_serves_first
    while True:
        server_holds = hold_a if a_serving else hold_b
        if rng.random() < server_holds:
            if a_serving:
                a += 1
            else:
                b += 1
        elif a_serving:
            b += 1
        else:
            a += 1
        a_serving = not a_serving
        if a >= 6 and a - b >= 2:
            return a, b
        if b >= 6 and b - a >= 2:
            return a, b
        if a == 6 and b == 6:
            edge = hold_a / (hold_a + hold_b) if (hold_a + hold_b) else 0.5
            if rng.random() < edge:
                return 7, 6
            return 6, 7


def simulate_match(hold_a: float, hold_b: float, *, trials: int,
                   dispersion: float = 0.0) -> MatchDistribution:
    """``dispersion``: SD of the per-match hold-gap shift (0 = fixed holds)."""
    rng = random.Random(SEED)
    sets_needed = 2
    games_a: list[int] = []
    games_b: list[int] = []
    sets_a: list[int] = []
    sets_b: list[int] = []
    first_set_a: list[int] = []
    first_set_games_a: list[int] = []
    first_set_games_b: list[int] = []
    for _ in range(trials):
        shift = rng.gauss(0.0, dispersion) if dispersion else 0.0
        match_hold_a = min(0.98, max(0.30, hold_a + shift))
        match_hold_b = min(0.98, max(0.30, hold_b - shift))
        total_a = total_b = won_a = won_b = 0
        first_set_to_a = None
        first_games_a = first_games_b = 0
        a_serves_first = True
        while won_a < sets_needed and won_b < sets_needed:
            set_a, set_b = _play_set(rng, match_hold_a, match_hold_b, a_serves_first)
            if first_set_to_a is None:
                first_games_a, first_games_b = set_a, set_b
            total_a += set_a
            total_b += set_b
            if set_a > set_b:
                won_a += 1
                if first_set_to_a is None:
                    first_set_to_a = 1
            else:
                won_b += 1
                if first_set_to_a is None:
                    first_set_to_a = 0
            if (set_a + set_b) % 2:  # 7-6 includes the tie-break game
                a_serves_first = not a_serves_first
        games_a.append(total_a)
        games_b.append(total_b)
        sets_a.append(won_a)
        sets_b.append(won_b)
        first_set_a.append(first_set_to_a or 0)
        first_set_games_a.append(first_games_a)
        first_set_games_b.append(first_games_b)
    return MatchDistribution(trials, games_a, games_b, sets_a, first_set_a, sets_b,
                             first_set_games_a, first_set_games_b)
