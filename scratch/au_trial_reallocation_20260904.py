#!/usr/bin/env python3
"""EXP-20260904-01: give trial_score a share that matches its accuracy.

`trial_score` scores within-race AUC 0.5587 at 98.6% coverage -- better than
`preparation_score` (0.5466) and `jockey_horse_fit_score` (0.5507) -- but it
sits at 5.8256% of `pace_perf`, so one point of it reaches the ability score as
0.0070 against their 0.2524. This tests whether that allocation is wrong.

Only the dimension composition changes, so nothing needs re-scoring: the dump
already carries every leaf, and `map_features_to_matrix_scores` rebuilds the
matrix from them. Offline; the live engine is never written.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))

import au_eval as ev  # noqa: E402
from au_racing_engine import matrix_mapper as mm  # noqa: E402
from au_racing_engine.scoring import compose_matrix_score  # noqa: E402

# Pre-registered, fixed. No ladder search: `au-matrix-weights-tested-dont-change`
# records that edge-walking reads "optimal" when it means "flat".
VARIANTS = {
    "a25": ("pace_perf 內 trial 佔 25%",
            {"pace_perf": (("pace_figure_score", 0.75), ("trial_score", 0.25))}),
    "a50": ("pace_perf 內 trial 佔 50%",
            {"pace_perf": (("pace_figure_score", 0.50), ("trial_score", 0.50))}),
    "b50": ("trial 搬入 preparation，各佔一半",
            {"preparation": (("preparation_score", 0.50), ("trial_score", 0.50)),
             "pace_perf": (("pace_figure_score", 1.0),)}),
}


def scorer_for(formulas):
    original = dict(mm.MATRIX_FORMULAS)
    merged = {**original, **formulas}

    def score(row):
        mm.MATRIX_FORMULAS.clear()
        mm.MATRIX_FORMULAS.update(merged)
        try:
            matrix = mm.map_features_to_matrix_scores(row["features"])
            return (compose_matrix_score(matrix)
                    + float(row["wet"] or 0.0) + float(row.get("proven_class") or 0.0))
        finally:
            mm.MATRIX_FORMULAS.clear()
            mm.MATRIX_FORMULAS.update(original)

    return score


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--variant", required=True, choices=sorted(VARIANTS))
    ap.add_argument("--phase", choices=("dev", "terminal"), default="dev")
    args = ap.parse_args()

    races = json.loads(Path(args.data).read_text(encoding="utf-8"))["races"]
    label, formulas = VARIANTS[args.variant]
    cand = scorer_for(formulas)

    changed = sum(1 for r in races for row in r["rows"]
                  if abs(ev.default_scorer(row) - cand(row)) > 1e-9)
    total = sum(len(r["rows"]) for r in races)
    if not changed:
        print(json.dumps({"variant": args.variant, "verdict": "UNWIRED",
                          "note": "identical to baseline; check the patch"},
                         ensure_ascii=False, indent=2))
        return 1

    dev_idx, term_idx = ev.date_partitions(races)
    dev = [races[i] for i in dev_idx]
    base_dev, cand_dev = ev._counts(dev, ev.default_scorer), ev._counts(dev, cand)
    wanted = ("gold", "good_positional", "pass", "champion", "t3prec")
    missing = [k for k in wanted if k not in base_dev or k not in cand_dev]
    if missing:
        raise SystemExit(f"au_eval does not report: {missing}")
    out = {
        "variant": args.variant, "label": label,
        "races": len(races), "runners": total,
        "runners_changed": changed,
        "runners_changed_pct": round(100.0 * changed / total, 2),
        "dev_races": len(dev_idx), "terminal_races": len(term_idx),
        "dev": {k: {"base": round(base_dev[k], 5), "cand": round(cand_dev[k], 5),
                    "delta_pp": round(cand_dev[k] - base_dev[k], 5)} for k in wanted},
    }
    top4 = sum(1 for r in dev
               if [x["name"] for x in sorted(r["rows"], key=lambda x: -ev.default_scorer(x))][:4]
               != [x["name"] for x in sorted(r["rows"], key=lambda x: -cand(x))][:4])
    out["dev_races_with_top4_change"] = top4
    primary = [out["dev"][k]["delta_pp"] for k in ("gold", "good_positional")]
    out["dev_primary_regression"] = any(d < 0 for d in primary)
    if args.phase == "dev":
        out["decision"] = ("STOP — dev primary regression; terminal stays sealed"
                           if out["dev_primary_regression"]
                           else "PROCEED — eligible for one terminal confirmation")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if out["dev_primary_regression"]:
        out["decision"] = "REFUSED — cannot open terminal after a dev primary regression"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 1
    verdict = ev.compare(races, cand_scorer=cand, label=label)
    out["terminal"] = {"stage4_verdict": verdict.stage4_verdict, "ship": verdict.ship,
                       "why": verdict.reason,
                       "top5_auc_dev": round(verdict.top_dev, 6),
                       "top5_auc_terminal": round(verdict.top_hold, 6),
                       "top5_auc_terminal_ci": [round(x, 6) for x in verdict.top_hold_ci],
                       "counts_delta_pp": {k: round(v, 5)
                                           for k, v in (verdict.counts or {}).items()}}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
