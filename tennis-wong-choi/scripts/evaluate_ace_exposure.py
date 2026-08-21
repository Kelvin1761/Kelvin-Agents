#!/usr/bin/env python3
"""Read-only holdout test for an ace-rate x service-games exposure model."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import sqlite3
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

LAST_N = 15
SURFACE_WEIGHT = 0.60
CONCEDE_WEIGHT = 0.30


def _brier(pairs):
    return sum((p-y)**2 for p, y in pairs) / len(pairs) if pairs else None


def _negative_binomial_over(line: float, mean: float, size: float) -> float:
    """P(X > line) for NB(mean, size); size→∞ approaches Poisson."""
    cutoff = max(0, int(math.floor(line)))
    if mean <= 0 or size <= 0:
        return 0.0
    success = size/(size+mean)
    probability = success**size
    cdf = probability
    for count in range(cutoff):
        probability *= ((count+size)/(count+1))*(1-success)
        cdf += probability
    return max(0.001, min(0.999, 1-cdf))


def _poisson_over(line: float, mean: float) -> float:
    cutoff = max(0, int(math.floor(line)))
    probability = math.exp(-mean)
    cdf = probability
    for count in range(cutoff):
        probability *= mean/(count+1)
        cdf += probability
    return max(0.001, min(0.999, 1-cdf))


def _rate(rows, ace_key="aces", exposure_key="service_games"):
    numerator = sum(float(row[ace_key]) for row in rows if row[ace_key] is not None)
    denominator = sum(
        float(row[exposure_key]) for row in rows
        if row[ace_key] is not None and row[exposure_key] is not None
    )
    return numerator/denominator if denominator > 0 else None


def _ace_rate_profile(conn, player_id, as_of_date, surface):
    rows = conn.execute(
        """
        SELECT ace_count AS aces,service_games_played AS service_games,surface
        FROM player_match_history h
        WHERE player_id=? AND match_date<? AND ace_count IS NOT NULL
          AND service_games_played>0
          AND (SELECT COUNT(*) FROM player_match_history duplicate
               WHERE duplicate.player_id=h.player_id
                 AND duplicate.opponent_id=h.opponent_id
                 AND duplicate.match_date=h.match_date
                 AND duplicate.ace_count IS NOT NULL)=1
        ORDER BY match_date DESC LIMIT ?
        """,
        (player_id, as_of_date, LAST_N),
    ).fetchall()
    if len(rows) < 5:
        return None
    overall = _rate(rows)
    surface_rows = [
        row for row in rows
        if str(row["surface"] or "").lower() == str(surface or "").lower()
    ]
    surface_rate = _rate(surface_rows) if surface_rows else overall
    return (1-SURFACE_WEIGHT)*overall + SURFACE_WEIGHT*surface_rate


def _conceded_ace_rate(conn, player_id, as_of_date):
    rows = conn.execute(
        """
        SELECT opponent.ace_count AS aces,
               opponent.service_games_played AS service_games
        FROM player_match_history player
        JOIN player_match_history opponent
          ON opponent.source_provider=player.source_provider
         AND opponent.player_id=player.opponent_id
         AND opponent.opponent_id=player.player_id
         AND replace(replace(opponent.provider_match_id,'-winner',''),'-loser','')
             =replace(replace(player.provider_match_id,'-winner',''),'-loser','')
        WHERE player.player_id=? AND player.match_date<?
          AND opponent.ace_count IS NOT NULL
          AND opponent.service_games_played>0
        ORDER BY player.match_date DESC LIMIT ?
        """,
        (player_id, as_of_date, LAST_N),
    ).fetchall()
    return _rate(rows) if rows else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=PROJECT_DIR/"tennis_wc.db")
    parser.add_argument("--split", required=True)
    args = parser.parse_args()

    from tennis_wc.props import ace_model
    from tennis_wc.props.daily import _player_games_distribution

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT p.match_id,p.match_date,p.subject_player_id,p.line,
               p.model_prob_raw,p.market_prob_fair,p.result_status,
               m.player_a_id,m.player_b_id,m.tour,
               COALESCE((SELECT lower(tl.surface) FROM tournament_levels tl
                         WHERE tl.tournament_id=m.tournament_id
                           AND tl.surface IS NOT NULL
                         ORDER BY tl.id DESC LIMIT 1),'unknown') AS surface
        FROM prop_tracker p JOIN matches m ON m.id=p.match_id
        WHERE p.prop_scope='player' AND p.side='over'
          AND p.market_key LIKE '%_aces_%'
          AND p.result_status IN ('WON','LOST')
          AND p.model_prob_raw IS NOT NULL AND p.market_prob_fair IS NOT NULL
        ORDER BY p.match_date,p.id
        """,
    ).fetchall()

    variants = defaultdict(list)
    by_tour = defaultdict(lambda: defaultdict(list))
    missing = 0
    distribution_cache = {}
    training_exposure = []
    holdout_exposure = []
    for row in rows:
        subject = int(row["subject_player_id"])
        opponent = (
            int(row["player_b_id"])
            if subject == int(row["player_a_id"]) else int(row["player_a_id"])
        )
        own_rate = _ace_rate_profile(
            conn, subject, row["match_date"], row["surface"]
        )
        conceded_rate = _conceded_ace_rate(conn, opponent, row["match_date"])
        meta = {
            "player_a_id": row["player_a_id"],
            "player_b_id": row["player_b_id"],
            "match_date": row["match_date"],
            "surface": row["surface"],
        }
        cache_key = (row["match_id"], subject)
        if cache_key not in distribution_cache:
            distribution_cache[cache_key] = _player_games_distribution(
                conn, meta, subject, trials=1500
            )
        distribution = distribution_cache[cache_key]
        if own_rate is None or distribution is None:
            missing += 1
            continue
        rate = own_rate
        if conceded_rate is not None:
            rate = (1-CONCEDE_WEIGHT)*rate + CONCEDE_WEIGHT*conceded_rate
        expected_service_games = sum(
            a+b for a, b in zip(distribution.games_a, distribution.games_b)
        ) / (2.0*distribution.trials)
        mean = rate*expected_service_games
        actual = 1.0 if row["result_status"] == "WON" else 0.0
        exposure_row = (float(row["line"]), mean, actual)
        if str(row["match_date"]) < args.split:
            training_exposure.append(exposure_row)
            continue
        holdout_exposure.append(exposure_row)
        exposure_probability = ace_model.interp_prob_over(
            float(row["line"]), mean,
            ace_model.player_curve_for_surface(row["surface"]),
        )
        probabilities = {
            "stored_raw": float(row["model_prob_raw"]),
            "exposure": exposure_probability,
            "market": float(row["market_prob_fair"]),
        }
        for name, probability in probabilities.items():
            pair = (max(0.001, min(0.999, probability)), actual)
            variants[name].append(pair)
            by_tour[str(row["tour"] or "unknown")][name].append(pair)

    size_grid = (0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0, 50.0, 100.0)
    size_scores = {
        size: _brier([
            (_negative_binomial_over(line, mean, size), actual)
            for line, mean, actual in training_exposure
        ])
        for size in size_grid
    }
    fitted_size = min(size_scores, key=size_scores.get) if training_exposure else None
    if fitted_size is not None:
        variants["exposure_negative_binomial"] = [
            (_negative_binomial_over(line, mean, fitted_size), actual)
            for line, mean, actual in holdout_exposure
        ]
    variants["exposure_poisson"] = [
        (_poisson_over(line, mean), actual)
        for line, mean, actual in holdout_exposure
    ]

    market_brier = _brier(variants["market"])
    payload = {
        "split": args.split,
        "canonical_props": len(rows),
        "scored": len(variants["market"]),
        "missing_exposure": missing,
        "training_props": len(training_exposure),
        "negative_binomial_size": fitted_size,
        "negative_binomial_train_brier": (
            round(size_scores[fitted_size], 6) if fitted_size is not None else None
        ),
        "overall": {
            name: {
                "n": len(pairs),
                "brier": round(_brier(pairs), 6),
                "gain_vs_market": round(market_brier-_brier(pairs), 6),
            }
            for name, pairs in variants.items()
        },
        "by_tour": {
            tour: {
                name: {"n": len(pairs), "brier": round(_brier(pairs), 6)}
                for name, pairs in groups.items()
            }
            for tour, groups in by_tour.items()
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
