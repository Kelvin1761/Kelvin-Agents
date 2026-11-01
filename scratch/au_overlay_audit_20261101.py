#!/usr/bin/env python3
"""EXP-20261101-38 overlay 消融 arm 產生器 + 安全欄（X5）評估。規格見 protocol —— 唔准喺度改。

    python3 au_overlay_audit_20261101.py --dump dump_shipped.json --outdir ARMS
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))
import au_fq_weight_class_eval_20261028 as fe  # noqa: E402
from au_racing_engine import engine_core as ec  # noqa: E402
from au_racing_engine.renderer import _default_leaf_count, THIN_EVIDENCE_MIN_DEFAULTS  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402
from au_walkforward_refit import exact_score  # noqa: E402

KEEP = ("n", "name", "pos", "sp", "wet", "proven_class", "full_time")


def tags(race):
    d = race["rows"][0].get("distance")
    try:
        d = float(str(d).rstrip("m"))
    except (TypeError, ValueError):
        d = None
    top = min(range(len(race["rows"])), key=lambda i: (-race["rows"][i]["ability"], race["rows"][i]["n"]))
    runs = len(race["pf_field"].get(str(race["rows"][top]["n"])) or [])
    return {"distance": None if not d else "<=1200" if d <= 1200 else "1201-1600" if d <= 1600 else ">1600",
            "top_pf_runs": "0" if runs == 0 else "1-2" if runs <= 2 else "3-5" if runs <= 5 else "6+"}


def arm(race, fn):
    rows = []
    for x in race["rows"]:
        r = {k: x[k] for k in KEEP}
        r["features"] = dict(x["features"])
        rows.append(fn(r, x))
    for r in rows:
        r["ability"] = exact_score(r, MATRIX_WEIGHTS)
    return {**{k: v for k, v in race.items() if k not in ("rows", "pf_field", "fq_field")}, "tags": tags(race), "rows": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    races = json.loads(Path(args.dump).read_text())["races"]

    base = [arm(r, lambda a, x: a) for r in races]
    gap = max(abs(b["ability"] - x["ability"]) for r, rb in zip(races, base) for x, b in zip(r["rows"], rb["rows"]))
    print("ability replica max gap", gap, flush=True)
    if gap > 0.005:
        raise SystemExit("replica does not reproduce the engine — stop")

    def zero(key):
        return lambda a, x: {**a, key: 0.0}
    arms = {"base": base, "X1_no_wet": [arm(r, zero("wet")) for r in races],
            "X2_no_proven_class": [arm(r, zero("proven_class")) for r in races],
            "X3_no_full_time": [arm(r, zero("full_time")) for r in races]}
    pen = ec.FORM_QUALITY_TRIP_CHANGE_PEN
    ec.FORM_QUALITY_TRIP_CHANGE_PEN = 0.0
    x4 = []
    for r in races:
        fq = fe.fq_scores(r)
        it = iter(fq)
        x4.append(arm(r, lambda a, x: {**a, "features": {**a["features"], "form_quality_score": round(next(it), 6)}}))
    ec.FORM_QUALITY_TRIP_CHANGE_PEN = pen
    arms["X4_no_trip_pen"] = x4
    for name, built in arms.items():
        (out / f"{name}.json").write_text(json.dumps({"races": built}))
        changed = sum(1 for a, b in zip(base, built) if [x["ability"] for x in a["rows"]] != [x["ability"] for x in b["rows"]])
        print("built", name, "races changed", changed, flush=True)

    # X5 安全欄：只對調頭 1／2。量首選上名率、頭馬率。
    clean = [(r, b) for r, b in zip(races, base) if r["date"] >= "2026-08-05"
             and sum(x["pos"] <= 3 for x in r["rows"]) >= 3 and any(x["pos"] == 1 for x in r["rows"])]
    per_day = {}
    swaps = 0
    for r, b in clean:
        order = sorted(range(len(b["rows"])), key=lambda i: (-b["rows"][i]["ability"], b["rows"][i]["n"]))
        top = order[0]
        rail_top = top
        if _default_leaf_count({"feature_scores": r["rows"][top]["features"]}) >= THIN_EVIDENCE_MIN_DEFAULTS:
            rail_top = order[1]
            swaps += 1
        d = per_day.setdefault(r["date"], [0, 0, 0, 0, 0])
        d[0] += b["rows"][top]["pos"] <= 3
        d[1] += b["rows"][rail_top]["pos"] <= 3
        d[2] += b["rows"][top]["pos"] == 1
        d[3] += b["rows"][rail_top]["pos"] == 1
        d[4] += 1
    days = sorted(per_day)
    def stat(ds, i, j):
        n = sum(per_day[d][4] for d in ds)
        return (sum(per_day[d][j] for d in ds) - sum(per_day[d][i] for d in ds)) / n
    rng = random.Random(7)
    res = {"races": len(clean), "swaps": swaps}
    for label, i, j in (("top_pick_place", 0, 1), ("top_pick_win", 2, 3)):
        boots = sorted(stat([days[rng.randrange(len(days))] for _ in days], i, j) for _ in range(2000))
        n = sum(per_day[d][4] for d in days)
        res[label] = {"without": round(sum(per_day[d][i] for d in days) / n, 4),
                      "with_rail": round(sum(per_day[d][j] for d in days) / n, 4),
                      "delta": round(stat(days, i, j), 4), "ci": [round(boots[50], 4), round(boots[1949], 4)]}
    print("X5 thin-evidence rail", json.dumps(res), flush=True)
    (out / "x5_rail.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
