"""The formal banker rule (steady B2, EXP-20261027-21), rewritten without the old engine.

EXP-20261103-13 tested simpler selectors (highest joint probability) against B2 and could
not tell them apart on 59-79 games, so the pre-registered fallback keeps B2's rules:

strict pool    L10 and L5 hit rate >= 80%, price >= 1.20, CoV <= 0.65, L3 average >= line,
               L10 average >= line x 1.15, no bench/day-to-day/early-season flag
fallback pool  (only when strict builds nothing) 70% / 70%, price >= 1.15, CoV <= 0.75,
               L3 average >= line x 0.85
AST guard      an AST line at or above the L10 median needs S - market >= 3pp (the old
               engine asked its Monte Carlo for the same edge)
build          greedy from each of the 20 best seeds toward a 2.0-3.5 (fallback 4.0) leg-price
               product, 2-4 legs, one leg per player, <=2 PTS and <=1 AST legs per team, <=3
               legs per team; best by 0.6 x mean L10 hit + 0.1 x total edge + 2 per leg
               + 10 per 100%-L10 leg + 5 per 90%-L10 leg.

Hit rates and edges are in percent, as the rule was written. Edge = C - 1/price.
"""
from __future__ import annotations

import math
from collections import Counter

from .legs import Leg

STRICT = dict(hit=80, l5=80, min_price=1.20, max_cov=0.65, l3_factor=1.0, buffer=0.15, target=(2.0, 3.5))
FALLBACK = dict(hit=70, l5=70, min_price=1.15, max_cov=0.75, l3_factor=0.85, buffer=None, target=(2.0, 4.0))
EARLY_FLAGS = {"l10_mostly_previous_season", "new_team"}
BLOCK_FLAGS = {"bench_minutes", "volatile_3pm"}
PLAYOFF_PHASES = {"PLAYOFFS", "PLAY_IN"}
SEEDS = 20
TOLERANCE = 1.2
MIN_LEGS, MAX_LEGS = 2, 4


def pct(x):
    return round(100 * x, 1)


def edge(leg: Leg) -> float:
    return round(100 * (leg.p_c or 0.0) - round(100 / leg.price, 2), 2)


def ast_guard_ok(leg: Leg) -> bool:
    if leg.stat != "AST" or not leg.line or not leg.median or leg.line < leg.median:
        return True
    return leg.p_s is not None and 100 * (leg.p_s - leg.market) >= 3


def playoff_ok(leg: Leg, phase: str | None) -> bool:
    if phase not in PLAYOFF_PHASES:
        return True
    if 0 < leg.minutes_l10 < 18 or (leg.l3_avg > 0 and leg.l3_avg < leg.line * 0.8):
        return False
    if leg.stat == "AST" and leg.cov > 0.45 and leg.minutes_l10 < 30:
        return False
    return max(pct(leg.p_c or 0), pct(leg.hit_l10)) >= 60 and pct(leg.hit_l5) >= 60


def pool(legs, rule, phase=None):
    out = []
    for leg in legs:
        if leg.p_c is None or leg.availability != "ok" or (BLOCK_FLAGS | EARLY_FLAGS) & set(leg.flags):
            continue
        if pct(leg.hit_l10) < rule["hit"] or pct(leg.hit_l5) < rule["l5"]:
            continue
        if leg.price < rule["min_price"] or leg.cov > rule["max_cov"]:
            continue
        if leg.l3_avg < leg.line * rule["l3_factor"]:
            continue
        if rule["buffer"] is not None and leg.line > 0 and leg.avg > 0 and (leg.avg - leg.line) / leg.line < rule["buffer"]:
            continue
        if not ast_guard_ok(leg) or not playoff_ok(leg, phase):
            continue
        out.append(leg)
    if rule is STRICT:
        out.sort(key=lambda l: (-pct(l.hit_l10), -pct(l.hit_l5), -edge(l), l.price))
    else:
        out.sort(key=lambda l: (-pct(l.hit_l10), -edge(l), l.price))
    return out


def allowed(combo) -> bool:
    teams = Counter(l.team for l in combo)
    pts = Counter(l.team for l in combo if l.stat == "PTS")
    ast = Counter(l.team for l in combo if l.stat == "AST")
    return (len({l.player for l in combo}) == len(combo) and max(pts.values(), default=0) <= 2
            and max(ast.values(), default=0) <= 1)


def product(combo) -> float:
    return math.prod(l.price for l in combo)


def score(combo) -> float:
    hits = [pct(l.hit_l10) for l in combo]
    return (sum(hits) / len(hits) * 0.6 + sum(edge(l) for l in combo) * 0.1 + len(combo) * 2
            + sum(10 for h in hits if h >= 100) + sum(5 for h in hits if 90 <= h < 100))


def build_from(p, seed, lo, hi):
    combo = [p[seed]]
    for cand in p:
        if len(combo) >= MAX_LEGS:
            break
        if cand.player in {l.player for l in combo}:
            continue
        if cand.stat == "PTS" and sum(l.stat == "PTS" and l.team == cand.team for l in combo) >= 2:
            continue
        if sum(l.team == cand.team for l in combo) >= 3:
            continue
        test = combo + [cand]
        if not allowed(test):
            continue
        if product(test) > hi and len(test) >= MIN_LEGS:
            if len(combo) >= 2:   # swap out one of the three highest-priced non-seed legs
                for i in sorted(range(1, len(combo)), key=lambda i: -combo[i].price)[:3]:
                    swapped = [l for j, l in enumerate(combo) if j != i] + [cand]
                    if allowed(swapped) and lo <= product(swapped) <= hi:
                        combo = swapped
                        break
            continue
        combo.append(cand)
        if len(combo) >= MIN_LEGS and (product(combo) >= (lo + hi) / 2 or (product(combo) >= lo and len(combo) >= MIN_LEGS + 1)):
            break
    if len(combo) >= MIN_LEGS and lo <= product(combo) <= hi * TOLERANCE:
        return combo
    return None


def build(p, lo, hi):
    best, best_score = [], -999.0
    for seed in range(min(len(p), SEEDS)):
        combo = build_from(p, seed, lo, hi)
        if combo and product(combo) <= hi * TOLERANCE and score(combo) > best_score:
            best, best_score = combo, score(combo)
    return best


def pool_sizes(legs, phase=None) -> dict:
    """How many legs pass each pool's single-leg rules (the NO BET explanation)."""
    return {"strict": len(pool(legs, STRICT, phase)), "fallback": len(pool(legs, FALLBACK, phase))}


def select_b2(legs: list[Leg], phase: str | None = None) -> tuple[list[Leg], str]:
    """(combo, rule): rule is 'banker', 'banker_fallback' or 'none'."""
    combo = build(pool(legs, STRICT, phase), *STRICT["target"])
    if combo:
        return combo, "banker"
    combo = build(pool(legs, FALLBACK, phase), *FALLBACK["target"])
    return combo, ("banker_fallback" if combo else "none")
