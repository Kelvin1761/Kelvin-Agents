#!/usr/bin/env python3
"""HKJC outer-weight study on a harness `--dump-matrix` file (Phase 3, 2026-10-10).

Answers Kelvin's first question — "put everything to neutral and see if the
current weighting is the best" — without re-running the engine: every horse's
final raw matrix scores are in the dump, so any weight set can be re-ranked
offline. Non-matrix adjustments (SIP, whole-field cap) are carried over as the
residual `raw − Σ w·m`; debut runners keep their own weight set untouched.

Pre-registered arms (EXP-20261010-06):
  current       production weights (sanity: must reproduce production picks)
  neutral       every sum-to-1 dimension 1/k; centred dimensions unchanged
  wf_refit      walk-forward: for meeting t, fit on meetings < t only (first 10
                meetings use production weights). Within-race softmax on the
                composite / τ (τ = 3), weights = softmax(θ) so they stay ≥ 0 and
                sum to 1, L2 shrink λ = 2.0 towards production. Nothing tuned.

Output: per-race rows in the harness format, ready for
`hkjc_eval_harness.py compare --stage4 fixed_rule|walk_forward_oos`.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parents[4]
sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"))
sys.path.insert(0, str(REPO / ".agents/skills/shared_racing"))

TAU = 3.0
L2 = 2.0
WARMUP_MEETINGS = 10
RANKING = ("top3_capture_at5", "ndcg_at5", "competitive_recall_at5", "mean_top3_model_rank")


def load(path: str) -> list[dict]:
    rows = [json.loads(line) for line in open(path, encoding="utf-8")]
    return [r for r in rows if "error" not in r and r.get("horses")]


def composite(horse: dict, weights: dict, centred: dict, base_weights: dict) -> float:
    if horse["debut"]:
        return horse["raw"]
    m = horse["m"]
    base = sum(m.get(k, 60.0) * w for k, w in base_weights.items()) + sum(
        c * (m.get(k, 60.0) - 60.0) for k, c in centred.items())
    residual = horse["raw"] - base
    new = sum(m.get(k, 60.0) * w for k, w in weights.items()) + sum(
        c * (m.get(k, 60.0) - 60.0) for k, c in centred.items())
    return new + residual


def rank_row(row: dict, weights: dict, centred: dict, base_weights: dict, arm: str) -> dict:
    from eval_metrics import race_metrics

    scored = sorted(((-composite(h, weights, centred, base_weights), h["n"]) for h in row["horses"]))
    picks = [n for _s, n in scored]
    positions = {h["n"]: h["pos"] for h in row["horses"] if h.get("pos")}
    metrics = race_metrics(picks, [n for n, p in positions.items() if p <= 3], actual_pos=positions)
    metrics["mean_top3_model_rank"] = metrics.get("top3_mean_model_rank")
    out = {k: row[k] for k in ("date", "meeting", "race", "venue", "awt", "distance", "field")}
    out.update({"arm": arm, "picks": picks, "meeting_dead_fields": row.get("meeting_dead_fields", [])})
    out.update({k: metrics.get(k) for k in ("gold", "gold_strict", "good_positional", "champion", *RANKING)})
    return out


def fit(rows: list[dict], keys: list[str], prior: dict, centred: dict, base_weights: dict) -> dict:
    import numpy as np

    races = []
    for row in rows:
        horses = [h for h in row["horses"] if not h["debut"] and h.get("pos")]
        if len(horses) < 4 or not any(h["pos"] <= 3 for h in horses):
            continue
        x = np.array([[h["m"].get(k, 60.0) for k in keys] for h in horses])
        offset = np.array([composite(h, {k: 0.0 for k in keys}, centred, base_weights) for h in horses])
        y = np.array([1.0 if h["pos"] <= 3 else 0.0 for h in horses])
        races.append((x, offset, y / y.sum()))
    from scipy.optimize import minimize

    w0 = np.array([prior[k] for k in keys])

    def weights_of(theta):
        e = np.exp(theta - theta.max())
        return e / e.sum()

    def loss(theta):
        w = weights_of(theta)
        total = 0.0
        for x, offset, y in races:
            s = (x @ w + offset) / TAU
            s = s - s.max()
            total -= float(y @ (s - np.log(np.exp(s).sum())))
        return total / len(races) + L2 * float(((w - w0) ** 2).sum())

    # Exact optimisation (L-BFGS on θ, numerical gradient). The first version used
    # a hand-rolled gradient step 25× too large and collapsed every fit into one
    # corner — an optimiser bug, not evidence (EXP-20261010-06).
    result = minimize(loss, np.log(w0), method="L-BFGS-B", options={"maxiter": 200})
    w = weights_of(result.x)
    return {k: float(v) for k, v in zip(keys, w)}


def _shape_scaled(row: dict, k: float, base: dict) -> dict:
    """Copy of a race with race_shape deviations from the race median scaled by k."""
    shapes = sorted(h["m"]["race_shape"] for h in row["horses"] if "race_shape" in h["m"])
    if not shapes:
        return row
    mid = len(shapes) // 2
    median = shapes[mid] if len(shapes) % 2 else (shapes[mid - 1] + shapes[mid]) / 2
    horses = []
    for h in row["horses"]:
        h2 = dict(h)
        if not h["debut"] and "race_shape" in h["m"]:
            old = h["m"]["race_shape"]
            new = median + k * (old - median)
            h2["m"] = {**h["m"], "race_shape": new}
            h2["raw"] = h["raw"] + base["race_shape"] * (new - old)
        horses.append(h2)
    return {**row, "horses": horses}


def shape_amplitude(rows: list[dict], base: dict, centred: dict) -> list[dict]:
    """EXP-20261010-09: walk-forward fit of one race_shape amplitude k ∈ [0, 1.5]."""
    import numpy as np
    from scipy.optimize import minimize_scalar

    by_meeting = defaultdict(list)
    for r in rows:
        by_meeting[r["meeting"]].append(r)
    meetings = sorted(by_meeting, key=lambda m: m[:10])

    def loss(k, history):
        total, n = 0.0, 0
        for row in history:
            scaled = _shape_scaled(row, k, base)
            horses = [h for h in scaled["horses"] if h.get("pos")]
            if len(horses) < 4 or not any(h["pos"] <= 3 for h in horses):
                continue
            s = np.array([h["raw"] for h in horses]) / TAU
            y = np.array([1.0 if h["pos"] <= 3 else 0.0 for h in horses])
            s = s - s.max()
            total -= float((y / y.sum()) @ (s - np.log(np.exp(s).sum())))
            n += 1
        return total / max(n, 1)

    out, trail = [], []
    for index, meeting in enumerate(meetings):
        history = [r for m in meetings[:index] for r in by_meeting[m]]
        k = 1.0 if index < WARMUP_MEETINGS else float(
            minimize_scalar(lambda v: loss(v, history), bounds=(0.0, 1.5), method="bounded").x)
        trail.append({"meeting": meeting, "k": round(k, 3)})
        for row in by_meeting[meeting]:
            out.append(rank_row(_shape_scaled(row, k, base), base, centred, base, "wf_shape_k"))
    Path("shape_k_trail.json").write_text(json.dumps(trail, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main(argv=None) -> int:
    from hkjc_racing_engine import scoring

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dump")
    ap.add_argument("--arm", choices=("current", "neutral", "wf_refit", "wf_shape_k"), required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    rows = load(args.dump)
    base = dict(scoring.MATRIX_WEIGHTS)
    centred = dict(scoring.CENTRED_MATRIX_WEIGHTS)
    keys = list(base)
    out = []
    if args.arm == "current":
        out = [rank_row(r, base, centred, base, "current") for r in rows]
    elif args.arm == "neutral":
        neutral = {k: 1.0 / len(keys) for k in keys}
        out = [rank_row(r, neutral, centred, base, "neutral") for r in rows]
    elif args.arm == "wf_shape_k":
        out = shape_amplitude(rows, base, centred)
    else:
        by_meeting = defaultdict(list)
        for r in rows:
            by_meeting[r["meeting"]].append(r)
        meetings = sorted(by_meeting, key=lambda m: m[:10])
        trail = []
        for index, meeting in enumerate(meetings):
            history = [r for m in meetings[:index] for r in by_meeting[m]]
            weights = base if index < WARMUP_MEETINGS else fit(history, keys, base, centred, base)
            trail.append({"meeting": meeting, "weights": {k: round(v, 4) for k, v in weights.items()}})
            out.extend(rank_row(r, weights, centred, base, "wf_refit") for r in by_meeting[meeting])
        Path(args.out + ".weights.json").write_text(json.dumps(trail, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(args.out, "w", encoding="utf-8") as handle:
        for row in out:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{args.arm}: {len(out)} races → {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
