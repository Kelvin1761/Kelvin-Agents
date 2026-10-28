"""Reproduce the frozen-shadow sensitivity diagnostic; never modify the DB.

Run from any checkout with the accompanying audit fixes:
  PYTHONDONTWRITEBYTECODE=1 python docs/audits/tennis-model-review-20261026-shadow.py --db PATH
No fitting or parameter selection occurs here. The date/version and bootstrap
are those of the existing shadow protocol; this is not a promotion gate.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import importlib.util
import json
import math
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tennis-wong-choi/src"))


def main() -> None:
    from tennis_wc.evaluation.match_corpus import earliest_match_odds, prematch_outcomes

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location(
        "frozen_backbone_audit", ROOT / "tennis-wong-choi/scripts/tune_elo_backbone.py"
    )
    harness = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = harness
    spec.loader.exec_module(harness)
    harness.HOLDOUT_START = "2026-10-10"
    version = "elo-v2-start-of-day.surface-0.35"
    with sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        valid = {row["match_id"] for row in prematch_outcomes(conn, since=harness.HOLDOUT_START)}
        opening = earliest_match_odds(conn)
    groups = defaultdict(list)
    excluded = []
    for row in harness.load_holdout(str(args.db)):
        model = json.loads(row["pricing_json"])["pricing"]["model"]
        shadow = model.get("shadow")
        if not shadow:
            continue
        if shadow.get("version") != version:
            raise ValueError("unexpected shadow version; do not pool fitted variants")
        if row["match_id"] not in valid or row["match_id"] not in opening:
            excluded.append(row["match_id"])
            continue
        y = row["y"]
        probabilities = (float(model["player_a_probability"]),
                         float(shadow["player_a_probability"]), row["market_pa"])
        ll = tuple(-(y*math.log(p)+(1-y)*math.log(1-p)) for p in probabilities)
        brier = tuple((p-y)**2 for p in probabilities)
        entry = ll + brier
        level = str(row["level"] or "").upper()
        tier = ("itf_utr" if "ITF" in level or "UTR" in level else
                "challenger" if "CHALL" in level else
                "unknown" if not level or level == "UNKNOWN" else "tour")
        groups["all"].append(entry)
        groups[tier].append(entry)
        if tier in {"tour", "challenger"}:
            groups["bettable"].append(entry)
    output = {}
    for name, rows in groups.items():
        output[name] = {"n": len(rows)}
        for metric, offset in (("log_loss", 0), ("brier", 3)):
            output[name][metric] = {
                **{label: sum(row[offset+i] for row in rows)/len(rows)
                   for i, label in enumerate(("production", "shadow", "market"))},
                "paired": harness.paired_delta(
                    [row[offset] for row in rows], [row[offset+1] for row in rows]
                ),
            }
    print(json.dumps({"since": harness.HOLDOUT_START, "version": version,
                      "excluded_invalid_result_match_ids": excluded,
                      "bootstrap": {"resamples": 4000, "seed": 20260826, "unit": "match"},
                      "groups": output}, indent=2))


if __name__ == "__main__":
    main()
