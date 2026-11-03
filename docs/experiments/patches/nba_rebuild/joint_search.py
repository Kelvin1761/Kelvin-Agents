"""EXP-20261103-15 K arms: highest-joint-probability banker search (NOT adopted; B2 kept).

Moved out of nba_engine after the verdict; kept here so the evaluation re-runs.

Banker selection: the 2-4 leg same-game multi most likely to land, priced >= 2.0.

1. Pool: every leg with a model probability, minus availability / role risks.
2. Value check (optional): keep a leg only when the model rates it at least the price does.
3. Exact search for the highest joint probability (legs treated as independent) among
   combinations whose leg-price product lies in [min_price, max_price] and which pass the
   structural rules (one leg per player, <=3 legs per team, <=2 PTS legs per team).

The leg-price product only shapes the search; the bet is placed at Sportsbet's real SGM
quote, which must itself be >= min_price (run.py).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


# Exactly the exclusions EXP-20261103-15 evaluated; the early-season flags are reported,
# not used (that selector was not the one measured).
EXCLUDE_FLAGS = {"bench_minutes", "volatile_3pm"}


@dataclass(frozen=True)
class Policy:
    probability: str = "p_c"     # Leg attribute the selector ranks by
    value_check: bool = False    # require probability >= 1/price on every leg
    min_legs: int = 2
    max_legs: int = 4
    min_price: float = 2.0
    max_price: float = 4.0
    max_per_team: int = 3
    max_pts_per_team: int = 2


def best_combo(items, prob, price, player, team, is_pts, policy: Policy):
    """Exact branch-and-bound: (combo, joint probability) or ([], None).

    Items are visited in descending probability, so once joint * p(next) cannot beat the
    best found, no later item can either. Adding a leg never lowers the price product, so a
    branch over max_price is dead.
    """
    items = sorted(items, key=lambda x: -prob(x))
    best, best_p = [], 0.0

    def ok(combo, x):
        if player(x) in {player(c) for c in combo}:
            return False
        if sum(team(c) == team(x) for c in combo) >= policy.max_per_team:
            return False
        return not (is_pts(x) and sum(team(c) == team(x) and is_pts(c) for c in combo) >= policy.max_pts_per_team)

    def dfs(start, combo, joint, product):
        nonlocal best, best_p
        if len(combo) >= policy.min_legs and policy.min_price <= product and joint > best_p:
            best, best_p = list(combo), joint
        if len(combo) == policy.max_legs:
            return
        for i in range(start, len(items)):
            x = items[i]
            j = joint * prob(x)
            if j <= best_p:
                break
            q = product * price(x)
            if q > policy.max_price or not ok(combo, x):
                continue
            combo.append(x)
            dfs(i + 1, combo, j, q)
            combo.pop()

    dfs(0, [], 1.0, 1.0)
    return best, (best_p if best else None)


def eligible(leg, policy: Policy) -> str | None:
    """Why a leg is out of the banker pool, or None."""
    p = getattr(leg, policy.probability)
    if p is None:
        return "no_probability"
    if leg.availability != "ok":
        return "availability"
    if EXCLUDE_FLAGS & set(leg.flags):
        return sorted(EXCLUDE_FLAGS & set(leg.flags))[0]
    if policy.value_check and p < leg.market:
        return "no_value"
    return None


def select(legs, policy: Policy = Policy()):
    """(best combo or [], funnel diagnostics)."""
    reasons = Counter(eligible(leg, policy) or "eligible" for leg in legs)
    pool = [leg for leg in legs if eligible(leg, policy) is None]
    combo, joint = best_combo(pool, lambda l: getattr(l, policy.probability), lambda l: l.price,
                              lambda l: l.player, lambda l: l.team, lambda l: l.stat == "PTS", policy)
    return combo, {"candidates": len(legs), "funnel": dict(reasons), "pool": len(pool),
                   "joint_probability": None if joint is None else round(joint, 4)}
