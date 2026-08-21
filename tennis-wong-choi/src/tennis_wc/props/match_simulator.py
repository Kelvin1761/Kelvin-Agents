"""Stage 3: a match from two hold probabilities.

Every games and sets prop is a function of ``hold_a`` and ``hold_b``, so one
simulator replaces seven closed forms and, more importantly, makes them
mutually consistent -- today the margin curve, the share curve and the
exact-score table imply three different distributions for the same match.

Nothing here reads odds. The whole point of the direction is a model that
stands on its own; the market is for comparing against afterwards, not for
deriving the estimate from.
"""
from __future__ import annotations

from dataclasses import dataclass
import random

DEFAULT_TRIALS = 4000
# Fixed: a price must not change because a simulation was reseeded.
SEED = 20260810

# How far the true hold GAP sits from our estimate on any given day.
#
# Drawing every service game from one fixed pair of hold rates makes a match's
# only randomness a sequence of coin flips, and real tennis is more one-sided
# than that allows. Measured over 996 settled matches with both holds usable:
# 60.9% finish in two sets against the simulator's 55.2%, and the shortfall is
# the same size on clay (+4.7pp), grass (+4.5pp) and hard (+4.2pp). Conditional
# on the number of sets the game counts are nearly exact -- 19.28 actual against
# 19.62 simulated for two-setters, 29.60 against 29.84 for three -- so the
# defect is the MIX of two-set and three-set matches, not the level.
#
# Stage 3 passed because it checked the simulator at hold_a == hold_b == 0.75,
# where there is no favourite to under-back, against a pooled mean. Fed the
# model's own asymmetric holds it over-predicts the total by 0.9 to 1.3 games
# on every surface.
#
# What is missing is that the hold estimate is an estimate: on the day, one
# player is better or worse than their rolling profile says, and that
# dispersion is what makes blowouts common. One shift per match, drawn once and
# applied antithetically so the gap moves and the total does not.
#
# Fitted to the straight-sets rate on 454 matches before 2026-07-15 and scored
# on the 542 after: the rate goes 0.552 -> 0.613 against an actual 0.609, and
# the total-games bias -- which it was NOT fitted on -- goes -1.17 to -0.17
# games. Win-a-set Brier 0.2022 -> 0.1991 over the same held-out matches.
#
# The value comes from the surfaces, not from that window. Over the whole
# settled record (1,003 matches) the straight-sets rate wants the same shift on
# all three, which is the strongest argument that this is one real effect and
# not three coincidences:
#
#              actual   sigma 0   sigma 0.05   sigma 0.06   sigma 0.07
#   Clay  266   0.594     0.547        0.579     ~0.593        0.606
#   Grass 228   0.601     0.555        0.589     ~0.602        0.616
#   Hard  240   0.613     0.559        0.593     ~0.607        0.622
#
# 0.06, from three independent surface fits, rather than the 0.07 a single
# pooled window gave.
#
# One thing it does NOT fix: grass total games. Clay and hard land within 0.2
# games, grass stays ~0.9 short, because grass SETS are longer -- more 7-5 and
# 7-6 -- which is a set-length effect and not a set-mix one. Left alone rather
# than absorbed into this parameter, which would break the two surfaces it
# currently gets right.
FITTED_HOLD_GAP_DISPERSION = 0.06

