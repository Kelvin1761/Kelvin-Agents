"""Best-of-three set outcome distribution from a match-win probability.

The table is empirical (settled BO3 matches), keyed by the favourite's match
probability; values in between are linearly interpolated.
"""
from __future__ import annotations

# favourite probability -> P(fav 2-0), P(fav 2-1), P(dog 2-1), P(dog 2-0), P(fav wins set 1)
SET_OUTCOME_TABLE: dict[float, dict[str, float]] = {
    0.5: {"F20": 0.319, "F21": 0.2, "D21": 0.182, "D20": 0.299, "set1": 0.51},
    0.55: {"F20": 0.336, "F21": 0.192, "D21": 0.18, "D20": 0.292, "set1": 0.529},
    0.6: {"F20": 0.374, "F21": 0.21, "D21": 0.165, "D20": 0.251, "set1": 0.562},
    0.65: {"F20": 0.401, "F21": 0.203, "D21": 0.161, "D20": 0.234, "set1": 0.582},
    0.7: {"F20": 0.437, "F21": 0.205, "D21": 0.152, "D20": 0.205, "set1": 0.612},
    0.75: {"F20": 0.464, "F21": 0.216, "D21": 0.139, "D20": 0.181, "set1": 0.648},
    0.8: {"F20": 0.501, "F21": 0.209, "D21": 0.118, "D20": 0.172, "set1": 0.663},
    0.85: {"F20": 0.542, "F21": 0.2, "D21": 0.116, "D20": 0.141, "set1": 0.698},
    0.9: {"F20": 0.571, "F21": 0.207, "D21": 0.098, "D20": 0.124, "set1": 0.715},
    0.95: {"F20": 0.657, "F21": 0.181, "D21": 0.078, "D20": 0.083, "set1": 0.783},
}
_KEYS = sorted(SET_OUTCOME_TABLE)


def _favourite_row(fav_prob: float) -> dict[str, float]:
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
    """P(a20), P(a21), P(b21), P(b20), P(a wins set 1) for player A."""
    if p_a >= 0.5:
        d = _favourite_row(p_a)
        out = {"a20": d["F20"], "a21": d["F21"], "b21": d["D21"], "b20": d["D20"], "a_set1": d["set1"]}
    else:
        d = _favourite_row(1 - p_a)
        out = {"a20": d["D20"], "a21": d["D21"], "b21": d["F21"], "b20": d["F20"], "a_set1": 1 - d["set1"]}
    out["three_sets"] = out["a21"] + out["b21"]
    return out


def set_handicap_cover(a_handicap: float, outcomes: dict[str, float]) -> tuple[float, float]:
    """P(player A covers a BO3 set handicap) and the expected set margin."""
    margins = {"a20": 2.0, "a21": 1.0, "b21": -1.0, "b20": -2.0}
    cover = sum(float(outcomes[k]) for k, m in margins.items() if m + float(a_handicap) > 0)
    expected = sum(float(outcomes[k]) * m for k, m in margins.items())
    return max(0.01, min(0.99, cover)), round(expected, 3)
