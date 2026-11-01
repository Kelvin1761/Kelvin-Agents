#!/usr/bin/env python3
"""EXP-20261101-31 離線 replica 同 arm 產生器。規格見 protocol —— 唔准喺度改。

    python3 au_l600_pit_standard_eval_20261101.py --dump dump_shipped.json --races races.json --outdir ARMS

base = 現行 delta（replica 必須同引擎一致）；S／S0 = 每個目標賽日用之前賽事 fit 嘅情境標準重算 delta。
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))
from au_racing_engine.full_time_speed import ContextStandard, class_key  # noqa: E402
import au_l600_weighting_eval_20261101 as w  # noqa: E402  (pace figure replica, arm "R" = live)

MIN_HISTORY = 100
MATCH_TOL = 0.006


class L600Standard(ContextStandard):
    def length(self, event):
        return 600.0


def event(race):
    return {"track": race["track"], "date": race["date"], "distance": race["distance"],
            "going": race["going"], "rating": "unknown", "rail": "unknown",
            "class": class_key("RaceClass:[" + (race.get("cls") or "") + "]"), "l600": race["raw"]}


def new_deltas(races_by_key, target_date, variant):
    """→ {key: 新 delta}，只用 date < target_date 嘅可靠賽事 fit。"""
    keys = [k for k, r in races_by_key.items() if r["reliable"] and r["date"] < target_date]
    if len(keys) < MIN_HISTORY:
        return {}
    events = [event(races_by_key[k]) for k in keys]
    model = L600Standard(events, "l600")
    resid = {}
    days = defaultdict(list)
    for k, e in zip(keys, events):
        r = math.log(e["l600"] / 600.0) - model.predict(e)
        resid[k] = r
        days[(e["track"], e["date"])].append(k)
    out = {}
    for k, e in zip(keys, events):
        par = model.predict(e, True)
        if variant:
            others = [resid[o] for o in days[(e["track"], e["date"])] if o != k]
            if len(others) >= 3:
                par += float(np.clip(statistics.median(others), -0.05, 0.05)) * len(others) / (len(others) + 3)
        out[k] = round(e["l600"] - 600.0 * math.exp(par), 3)
    return out


def build_index(races_by_key):
    idx = defaultdict(list)
    for k, r in races_by_key.items():
        idx[(r["date"], r["distance"])].append((k, r["all_deltas"]))
    return idx


def match(run, idx):
    try:
        d, dist, delta = run.get("run_date"), int(float(run.get("distance"))), float(run.get("l600_delta"))
    except (TypeError, ValueError):
        return None
    hits = [k for k, deltas in idx.get((d, dist), []) if any(abs(delta - x) <= MATCH_TOL for x in deltas)]
    return hits[0] if len(hits) == 1 else None


def remap(race, idx, deltas, stats):
    field = {}
    for n, runs in race["pf_field"].items():
        new_runs = []
        for run in runs:
            run = dict(run)
            if run.get("l600_delta") is not None:
                stats["runs"] += 1
                key = match(run, idx)
                if key is None:
                    stats["unmatched"] += 1
                elif key not in deltas:
                    stats["unreliable_or_no_fit"] += 1
                else:
                    stats["replaced"] += 1
                    run["l600_delta"] = deltas[key]
            new_runs.append(run)
        field[n] = new_runs
    return {**race, "pf_field": field}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--races", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    dump = json.loads(Path(args.dump).read_text(encoding="utf-8"))
    races_by_key = json.loads(Path(args.races).read_text(encoding="utf-8"))
    idx = build_index(races_by_key)

    gaps = 0
    for r in w.clean(dump["races"]):
        b = w.build(r, "R")
        gaps += sum(abs(y["features"]["pace_figure_score"] - x["features"]["pace_figure_score"]) > 1e-3
                    for x, y in zip(r["rows"], b["rows"]))
    print("replica rows off:", gaps, flush=True)
    if gaps:
        raise SystemExit("replica does not reproduce the engine — stop")

    arms = {"base": [], "S": [], "S0": []}
    stats = {a: defaultdict(int) for a in ("S", "S0")}
    cache = {}
    for i, race in enumerate(dump["races"]):
        arms["base"].append(w.build(race, "R"))
        for arm, variant in (("S", True), ("S0", False)):
            ck = (race["date"], variant)
            if ck not in cache:
                cache[ck] = new_deltas(races_by_key, race["date"], variant)
            arms[arm].append(w.build(remap(race, idx, cache[ck], stats[arm]), "R"))
        if i % 500 == 0:
            print("race", i, race["date"], flush=True)
    for arm in ("S", "S0"):
        s = stats[arm]
        print(arm, dict(s), "replaced share %.1f%%" % (100 * s["replaced"] / max(1, s["runs"])), flush=True)

    clean = w.clean(dump["races"])
    clean_keys = {(r["meeting"], r["race"]) for r in clean}
    def only_pf(built_races, arm_name):
        m = {}
        for b in built_races:
            if (b["meeting"], b["race"]) in clean_keys:
                m[(b["meeting"], b["race"])] = b
        return m
    base_map, desc = only_pf(arms["base"], "base"), {"stats": {a: dict(s) for a, s in stats.items()}}
    # leaf AUC（只計有 PF 往績嘅馬）
    def parts(built):
        days = {}
        for r in clean:
            b = built[(r["meeting"], r["race"])]
            ok = [(y["features"]["pace_figure_score"], x["pos"] <= 3) for x, y in zip(r["rows"], b["rows"])
                  if r["pf_field"].get(str(x["n"]))]
            hit = tot = 0.0
            for a, pa in ok:
                for c, pc in ok:
                    if pa and not pc:
                        tot += 1; hit += 1.0 if a > c else 0.5 if a == c else 0.0
            h, t = days.get(r["date"], (0.0, 0.0)); days[r["date"]] = (h + hit, t + tot)
        return days
    bp = parts(base_map)
    desc["leaf_auc_base"] = round(sum(h for h, _ in bp.values()) / sum(t for _, t in bp.values()), 5)
    for arm in ("S", "S0"):
        desc[f"leaf_auc_{arm}"] = w.paired(bp, parts(only_pf(arms[arm], arm)))
    # 後備表往績佔比（分層用）：按 baseline 首選以外，全場 PF 行喺後備表場地嘅比例
    from au_racing_engine.engine_core import _STANDARD_600M
    for arm, built in arms.items():
        for race, b in zip(dump["races"], built):
            tot = fb = 0
            for runs in race["pf_field"].values():
                for run in runs:
                    k = match(run, idx)
                    if k:
                        tot += 1; fb += races_by_key[k]["track"] not in _STANDARD_600M
            b["tags"]["fallback_share"] = fb / tot if tot else 0.0
        (out / f"{arm}.json").write_text(json.dumps({"races": built}))
    print(json.dumps(desc, indent=1), flush=True)
    (out / "describe.json").write_text(json.dumps(desc, indent=1))


if __name__ == "__main__":
    main()
