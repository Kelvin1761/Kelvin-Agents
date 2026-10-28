#!/usr/bin/env python3
"""EXP-20261027-13 — walk-forward magnitude for one overlay (pre-registered).

Input is a `hkjc_eval_harness.py run --dump-matrix` file (overlay weight 0, so
each horse carries `raw` and the overlay value in `o`).  Because an overlay is
added to the final raw score and the harness ranks on raw, `raw + w × o`
reproduces the engine exactly.

For each meeting day d (chronological) the weight is the grid value that
maximised Σ(gold + good_positional) over every earlier day; ties go to the
smaller weight; the first BURN_IN days use 0.  Output rows keep the harness
schema so `hkjc_eval_harness.py compare` can pair them.

    python3 hkjc_overlay_walk_forward.py base.jsonl --overlay top_jockey_today --out cand.jsonl
    python3 hkjc_overlay_walk_forward.py base.jsonl --overlay top_jockey_today --fixed 1.0 --out fixed.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / ".agents/skills/shared_racing"))
from eval_metrics import race_metrics  # noqa: E402

GRID = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0)
BURN_IN = 10
METRIC_KEYS = ("gold", "gold_strict", "good_positional", "champion",
               "top3_capture_at5", "ndcg_at5", "competitive_recall_at5")


def rescore(row: dict, overlay: str, weight: float) -> dict:
    scored = sorted(
        ((-(h["raw"] + weight * float((h.get("o") or {}).get(overlay, 0.0))), h["n"]) for h in row["horses"]),
    )
    picks = [n for _s, n in scored]
    positions = {h["n"]: h["pos"] for h in row["horses"] if h.get("pos")}
    metrics = race_metrics(picks, [n for n, p in positions.items() if p <= 3], actual_pos=positions)
    metrics["mean_top3_model_rank"] = metrics.get("top3_mean_model_rank")
    return dict(row, picks=picks, **{k: metrics.get(k) for k in (*METRIC_KEYS, "mean_top3_model_rank")})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dump")
    parser.add_argument("--overlay", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--fixed", type=float, help="apply one weight to every day (fidelity check)")
    args = parser.parse_args()
    rows = [json.loads(line) for line in Path(args.dump).read_text(encoding="utf-8").splitlines()]
    by_day = defaultdict(list)
    for row in rows:
        by_day[row.get("date") or row["meeting"][:10]].append(row)
    days = sorted(by_day)
    # objective[w] accumulates Σ(gold + good_positional) over finished days
    objective = {w: 0.0 for w in GRID}
    chosen, out = [], []
    for index, day in enumerate(days):
        if args.fixed is not None:
            weight = args.fixed
        elif index < BURN_IN:
            weight = 0.0
        else:
            best = max(objective.values())
            weight = min(w for w in GRID if objective[w] == best)
        chosen.append((day, weight))
        for row in by_day[day]:
            if "error" in row or not row.get("horses"):
                out.append(row)
                continue
            out.append(rescore(row, args.overlay, weight))
            for w in GRID:
                scored = rescore(row, args.overlay, w)
                objective[w] += float(scored["gold"] or 0) + float(scored["good_positional"] or 0)
    Path(args.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
    print(json.dumps({"overlay": args.overlay, "chosen": chosen,
                      "final_objective": objective}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
