#!/usr/bin/env python3
"""One ruler for the match-winner model: us, the market, and simple baselines.

Reports separately for fixtures where an as-of Elo exists and where it does
not.  A pooled number is meaningless here: the model returns exactly 0.5 when
it has no Elo backbone, which was 24.3% of stored predictions, so a pooled
Brier mixes a real estimate with a coin flip and reads as mediocre skill rather
than as absent coverage.

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
    positives = [p for p, y in pairs if y == 1]
    negatives = [p for p, y in pairs if y == 0]
    if not positives or not negatives:
        return None
    wins = sum(1 for a in positives for b in negatives if a > b)
    ties = sum(1 for a in positives for b in negatives if a == b)
    return (wins + 0.5 * ties) / (len(positives) * len(negatives))


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

    from tennis_wc.features.elo import elo_probability
    from tennis_wc.history import elo_history
    from tennis_wc.modelling import probability_calibration as calib

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT m.id, m.match_date, m.player_a_id, m.player_b_id, r.winner_player_id,
               (SELECT CASE WHEN p.selection_player_id = m.player_a_id
                            THEN p.model_probability ELSE 1.0 - p.model_probability END
                  FROM predictions p WHERE p.match_id = m.id
                 ORDER BY p.id DESC LIMIT 1) AS model_p,
               MIN(CASE WHEN s.selection_side = 'player_a' THEN s.odds END) AS odds_a,
               MIN(CASE WHEN s.selection_side = 'player_b' THEN s.odds END) AS odds_b
        FROM matches m
        JOIN match_results r ON r.match_id = m.id
        JOIN market_odds_snapshots s ON s.match_id = m.id AND s.market_key = 'match_winner'
        WHERE r.winner_player_id IS NOT NULL AND m.player_a_id <> m.player_b_id
        GROUP BY m.id
        """
    ).fetchall()

    buckets: dict[str, dict[str, list]] = {
        "elo present": {k: [] for k in
                        ("model", "model+calibrated", "market", "elo", "favourite", "coin")},
        "elo absent": {k: [] for k in
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
        if not row["odds_a"] or not row["odds_b"]:
            continue
        implied_a, implied_b = 1 / row["odds_a"], 1 / row["odds_b"]
        market = implied_a / (implied_a + implied_b)
        outcome = 1.0 if row["winner_player_id"] == row["player_a_id"] else 0.0
        rating_a = elo_history.rating_as_of(conn, row["player_a_id"], row["match_date"])
        rating_b = elo_history.rating_as_of(conn, row["player_b_id"], row["match_date"])
        has_elo = rating_a is not None and rating_b is not None
        key = "elo present" if has_elo else "elo absent"
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
            buckets[key]["elo"].append((elo_probability(rating_a, rating_b), outcome))

    payload = {
        "fixtures_scored": len(rows),
        "buckets": [_report(name, series) for name, series in buckets.items()],
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
