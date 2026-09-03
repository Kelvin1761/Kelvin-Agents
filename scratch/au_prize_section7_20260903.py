#!/usr/bin/env python3
"""Contract §7 acceptance measurement for the prize-column backfill.

§7 does not ask whether the primary KPIs improved; it asks whether any of them
got *significantly* worse, and whether any pre-declared cohort has a paired CI
that is entirely negative. Both are measured here by resampling whole races, so
runners inside one race stay together.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
sys.path.insert(0, str(ROOT / "scratch"))

import au_eval as ev  # noqa: E402
from au_class_eval_20260903 import cand_scorer, merge  # noqa: E402

PRIMARY = ("gold", "good_positional")
FAV_SP_BUCKETS = ((0, 3, "SP≤3"), (3, 5, "SP 3-5"), (5, 10, "SP 5-10"),
                  (10, 20, "SP 10-20"), (20, 10**9, "SP>20"))


def _fav_sp(race):
    """Baseline top pick's starting price -- a cohort key, never a model input."""
    ranked = sorted(race["rows"], key=lambda r: -ev.default_scorer(r))
    try:
        return float(str(ranked[0].get("sp") or "").replace("$", ""))
    except (TypeError, ValueError):
        return None


def race_outcomes(races, scorer):
    """Per-race metric rows, computed once. Bootstrapping resamples these.

    Recomputing `_counts` inside every bootstrap iteration re-scored the whole
    corpus thousands of times; the rates are race-level means, so resampling
    precomputed rows gives the same interval for a fraction of the work.
    """
    out = []
    for race in races:
        ranked = sorted(((scorer(row), index, row["pos"])
                         for index, row in enumerate(race["rows"])), key=lambda t: -t[0])
        pos = {t[1]: t[2] for t in ranked}
        top3 = {h for h, p in pos.items() if p <= 3}
        winner = next((h for h, p in pos.items() if p == 1), None)
        if len(top3) < 3 or winner is None:
            out.append(None)  # excluded by the live rule; keep the slot aligned
            continue
        metadata = race.get("metadata") or {}
        field_size = int(race.get("field") or metadata.get("field_size") or len(pos))
        out.append(ev.race_metrics([t[1] for t in ranked], top3, winner=winner,
                                   actual_pos=pos, field_size=field_size))
    return out


def _rate(rows, indices, key):
    kept = [rows[i] for i in indices if rows[i] is not None]
    if not kept:
        return None
    return 100.0 * ev.summarize_races(kept)["counts"][key] / len(kept)


def paired_ci(races, key, iterations=2000, seed=20260903, precomputed=None):
    n = len(races)
    if n < 20:
        return None
    base_rows, cand_rows = precomputed if precomputed else (
        race_outcomes(races, ev.default_scorer), race_outcomes(races, cand_scorer))
    everything = list(range(n))
    base = _rate(base_rows, everything, key)
    cand = _rate(cand_rows, everything, key)
    if base is None or cand is None:
        return None
    rng = random.Random(seed)
    deltas = []
    for _ in range(iterations):
        sample = [rng.randrange(n) for _ in range(n)]
        b = _rate(base_rows, sample, key)
        c = _rate(cand_rows, sample, key)
        if b is not None and c is not None:
            deltas.append(c - b)
    deltas.sort()
    lo = deltas[int(0.025 * len(deltas))]
    hi = deltas[min(len(deltas) - 1, int(0.975 * len(deltas)))]
    return {"races": n, "base": round(base, 4), "cand": round(cand, 4),
            "delta_pp": round(cand - base, 4), "ci95": [round(lo, 4), round(hi, 4)],
            "entirely_negative": hi < 0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--iterations", type=int, default=2000)
    args = ap.parse_args()

    races = merge(Path(args.baseline), Path(args.candidate))
    dev_idx, term_idx = ev.date_partitions(races)
    out = {"races": len(races), "dev": len(dev_idx), "terminal": len(term_idx),
           "iterations": args.iterations, "primary": {}, "cohorts": {}}

    all_base = race_outcomes(races, ev.default_scorer)
    all_cand = race_outcomes(races, cand_scorer)

    def subset_pre(indices):
        return ([all_base[i] for i in indices], [all_cand[i] for i in indices])

    windows = {"all": list(range(len(races))), "dev": dev_idx, "terminal": term_idx}
    for key in PRIMARY:
        out["primary"][key] = {
            w: paired_ci([races[i] for i in idx], key, args.iterations,
                         precomputed=subset_pre(idx))
            for w, idx in windows.items()}

    cohort_idx = {}
    for lo, hi, label in ev.FIELD_BUCKETS:
        cohort_idx[label] = [i for i, r in enumerate(races)
                             if lo <= ev._field_size(r) <= hi]
    fav = {i: _fav_sp(r) for i, r in enumerate(races)}
    for lo, hi, label in FAV_SP_BUCKETS:
        cohort_idx[label] = [i for i, r in enumerate(races)
                             if fav[i] is not None and lo < fav[i] <= hi]
    for key in PRIMARY:
        out["cohorts"][key] = {
            label: paired_ci([races[i] for i in idx], key, args.iterations,
                             precomputed=subset_pre(idx))
            for label, idx in cohort_idx.items()}

    negatives = [f"{k}:{c}" for k, cells in out["cohorts"].items()
                 for c, v in cells.items() if v and v["entirely_negative"]]
    primary_neg = [f"{k}:{w}" for k, ws in out["primary"].items()
                   for w, v in ws.items() if v and v["entirely_negative"]]
    out["section7"] = {
        "primary_significantly_negative": primary_neg,
        "cohorts_entirely_negative": negatives,
        "passes_zero_significant_regression": not primary_neg and not negatives,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
