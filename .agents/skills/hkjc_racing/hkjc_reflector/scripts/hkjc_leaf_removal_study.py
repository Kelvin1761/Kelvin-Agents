#!/usr/bin/env python3
"""HKJC leaf-removal study on a harness `--dump-matrix` file (EXP-20261019-04).

Each arm sets ONE leaf to neutral 60 for every non-debut runner and re-ranks
offline. The composite moves by Σ_d W_d · share_d · (60 − leaf) over every
dimension that uses the leaf (weight_score sits in both 級數優勢 and 馬匹健康).
Debut runners keep their own formula. Dimension clipping is ignored (dimension
scores sit well inside 0–100).

Arms: current (sanity: reproduces production) and remove_<leaf>.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parents[4]
sys.path.insert(0, str(REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"))
sys.path.insert(0, str(REPO / ".agents/skills/shared_racing"))
sys.path.insert(0, str(SCRIPTS))

from hkjc_weight_study import load, rank_row  # noqa: E402

LEAVES = ("form_score", "consistency_score", "jockey_score", "trainer_score", "class_score",
          "weight_score", "risk_score", "formline_strength_score", "trackwork_trend_score")


def leaf_weights() -> dict[str, float]:
    """Effective outer weight of each leaf = Σ over dimensions of W_d × share."""
    from hkjc_racing_engine import dimensions, scoring

    out: dict[str, float] = {}
    for spec in dimensions.DIMENSIONS:
        weight = scoring.MATRIX_WEIGHTS.get(spec.key)
        if weight is None:
            continue
        for leaf, share in spec.leaves:
            out[leaf] = out.get(leaf, 0.0) + float(weight) * float(share)
    return out


def main(argv=None) -> int:
    from hkjc_racing_engine import scoring

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dump")
    ap.add_argument("--arm", required=True, choices=["current", *[f"remove_{x}" for x in LEAVES]])
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    rows = load(args.dump)
    eff = leaf_weights()
    leaf = None if args.arm == "current" else args.arm[len("remove_"):]
    base = dict(scoring.MATRIX_WEIGHTS)
    centred = dict(scoring.CENTRED_MATRIX_WEIGHTS)
    out = []
    for row in rows:
        shifted = dict(row)
        horses = []
        for h in row["horses"]:
            f = h.get("f") or {}
            raw = h["raw"]
            if leaf and not h["debut"] and leaf in f:
                raw += eff[leaf] * (60.0 - f[leaf])
            horses.append(dict(h, raw=raw))
        shifted["horses"] = horses
        out.append(rank_row(shifted, base, centred, base, args.arm))
    with open(args.out, "w", encoding="utf-8") as handle:
        for r in out:
            handle.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{args.arm}: {len(out)} races (effective weight {eff.get(leaf, 0):.4f}) → {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
