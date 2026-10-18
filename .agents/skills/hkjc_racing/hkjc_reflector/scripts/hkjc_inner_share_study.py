#!/usr/bin/env python3
"""HKJC inner-share study on a harness `--dump-matrix` file (EXP-20261019-03).

For a two-leaf dimension d = s·a + (1−s)·b (registry shares in `dimensions.py`),
re-rank offline with a different share. Everything else in the composite is
carried as the residual, so `--share current` reproduces production exactly:

    composite' = raw + W_d · ((s'·a + (1−s')·b) − (s·a + (1−s)·b))

Debut runners keep their own formula (untouched).

Arms:
  current          registry shares (sanity: must reproduce production picks)
  wf_<dimension>   walk-forward: for meeting t, fit s' on meetings < t only (first
                   10 meetings use the registry share). Within-race softmax on the
                   composite / τ, s' = sigmoid(θ) in (0, 1), τ fitted jointly
                   (log τ, start 6, bounds 0.5–30; EXP-20261019-02 found τ≈5–6),
                   L2 λ = 2.0 on (s' − s). Nothing tuned.
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
sys.path.insert(0, str(SCRIPTS))

from hkjc_weight_study import load, rank_row  # noqa: E402  (same row format / metrics)

L2 = 2.0
WARMUP_MEETINGS = 10
TAU_START = 6.0


def two_leaf_dimensions() -> dict[str, tuple[str, str, float, float]]:
    from hkjc_racing_engine import dimensions, scoring

    out = {}
    for spec in dimensions.DIMENSIONS:
        if len(spec.leaves) == 2 and spec.key in scoring.MATRIX_WEIGHTS:
            (a, s), (b, _s2) = spec.leaves
            out[spec.key] = (a, b, float(s), float(scoring.MATRIX_WEIGHTS[spec.key]))
    return out


def shifted_raw(horse: dict, dim: tuple[str, str, float, float], share: float) -> float:
    a, b, s0, weight = dim
    f = horse.get("f") or {}
    if horse["debut"] or a not in f or b not in f:
        return horse["raw"]
    return horse["raw"] + weight * ((share - s0) * (f[a] - f[b]))


def rank_with(row: dict, dim, share: float, arm: str) -> dict:
    shifted = dict(row)
    shifted["horses"] = [dict(h, raw=shifted_raw(h, dim, share)) for h in row["horses"]]
    # rank_row re-ranks on composite(); with identical weights it returns `raw`
    from hkjc_racing_engine import scoring

    base = dict(scoring.MATRIX_WEIGHTS)
    centred = dict(scoring.CENTRED_MATRIX_WEIGHTS)
    return rank_row(shifted, base, centred, base, arm)


def fit(rows: list[dict], dim) -> tuple[float, float]:
    import numpy as np
    from scipy.optimize import minimize

    a, b, s0, weight = dim
    races = []
    for row in rows:
        horses = [h for h in row["horses"] if h.get("pos") and not h["debut"] and a in (h.get("f") or {})
                  and b in (h.get("f") or {})]
        if len(horses) < 4 or not any(h["pos"] <= 3 for h in horses):
            continue
        raw = np.array([h["raw"] for h in horses])
        diff = np.array([weight * (h["f"][a] - h["f"][b]) for h in horses])
        y = np.array([1.0 if h["pos"] <= 3 else 0.0 for h in horses])
        races.append((raw, diff, y / y.sum()))

    def loss(params):
        share = 1.0 / (1.0 + math.exp(-params[0]))
        tau = math.exp(params[1])
        total = 0.0
        for raw, diff, y in races:
            s = (raw + (share - s0) * diff) / tau
            s = s - s.max()
            total -= float(y @ (s - np.log(np.exp(s).sum())))
        return total / len(races) + L2 * (share - s0) ** 2

    start = np.array([math.log(s0 / (1 - s0)), math.log(TAU_START)])
    res = minimize(loss, start, method="L-BFGS-B",
                   bounds=[(None, None), (math.log(0.5), math.log(30.0))], options={"maxiter": 300})
    return 1.0 / (1.0 + math.exp(-res.x[0])), math.exp(res.x[1])


def main(argv=None) -> int:
    dims = two_leaf_dimensions()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dump")
    ap.add_argument("--arm", required=True, choices=["current", *[f"wf_{k}" for k in dims]])
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    rows = load(args.dump)
    out = []
    if args.arm == "current":
        key = next(iter(dims))
        out = [rank_with(r, dims[key], dims[key][2], "current") for r in rows]
    else:
        key = args.arm[3:]
        dim = dims[key]
        by_meeting = defaultdict(list)
        for r in rows:
            by_meeting[r["meeting"]].append(r)
        meetings = sorted(by_meeting, key=lambda m: m[:10])
        trail = []
        for index, meeting in enumerate(meetings):
            history = [r for m in meetings[:index] for r in by_meeting[m]]
            share, tau = (dim[2], None) if index < WARMUP_MEETINGS else fit(history, dim)
            trail.append({"meeting": meeting, "share": round(share, 4), "tau": tau and round(tau, 3)})
            out.extend(rank_with(r, dim, share, args.arm) for r in by_meeting[meeting])
        Path(args.out + ".shares.json").write_text(json.dumps(trail, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(args.out, "w", encoding="utf-8") as handle:
        for row in out:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{args.arm}: {len(out)} races → {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
