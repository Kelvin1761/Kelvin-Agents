#!/usr/bin/env python3
"""Frozen-holdout comparison for the player game-handicap joint simulator.

No production rows are changed.  Every variant is rebuilt from history strictly
before the prop date, then scored against the same canonical player-A cover row.
The market is the baseline to beat; a lower Brier is better.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sqlite3
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

TRIALS = 1500


def _brier(pairs: list[tuple[float, float]]) -> float | None:
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs) if pairs else None


def _bootstrap_probability_not_better(
    candidate: list[tuple[float, float]],
    baseline: list[tuple[float, float]],
    *,
    rounds: int = 2000,
    seed: int = 20260821,
) -> float | None:
    if not candidate or len(candidate) != len(baseline):
        return None
    import random

    rng = random.Random(seed)
    n = len(candidate)
    not_better = 0
    for _ in range(rounds):
        delta = 0.0
        for _index in range(n):
            i = rng.randrange(n)
            cp, cy = candidate[i]
            bp, by = baseline[i]
            delta += (cp - cy) ** 2 - (bp - by) ** 2
        not_better += delta >= 0
    return not_better / rounds


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=PROJECT_DIR / "tennis_wc.db")
    parser.add_argument("--split", required=True)
    parser.add_argument("--trials", type=int, default=TRIALS)
    args = parser.parse_args()

    from tennis_wc.features.serve_return import serve_return_profile
    from tennis_wc.props.hold_model import estimate_hold, estimate_hold_fitted
    from tennis_wc.props.match_simulator import (
        FITTED_HOLD_GAP_DISPERSION,
        simulate_match,
    )

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT p.match_id,p.match_date,p.line,p.model_prob_raw,p.market_prob_fair,
               p.result_status,m.player_a_id,m.player_b_id,
               COALESCE((SELECT lower(tl.surface) FROM tournament_levels tl
                         WHERE tl.tournament_id=m.tournament_id
                           AND tl.surface IS NOT NULL
                         ORDER BY tl.id DESC LIMIT 1),'unknown') AS surface
        FROM prop_tracker p JOIN matches m ON m.id=p.match_id
        WHERE p.prop_scope='player_game_margin'
          AND p.side='over'
          AND p.result_status IN ('WON','LOST')
          AND p.is_point_in_time = 1
          AND p.model_prob_raw IS NOT NULL
          AND p.market_prob_fair IS NOT NULL
          AND p.match_date >= ?
        ORDER BY p.match_date,p.match_id,p.id
        """,
        (args.split,),
    ).fetchall()

    variants: dict[str, list[tuple[float, float]]] = defaultdict(list)
    by_surface: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    cache: dict[tuple, object] = {}
    missing_profiles = 0
    for row in rows:
        a = serve_return_profile(
            conn, row["player_a_id"], row["match_date"], surface=row["surface"]
        )
        b = serve_return_profile(
            conn, row["player_b_id"], row["match_date"], surface=row["surface"]
        )
        hand_a = estimate_hold(a, b, return_weight=0.35, elo_weight=0.04)
        hand_b = estimate_hold(b, a, return_weight=0.35, elo_weight=0.04)
        fitted_a = estimate_hold_fitted(a, b)
        fitted_b = estimate_hold_fitted(b, a)
        if not all(x.is_usable for x in (hand_a, hand_b, fitted_a, fitted_b)):
            missing_profiles += 1
            continue

        actual = 1.0 if row["result_status"] == "WON" else 0.0
        fixed = {
            "stored_raw": float(row["model_prob_raw"]),
            "market": float(row["market_prob_fair"]),
        }
        estimates = {
            "hand_sigma_0": (hand_a.probability, hand_b.probability, 0.0),
            "hand_sigma_006": (
                hand_a.probability, hand_b.probability, FITTED_HOLD_GAP_DISPERSION,
            ),
            "fitted_sigma_0": (fitted_a.probability, fitted_b.probability, 0.0),
            "fitted_sigma_006": (
                fitted_a.probability, fitted_b.probability,
                FITTED_HOLD_GAP_DISPERSION,
            ),
        }
        probabilities = dict(fixed)
        for name, (hold_a, hold_b, dispersion) in estimates.items():
            key = (
                round(hold_a, 3), round(hold_b, 3), float(dispersion), args.trials,
            )
            if key not in cache:
                cache[key] = simulate_match(
                    key[0], key[1], trials=args.trials, dispersion=dispersion
                )
            probabilities[name] = cache[key].game_handicap_cover(
                float(row["line"]) * -1.0, "a"
            )

        surface = str(row["surface"] or "unknown")
        for name, probability in probabilities.items():
            pair = (max(0.001, min(0.999, probability)), actual)
            variants[name].append(pair)
            by_surface[surface][name].append(pair)

    market = variants.get("market", [])
    payload = {
        "split": args.split,
        "canonical_props": len(rows),
        "scored_with_serve_profiles": len(market),
        "missing_profiles": missing_profiles,
        "trials": args.trials,
        "overall": {},
        "by_surface": {},
    }
    for name, pairs in variants.items():
        brier = _brier(pairs)
        market_brier = _brier(market)
        payload["overall"][name] = {
            "n": len(pairs),
            "brier": round(brier, 6) if brier is not None else None,
            "gain_vs_market": (
                round(market_brier - brier, 6)
                if brier is not None and market_brier is not None else None
            ),
            "p_not_better_than_market": (
                round(_bootstrap_probability_not_better(pairs, market), 4)
                if name != "market" else None
            ),
        }
    for surface, surface_variants in sorted(by_surface.items()):
        surface_market = surface_variants.get("market", [])
        market_brier = _brier(surface_market)
        payload["by_surface"][surface] = {
            name: {
                "n": len(pairs),
                "brier": round(_brier(pairs), 6),
                "gain_vs_market": round(market_brier - _brier(pairs), 6),
            }
            for name, pairs in surface_variants.items()
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
