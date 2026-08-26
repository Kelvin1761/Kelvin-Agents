#!/usr/bin/env python3
"""Stage 4: price player_total_games from serve, and score it honestly.

The prediction uses no odds at all -- two hold rates from the walk-forward
serve profiles, a simulated match, and the probability read off the resulting
distribution. The market appears only as something to be scored against
afterwards.

Stage 2's exit test compared predicted to realised per-match hold rate, which
is dominated by binomial noise: ten-odd service games per match puts a large
floor under any model's error there. This scores the quantity that actually
matters instead -- the probability of the prop outcome.

Usage:
  PYTHONPATH=src .venv/bin/python scripts/evaluate_serve_pricing.py --split 2026-07-15
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

TRIALS = 1500


def _brier(pairs):
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs) if pairs else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=PROJECT_DIR / "tennis_wc.db")
    parser.add_argument("--split", help="Score only props on or after this date.")
    args = parser.parse_args()

    from tennis_wc.features.serve_return import serve_return_profile
    from tennis_wc.props.hold_model import estimate_hold, estimate_hold_fitted
    from tennis_wc.props.match_simulator import (
        FITTED_HOLD_GAP_DISPERSION,
        simulate_match,
    )

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    # Provably pre-match rows only -- see evaluation/corpus.py. 70% of this
    # table was written after the results were known.
    where = ["p.prop_scope = 'player_games'", "p.result_status IN ('WON','LOST')",
             "p.is_point_in_time = 1",
             "p.subject_player_id IS NOT NULL", "p.model_prob_raw IS NOT NULL"]
    params: list = []
    if args.split:
        where.append("p.match_date >= ?")
        params.append(args.split)
    rows = conn.execute(
        f"""
        SELECT p.match_id, p.match_date, p.subject_player_id, p.line, p.side,
               p.result_status, p.model_prob_raw, p.decimal_odds,
               p.market_prob_fair,
               m.player_a_id, m.player_b_id,
               (SELECT tl.surface FROM tournament_levels tl
                 WHERE tl.tournament_id = m.tournament_id AND tl.surface IS NOT NULL
                 ORDER BY tl.id DESC LIMIT 1) AS surface
        FROM prop_tracker p JOIN matches m ON m.id = p.match_id
        WHERE {" AND ".join(where)}
        """,
        tuple(params),
    ).fetchall()

    cache: dict = {}
    variants: dict[str, list] = {
        "hand_sigma_0": [],
        "hand_sigma_006": [],
        "fitted_sigma_0": [],
        "fitted_sigma_006": [],
        "stored_raw": [],
        "market": [],
    }
    skipped = 0
    for row in rows:
        subject = row["subject_player_id"]
        opponent = (row["player_b_id"] if subject == row["player_a_id"]
                    else row["player_a_id"])
        server = serve_return_profile(conn, subject, row["match_date"],
                                      surface=row["surface"])
        returner = serve_return_profile(conn, opponent, row["match_date"],
                                        surface=row["surface"])
        hold_subject = estimate_hold(server, returner, return_weight=0.35, elo_weight=0.04)
        hold_opponent = estimate_hold(returner, server, return_weight=0.35, elo_weight=0.04)
        fitted_subject = estimate_hold_fitted(server, returner)
        fitted_opponent = estimate_hold_fitted(returner, server)
        if not all(x.is_usable for x in (
            hold_subject, hold_opponent, fitted_subject, fitted_opponent
        )):
            skipped += 1
            continue
        side = row["side"] or "over"
        won = 1.0 if row["result_status"] == "WON" else 0.0
        estimates = {
            "hand_sigma_0": (
                hold_subject.probability, hold_opponent.probability, 0.0,
            ),
            "hand_sigma_006": (
                hold_subject.probability, hold_opponent.probability,
                FITTED_HOLD_GAP_DISPERSION,
            ),
            "fitted_sigma_0": (
                fitted_subject.probability, fitted_opponent.probability, 0.0,
            ),
            "fitted_sigma_006": (
                fitted_subject.probability, fitted_opponent.probability,
                FITTED_HOLD_GAP_DISPERSION,
            ),
        }
        for name, (subject_hold, opponent_hold, dispersion) in estimates.items():
            key = (
                round(subject_hold, 3), round(opponent_hold, 3), dispersion,
            )
            if key not in cache:
                cache[key] = simulate_match(
                    key[0], key[1], trials=TRIALS, dispersion=dispersion
                )
            over = cache[key].player_games_over(float(row["line"]), player="a")
            predicted = over if side == "over" else 1-over
            variants[name].append((max(0.01, min(0.99, predicted)), won))
        stored = float(row["model_prob_raw"])
        variants["stored_raw"].append(
            (stored if side == "over" else 1-stored, won)
        )
        if row["market_prob_fair"] is not None:
            market = float(row["market_prob_fair"])
            variants["market"].append(
                (market if side == "over" else 1-market, won)
            )

    payload = {
        "props_scored": len(variants["hand_sigma_0"]),
        "skipped_no_serve_history": skipped,
        "brier": {
            name: round(_brier(pairs), 6) if pairs else None
            for name, pairs in variants.items()
        },
        "note": "market is the de-vigged stored probability",
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
