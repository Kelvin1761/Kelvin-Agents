"""Empirical BO3 set-outcome distribution.

One model answers every set-related derived market: given the favourite's
match-win probability, what is the joint distribution over
(fav 2-0, fav 2-1, dog 2-1, dog 2-0) and P(fav takes set 1)?

Fit on 68,876 completed BO3 season-file matches (Sackmann + TML, 2020-2026,
retirements excluded), bucketed by the favourite's rank-implied win prob.
Holdout-validated 2026-07-12 against (a) the report's old hand-picked
heuristics and (b) the iid inversion M = p^2(3-2p): the empirical table wins
on all three metrics — 4-outcome Brier 0.18075(heur)/0.17751(iid)/0.17436,
first-set 0.23799/0.23698/0.23619, goes-3-sets 0.25211/0.24128/0.22995.
Key reality the iid model misses: straight-sets endings are far MORE common
than independence predicts (form-of-the-day correlation between sets) — the
old heuristic said up to 62% three-setters for coin-flips; reality ~38%.

Live input is the model's match probability (externally validated as
well-calibrated). Table is BO3 only — BO5 markets keep their old fallbacks.
Rebuild with scripts/build_set_distribution.py after large history growth.
"""
from __future__ import annotations

# bucket (favourite match prob, 0.05 grid) -> outcome probs + P(fav wins set 1)
# F=favourite, D=underdog; F20 = favourite wins 2-0, D21 = dog wins 2-1, etc.
SET_OUTCOME_TABLE: dict[float, dict[str, float]] = {
    0.50: {"F20": 0.319, "F21": 0.200, "D21": 0.182, "D20": 0.299, "set1": 0.510},
    0.55: {"F20": 0.336, "F21": 0.192, "D21": 0.180, "D20": 0.292, "set1": 0.529},
    0.60: {"F20": 0.374, "F21": 0.210, "D21": 0.165, "D20": 0.251, "set1": 0.562},
    0.65: {"F20": 0.401, "F21": 0.203, "D21": 0.161, "D20": 0.234, "set1": 0.582},
    0.70: {"F20": 0.437, "F21": 0.205, "D21": 0.152, "D20": 0.205, "set1": 0.612},
    0.75: {"F20": 0.464, "F21": 0.216, "D21": 0.139, "D20": 0.181, "set1": 0.648},
    0.80: {"F20": 0.501, "F21": 0.209, "D21": 0.118, "D20": 0.172, "set1": 0.663},
    0.85: {"F20": 0.542, "F21": 0.200, "D21": 0.116, "D20": 0.141, "set1": 0.698},
    0.90: {"F20": 0.571, "F21": 0.207, "D21": 0.098, "D20": 0.124, "set1": 0.715},
    0.95: {"F20": 0.657, "F21": 0.181, "D21": 0.078, "D20": 0.083, "set1": 0.783},
}
_KEYS = sorted(SET_OUTCOME_TABLE)


def _fav_dist(fav_prob: float) -> dict[str, float]:
    """Linear interpolation between buckets; clamped at the table ends."""
    p = min(max(float(fav_prob), 0.5), 0.99)
    if p <= _KEYS[0]:
        return SET_OUTCOME_TABLE[_KEYS[0]]
    if p >= _KEYS[-1]:
        return SET_OUTCOME_TABLE[_KEYS[-1]]
    for lo, hi in zip(_KEYS, _KEYS[1:]):
        if lo <= p <= hi:
            t = (p - lo) / (hi - lo)
            a, b = SET_OUTCOME_TABLE[lo], SET_OUTCOME_TABLE[hi]
            return {k: a[k] * (1 - t) + b[k] * t for k in a}
    return SET_OUTCOME_TABLE[_KEYS[-1]]


def outcome_distribution(p_a: float) -> dict[str, float]:
    """Distribution oriented to PLAYER A (BO3):
    a20/a21 = A wins 2-0/2-1, b21/b20 = B wins, a_set1 = P(A takes set 1),
    three_sets = P(match goes the distance)."""
    if p_a >= 0.5:
        d = _fav_dist(p_a)
        out = {"a20": d["F20"], "a21": d["F21"], "b21": d["D21"], "b20": d["D20"],
               "a_set1": d["set1"]}
    else:
        d = _fav_dist(1 - p_a)
        out = {"a20": d["D20"], "a21": d["D21"], "b21": d["F21"], "b20": d["F20"],
               "a_set1": 1 - d["set1"]}
    out["three_sets"] = out["a21"] + out["b21"]
    return out


def first_set_win_probability(p_side: float) -> float:
    return outcome_distribution(p_side)["a_set1"]


def win_at_least_one_set_probability(p_side: float) -> float:
    """P(side wins >= 1 set) = 1 - P(opponent wins 2-0)."""
    return 1 - outcome_distribution(p_side)["b20"]


def three_sets_probability(p_a: float) -> float:
    return outcome_distribution(p_a)["three_sets"]


def set_score_probability(p_side: float, sets_lost: int) -> float | None:
    """P(side wins the match 2-<sets_lost>). BO3 only."""
    d = outcome_distribution(p_side)
    if sets_lost == 0:
        return d["a20"]
    if sets_lost == 1:
        return d["a21"]
    return None