# ...and it is NOT what the pricer runs. The correction is real at the level of
# moments and invisible at the level of a prop:
#
#   player_win_a_set Brier over 728 settled props   0.2097 -> 0.2084
#   P(0.06 is no better)                            0.43
#
# Indistinguishable, and the same on each surface taken separately. That reads
# oddly next to a fix that nails the straight-sets rate, until you notice what
# the shift does: it makes blowouts commoner without saying WHOSE. It is a
# variance correction, not a ranking one, and a prop like "does this player
# take a set" needs the ranking.
#
# Replayed over all 44 dates the cost shows up where a variance change would:
#
#                        whole record   later window   drawdown
#   sigma 0, edge 0.04      +6.72%         -0.02%       -47.0u
#   sigma 0.06, edge 0.04   +7.00%         +0.12%       -52.5u
#   sigma 0, edge 0.06      +8.16%         +2.33%       -44.5u
#   sigma 0.06, edge 0.06   +9.21%         +0.23%       -50.1u
#
# Drawdown is worse in every pairing, and at the min_edge that ships the later
# window turns from +2.33% to +0.23%. Kept, fitted, documented and OFF -- flip
# it when a family whose payoff depends on the SHAPE of the distribution
# (exact set score, big game handicaps) is being staked on its own evidence.
HOLD_GAP_DISPERSION = 0.0


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

    def first_set_winner(self, player: str = "a") -> float:
        won = sum(self.first_set_a)
        return won / self.trials if player == "a" else 1 - won / self.trials

    def first_set_match_outcomes(self) -> dict[str, float]:
        """Four exhaustive outcomes: first-set result crossed with match win."""
        counts = {"a_win": 0, "a_lose": 0, "b_win": 0, "b_lose": 0}
        for first_a, sets_a, sets_b in zip(
            self.first_set_a, self.sets_a, self.sets_b
        ):
            if sets_a > sets_b:
                counts["a_win" if first_a else "a_lose"] += 1
            else:
                counts["b_lose" if first_a else "b_win"] += 1
        return {key: value / self.trials for key, value in counts.items()}

    def first_set_game_handicap_cover(
        self, handicap: float, player: str = "a"
    ) -> float:
        pairs = zip(self.first_set_games_a, self.first_set_games_b)
        if player == "a":
            won = sum(1 for a, b in pairs if (a - b) + handicap > 0)
        else:
            won = sum(1 for a, b in pairs if (b - a) + handicap > 0)
        return won / self.trials

    def expected_first_set_margin(self) -> float:
        return sum(
            a - b for a, b in zip(
                self.first_set_games_a, self.first_set_games_b
            )
        ) / self.trials

    def exact_set_score(self, player: str = "a", sets_lost: int = 0) -> float:
        """P(player wins the match 2-`sets_lost`) in a best-of-three."""
        pairs = zip(self.sets_a, self.sets_b)
        if player == "a":
            return sum(1 for a, b in pairs if a == 2 and b == sets_lost) / self.trials
        return sum(1 for a, b in pairs if b == 2 and a == sets_lost) / self.trials

    def set_handicap_cover(self, handicap: float, player: str = "a") -> float:
        pairs = zip(self.sets_a, self.sets_b)
        if player == "a":
            return sum(1 for a, b in pairs if (a - b) + handicap > 0) / self.trials
        return sum(1 for a, b in pairs if (b - a) + handicap > 0) / self.trials

    def player_games_over(self, line: float, player: str = "a") -> float:
        games = self.games_a if player == "a" else self.games_b
        return sum(1 for value in games if value > line) / self.trials

    def total_games_over(self, line: float) -> float:
        return sum(
            1 for a, b in zip(self.games_a, self.games_b) if a + b > line
        ) / self.trials

    def player_wins_a_set(self, player: str = "a") -> float:
        if player == "a":
            return sum(1 for value in self.sets_a if value >= 1) / self.trials
        return sum(1 for value in self.sets_a if value <= 1) / self.trials

    def game_handicap_cover(self, handicap: float, player: str = "a") -> float:
        """P(player's game margin + handicap > 0)."""
        pairs = zip(self.games_a, self.games_b)
        if player == "a":
            return sum(1 for a, b in pairs if (a - b) + handicap > 0) / self.trials
        return sum(1 for a, b in pairs if (b - a) + handicap > 0) / self.trials

    def expected_margin(self) -> float:
        return sum(a - b for a, b in zip(self.games_a, self.games_b)) / self.trials


def _play_set(rng: random.Random, hold_a: float, hold_b: float, a_serves_first: bool):
    """Return (games_a, games_b). Tiebreak at 6-6 decided by the two holds."""
    a = b = 0
    a_serving = a_serves_first
    while True:
        server_holds = hold_a if a_serving else hold_b
        if rng.random() < server_holds:
            if a_serving:
                a += 1
            else:
                b += 1
        else:
            if a_serving:
                b += 1
            else:
                a += 1
        a_serving = not a_serving
        if a >= 6 and a - b >= 2:
            return a, b
        if b >= 6 and b - a >= 2:
            return a, b
        if a == 6 and b == 6:
            # A tiebreak is one game to whoever is the stronger server overall.
            edge = hold_a / (hold_a + hold_b) if (hold_a + hold_b) else 0.5
            if rng.random() < edge:
                return 7, 6
            return 6, 7


def simulate_match(
    hold_a: float,
    hold_b: float,
    *,
    best_of: int = 3,
    trials: int = DEFAULT_TRIALS,
    seed: int = SEED,
    dispersion: float | None = None,
) -> MatchDistribution:
    """Joint distribution of games and sets from two per-game hold rates.

    ``dispersion`` is the standard deviation of the per-match shift in the hold
    gap; see :data:`HOLD_GAP_DISPERSION`. Pass 0.0 for the fixed-hold simulator
    the stage-3 tests pin.
    """
    sigma = HOLD_GAP_DISPERSION if dispersion is None else float(dispersion)
    rng = random.Random(seed)
    sets_needed = best_of // 2 + 1
    games_a: list[int] = []
    games_b: list[int] = []
    sets_a: list[int] = []
    sets_b: list[int] = []
    first_set_a: list[int] = []
    first_set_games_a: list[int] = []
    first_set_games_b: list[int] = []
    for _ in range(trials):
        shift = rng.gauss(0.0, sigma) if sigma else 0.0
        match_hold_a = min(0.98, max(0.30, hold_a + shift))
        match_hold_b = min(0.98, max(0.30, hold_b - shift))
        total_a = total_b = 0
        won_a = won_b = 0
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
            # Whoever received first in the last set serves first in the next.
            a_serves_first = not a_serves_first
        games_a.append(total_a)
        games_b.append(total_b)
        sets_a.append(won_a)
        sets_b.append(won_b)
        first_set_a.append(first_set_to_a or 0)
        first_set_games_a.append(first_games_a)
        first_set_games_b.append(first_games_b)
    return MatchDistribution(
        trials, games_a, games_b, sets_a, first_set_a, sets_b,
        first_set_games_a, first_set_games_b,
    )
