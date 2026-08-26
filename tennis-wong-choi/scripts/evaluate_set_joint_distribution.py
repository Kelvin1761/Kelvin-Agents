#!/usr/bin/env python3
"""Score one empirical BO3 joint distribution across every set prop family.

This is a read-only frozen-holdout experiment.  It asks whether the calibrated
four-outcome table already in ``set_distribution`` is a better common source
than the mixed simulator/closed-form paths stored on the card.
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


def _brier(rows):
    return sum((p - y) ** 2 for p, y in rows) / len(rows) if rows else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=PROJECT_DIR / "tennis_wc.db")
    parser.add_argument("--split", required=True)
    args = parser.parse_args()

    from tennis_wc.modelling import set_distribution
    from tennis_wc.props.player_model import set_handicap_cover_probability

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        WITH latest_prediction AS (
            SELECT prediction.* FROM predictions prediction
            WHERE prediction.id IN (SELECT MAX(id) FROM predictions GROUP BY match_id)
        )
        SELECT p.*,m.player_a_id,m.player_b_id,
               CASE WHEN prediction.selection_player_id=m.player_a_id
                    THEN prediction.model_probability
                    ELSE 1.0-prediction.model_probability END AS p_a
        FROM prop_tracker p
        JOIN matches m ON m.id=p.match_id
        JOIN latest_prediction prediction ON prediction.match_id=p.match_id
        WHERE p.match_date >= ?
          AND p.result_status IN ('WON','LOST')
          AND p.is_point_in_time = 1
          AND p.model_prob_raw IS NOT NULL
          AND p.market_prob_fair IS NOT NULL
          AND p.prop_scope IN ('player_win_set','player_first_set',
                               'player_set_margin','player_exact_set_score')
          AND (p.prop_scope NOT IN ('player_first_set','player_set_margin')
               OR (p.side='over' AND p.subject_player_id=m.player_a_id))
        ORDER BY p.match_date,p.match_id,p.id
        """,
        (args.split,),
    ).fetchall()

    scored = defaultdict(lambda: defaultdict(list))
    skipped = defaultdict(int)
    for row in rows:
        p_a = float(row["p_a"])
        if abs(p_a - 0.5) <= 1e-12:
            skipped[row["prop_scope"]] += 1
            continue
        scope = str(row["prop_scope"])
        actual = 1.0 if row["result_status"] == "WON" else 0.0
        if scope == "player_win_set":
            p_side = p_a if row["subject_player_id"] == row["player_a_id"] else 1-p_a
            common = set_distribution.win_at_least_one_set_probability(p_side)
            family = "player_win_a_set"
        elif scope == "player_first_set":
            common = set_distribution.first_set_win_probability(p_a)
            family = "first_set_winner"
        elif scope == "player_set_margin":
            common, _margin = set_handicap_cover_probability(-float(row["line"]), p_a)
            family = "player_set_handicap"
        else:
            try:
                sets_lost = int(str(row["market_key"]).rsplit("_", 1)[-1])
            except ValueError:
                skipped[scope] += 1
                continue
            p_side = p_a if row["subject_player_id"] == row["player_a_id"] else 1-p_a
            common = set_distribution.set_score_probability(p_side, sets_lost)
            if common is None:
                skipped[scope] += 1
                continue
            family = "player_exact_set_score"

        scored[family]["stored_raw"].append((float(row["model_prob_raw"]), actual))
        scored[family]["common_joint"].append((float(common), actual))
        scored[family]["market"].append((float(row["market_prob_fair"]), actual))

    payload = {"split": args.split, "families": {}, "skipped": dict(skipped)}
    for family, variants in sorted(scored.items()):
        market_brier = _brier(variants["market"])
        payload["families"][family] = {
            name: {
                "n": len(pairs),
                "brier": round(_brier(pairs), 6),
                "gain_vs_market": round(market_brier - _brier(pairs), 6),
                "gain_vs_stored": round(
                    _brier(variants["stored_raw"]) - _brier(pairs), 6
                ),
            }
            for name, pairs in variants.items()
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
