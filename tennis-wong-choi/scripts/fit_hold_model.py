#!/usr/bin/env python3
"""Stage 2's exit test: does the hold model beat a rolling average?

Fits the two adjustment weights on an early window and scores them on a later
one, against the baselines the plan named:

  * rolling      -- the server's own mean hold rate, i.e. weights of zero
  * league       -- one number for everybody
  * combined_hold -- what the shipped games model implies, split evenly

If the fitted model cannot beat `rolling` out of sample, the extra features are
noise and the plan stops at this stage.

Usage:
  PYTHONPATH=src .venv/bin/python scripts/fit_hold_model.py --split 2026-07-01
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import statistics
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))


def _samples(conn, since: str | None, before: str | None, limit: int | None = None):
    """(server profile, returner profile, realised hold rate) per settled match."""
    from tennis_wc.features.serve_return import serve_return_profile

    where = ["h.hold_rate IS NOT NULL", "h.opponent_id IS NOT NULL"]
    params: list = []
    if since:
        where.append("h.match_date >= ?")
        params.append(since)
    if before:
        where.append("h.match_date < ?")
        params.append(before)
    sql = f"""
        SELECT h.player_id, h.opponent_id, h.match_date, h.hold_rate, h.surface
        FROM player_match_history h
        WHERE {" AND ".join(where)}
        ORDER BY h.match_date
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    out = []
    for row in conn.execute(sql, tuple(params)):
        server = serve_return_profile(conn, row["player_id"], row["match_date"],
                                      surface=row["surface"])
        if not server.is_usable:
            continue
        returner = serve_return_profile(conn, row["opponent_id"], row["match_date"],
                                        surface=row["surface"])
        out.append((server, returner, float(row["hold_rate"])))
    return out


def _score(samples, return_weight: float, elo_weight: float) -> float:
    """Mean absolute error of the predicted hold rate."""
    from tennis_wc.props.hold_model import estimate_hold

    if not samples:
        return float("nan")
    return sum(
        abs(estimate_hold(server, returner, return_weight=return_weight,
                          elo_weight=elo_weight).probability - actual)
        for server, returner, actual in samples
    ) / len(samples)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=PROJECT_DIR / "tennis_wc.db")
    parser.add_argument("--split", required=True, help="First date of the test window.")
    parser.add_argument("--train-since", default="2025-01-01")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    from tennis_wc.props.hold_model import LEAGUE_HOLD

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    train = _samples(conn, args.train_since, args.split, args.limit)
    test = _samples(conn, args.split, None, args.limit)

    best = (float("inf"), 0.0, 0.0)
    grid = [round(value / 20, 3) for value in range(0, 21)]     # 0.00 .. 1.00
    for return_weight in grid:
        for elo_weight in (0.0, 0.005, 0.01, 0.02, 0.04):
            error = _score(train, return_weight, elo_weight)
            if error < best[0]:
                best = (error, return_weight, elo_weight)
    _, return_weight, elo_weight = best

    actuals = [actual for _, _, actual in test]
    payload = {
        "train_samples": len(train),
        "test_samples": len(test),
        "fitted_return_weight": return_weight,
        "fitted_elo_weight": elo_weight,
        "test_mean_absolute_error": {
            "fitted_model": round(_score(test, return_weight, elo_weight), 5),
            "rolling_average": round(_score(test, 0.0, 0.0), 5),
            "league_constant": round(
                sum(abs(LEAGUE_HOLD - actual) for actual in actuals) / len(actuals), 5
            ) if actuals else None,
        },
        "test_actual_hold": {
            "mean": round(statistics.mean(actuals), 4) if actuals else None,
            "sd": round(statistics.pstdev(actuals), 4) if actuals else None,
        },
    }
    errors = payload["test_mean_absolute_error"]
    payload["beats_rolling_average"] = (
        errors["fitted_model"] < errors["rolling_average"]
    )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
