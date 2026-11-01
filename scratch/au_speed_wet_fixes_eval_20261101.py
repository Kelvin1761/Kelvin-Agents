#!/usr/bin/env python3
"""EXP-20261101-37 GW／GWX arm 產生器。規格見 protocol —— 唔准喺度改。

    python3 au_speed_wet_fixes_eval_20261101.py --root AU_ROOT --dump dump_shipped.json --races races.json --outdir ARMS
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
sys.path.insert(0, str(HERE))
import au_l600_weighting_eval_20261101 as w  # noqa: E402
from au_l600_pit_standard_eval_20261101 import build_index, match  # noqa: E402
from au_l600_standard_dig_20261101 import horse_runs  # noqa: E402
from au_l600_surface_standard_eval_20261101 import new_deltas  # noqa: E402
from au_racing_engine.full_time_speed import condition_key  # noqa: E402

GOING_MISMATCH_WEIGHT = 0.5      # full_time_speed.aggregate
TODAY = {"going": None}
_orig_run_weights = w.run_weights


def run_weights(runs, arm, today):
    ws = _orig_run_weights(runs, arm.replace("W", ""), today)
    if "W" in arm and TODAY["going"] in ("firm", "good", "soft", "heavy", "synthetic"):
        for i, run in enumerate(runs):
            g = run.get("_going")
            if g in ("firm", "good", "soft", "heavy", "synthetic") and g != TODAY["going"]:
                ws[i] *= GOING_MISMATCH_WEIGHT
    return ws


w.run_weights = run_weights


def remap(race, idx, deltas, races_by_key):
    field = {}
    for n, runs in race["pf_field"].items():
        out = []
        for run in runs:
            run = dict(run)
            if run.get("l600_delta") is not None:
                key = match(run, idx)
                if key is not None:
                    run["_going"] = races_by_key[key]["going"]
                    if key in deltas:
                        run["l600_delta"] = deltas[key]
            out.append(run)
        field[n] = out
    return {**race, "pf_field": field}


def no_wet(race):
    return {**race, "rows": [{**x, "wet": 0.0} for x in race["rows"]]}


def main():
    ap = argparse.ArgumentParser()
    for a in ("--root", "--dump", "--races", "--outdir"):
        ap.add_argument(a, required=True)
    args = ap.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    dump = json.loads(Path(args.dump).read_text())
    races_by_key = json.loads(Path(args.races).read_text())
    runs = horse_runs(args.root, races_by_key)
    idx = build_index(races_by_key)
    gaps = sum(abs(y["features"]["pace_figure_score"] - x["features"]["pace_figure_score"]) > 1e-3
               for r in w.clean(dump["races"]) for x, y in zip(r["rows"], w.build(r, "R")["rows"]))
    print("replica rows off:", gaps, flush=True)
    if gaps:
        raise SystemExit("replica does not reproduce the engine — stop")
    arms = {"base": [], "G": [], "GW": [], "GWX": []}
    cache = {}
    for i, race in enumerate(dump["races"]):
        TODAY["going"] = None
        arms["base"].append(w.build(race, "R"))
        if race["date"] not in cache:
            cache[race["date"]] = new_deltas(runs, races_by_key, race["date"], False)
        mapped = remap(race, idx, cache[race["date"]], races_by_key)
        arms["G"].append(w.build(mapped, "R"))
        TODAY["going"] = condition_key(race["rows"][0].get("going") or "")
        gw = w.build(mapped, "RW")
        arms["GW"].append(gw)
        arms["GWX"].append(w.build(no_wet(mapped), "RW"))
        for a in ("G", "GW", "GWX"):
            arms[a][-1]["tags"]["today_going"] = TODAY["going"]
        arms["base"][-1]["tags"]["today_going"] = TODAY["going"]
        if i % 1000 == 0:
            print("race", i, race["date"], flush=True)
    for a, built in arms.items():
        for b in built:
            b["tags"]["fallback_share"] = 0.0
        (out / f"{a}.json").write_text(json.dumps({"races": built}))
    print("built", list(arms), flush=True)


if __name__ == "__main__":
    main()
