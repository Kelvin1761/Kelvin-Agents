#!/usr/bin/env python3
"""One ruler for the match-winner model: us, the market, and simple baselines.

Reports separately where the actual forecast's Elo backbone was recorded and
where it cannot be recovered. An unavailable stored backbone is not proof that
the forecast lacked Elo: older payloads may omit the decomposition.

Baselines, because complexity has to earn its place:
  * market      -- the de-vigged match-winner price
  * elo         -- Elo probability from the as-of ratings alone, no nudges
  * favourite   -- always back the shorter price at its own implied probability
  * coin        -- 0.5 for everything

Usage:
  PYTHONPATH=src .venv/bin/python scripts/measure_match_model.py [--db PATH]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sqlite3
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))


def _brier(pairs) -> float:
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def _log_loss(pairs) -> float:
    total = 0.0
    for p, y in pairs:
        p = min(max(p, 1e-6), 1 - 1e-6)
        total -= y * math.log(p) + (1 - y) * math.log(1 - p)
    return total / len(pairs)


def _auc(pairs) -> float | None:
    positives = sum(y == 1 for _, y in pairs)
    negatives = len(pairs) - positives
    if not positives or not negatives:
        return None
    from itertools import groupby

    wins = negative_seen = 0.0
    for _, group in groupby(sorted(pairs), key=lambda pair: pair[0]):
        outcomes = [y for _, y in group]
        positive_ties = sum(outcomes)
        negative_ties = len(outcomes) - positive_ties
        wins += positive_ties * (negative_seen + 0.5 * negative_ties)
        negative_seen += negative_ties
    return wins / (positives * negatives)


def _recorded_elo_probability(pricing_json: str) -> float | None:
    """Use the actual forecast's backbone, not today's rebuilt Elo history."""
    try:
        model = json.loads(pricing_json)["pricing"]["model"]
        if not any(c.get("active") and c.get("name") in
                   {"surface_elo_edge", "overall_elo_edge"}
                   for c in model.get("components", [])):
            return None
        return 1.0 / (1.0 + math.exp(-float(model["elo_base_logit"])))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def _report(label: str, series: dict) -> dict:
    out = {"label": label, "n": 0, "models": {}}
    for name, pairs in series.items():
        if not pairs:
            continue
        out["n"] = len(pairs)
        out["models"][name] = {
            "brier": round(_brier(pairs), 4),
            "log_loss": round(_log_loss(pairs), 4),
            "auc": round(_auc(pairs), 4) if _auc(pairs) is not None else None,
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=PROJECT_DIR / "tennis_wc.db")
    args = parser.parse_args()

    from tennis_wc.evaluation.match_corpus import earliest_match_odds, prematch_outcomes
    from tennis_wc.modelling import probability_calibration as calib

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = prematch_outcomes(conn)
    opening = earliest_match_odds(conn)

    buckets: dict[str, dict[str, list]] = {
        "recorded Elo present": {k: [] for k in
                        ("model", "model+calibrated", "market", "elo", "favourite", "coin")},
        "recorded Elo unavailable": {k: [] for k in
                       ("model", "model+calibrated", "market", "favourite", "coin")},
    }
    # Walk-forward: refit on everything settled before each date, so a fixture
    # is never calibrated using its own result or any later one.
    calibrations: dict[str, object] = {}

    def calibration_for(match_date: str):
        if match_date not in calibrations:
            calibrations[match_date] = calib.fit_as_of(conn, match_date)
        return calibrations[match_date]

    for row in rows:
        odds = opening.get(row["match_id"])
        if not odds:
            continue
        implied_a, implied_b = 1 / odds["player_a_odds"], 1 / odds["player_b_odds"]
        market = implied_a / (implied_a + implied_b)
        outcome = 1.0 if row["winner_player_id"] == row["player_a_id"] else 0.0
        elo = _recorded_elo_probability(row["pricing_json"])
        has_elo = elo is not None
        key = "recorded Elo present" if has_elo else "recorded Elo unavailable"
        if row["model_p"] is not None:
            buckets[key]["model"].append((float(row["model_p"]), outcome))
            buckets[key]["model+calibrated"].append(
                (calib.apply(float(row["model_p"]), calibration_for(row["match_date"])),
                 outcome)
            )
        buckets[key]["market"].append((market, outcome))
        buckets[key]["favourite"].append((market, outcome))
        buckets[key]["coin"].append((0.5, outcome))
        if has_elo:
            buckets[key]["elo"].append((elo, outcome))

    payload = {
        "fixtures_scored": len(rows),
        "fixtures_with_opening_odds": sum(row["match_id"] in opening for row in rows),
        "corpus_policy": "earliest pre-start forecast; MIN(id) pre-start odds pair; agreed result",
        "note": "Opening market and forecast clocks may differ; this is a probability diagnostic, not executable ROI or promotion evidence.",
        "buckets": [_report(name, series) for name, series in buckets.items()],
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
