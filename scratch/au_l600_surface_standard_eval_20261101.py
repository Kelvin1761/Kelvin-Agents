#!/usr/bin/env python3
"""EXP-20261101-33 SH／G arm 產生器。規格見 protocol —— 唔准喺度改。

    python3 au_l600_surface_standard_eval_20261101.py --root AU_ROOT --dump dump_shipped.json \
        --races races.json --outdir ARMS
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
sys.path.insert(0, str(HERE.parent / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
sys.path.insert(0, str(HERE))
import au_l600_weighting_eval_20261101 as w  # noqa: E402
from au_l600_pit_standard_eval_20261101 import build_index, match, remap  # noqa: E402
from au_l600_standard_dig_20261101 import horse_runs  # noqa: E402

MIN_RACES = 100
ITERS, HORSE_SHRINK, TRACK_SHRINK = 30, 1.0, 20.0


def design(dist, going_idx, n_going):
    ld = np.log(dist / 1400.0)
    X = np.zeros((len(dist), 3 + max(0, n_going - 1)))
    X[:, 0], X[:, 1], X[:, 2] = 1.0, ld, ld * ld
    for j in range(1, n_going):
        X[:, 2 + j] = (going_idx == j)
    return X


def new_deltas(runs, races_by_key, target, use_track):
    rows = [r for r in runs if r["date"] < target]
    rkeys = sorted({r["key"] for r in rows})
    if len(rkeys) < MIN_RACES:
        return {}
    goings = sorted({races_by_key[k]["going"] for k in rkeys})
    gmap = {g: i for i, g in enumerate(goings)}
    tracks = sorted({races_by_key[k]["track"] for k in rkeys})
    tmap = {t: i for i, t in enumerate(tracks)}
    horses = sorted({r["horse"] for r in rows})
    hmap = {h: i for i, h in enumerate(horses)}
    y = np.array([math.log(r["own"] / 600.0) for r in rows])
    hid = np.array([hmap[r["horse"]] for r in rows])
    tid = np.array([tmap[r["track"]] for r in rows])
    X = design(np.array([r["distance"] for r in rows], dtype=float),
               np.array([gmap[r["going"]] for r in rows]), len(goings))
    hn, tn = np.bincount(hid, minlength=len(horses)), np.bincount(tid, minlength=len(tracks))
    hfe, tfe = np.zeros(len(horses)), np.zeros(len(tracks))
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    for _ in range(ITERS):
        base = X @ beta
        hfe = np.bincount(hid, y - base - tfe[tid], minlength=len(horses)) / (hn + HORSE_SHRINK)
        if use_track:
            tfe = np.bincount(tid, y - base - hfe[hid], minlength=len(tracks)) / (tn + TRACK_SHRINK)
            tfe -= tfe.mean()
        beta = np.linalg.lstsq(X, y - hfe[hid] - tfe[tid], rcond=None)[0]
    resid = y - hfe[hid] - X @ beta - tfe[tid]
    by_race = defaultdict(list)
    for r, e in zip(rows, resid):
        by_race[r["key"]].append(float(e))
    race_resid = {k: statistics.median(v) for k, v in by_race.items()}
    days = defaultdict(list)
    for k in race_resid:
        days[(races_by_key[k]["track"], races_by_key[k]["date"])].append(k)
    out = {}
    for k in rkeys:
        race = races_by_key[k]
        x = design(np.array([float(race["distance"])]), np.array([gmap[race["going"]]]), len(goings))[0]
        par = float(x @ beta) + (float(tfe[tmap[race["track"]]]) if use_track else 0.0)
        others = [race_resid[o] for o in days[(race["track"], race["date"])] if o != k]
        if len(others) >= 3:
            par += float(np.clip(statistics.median(others), -0.05, 0.05)) * len(others) / (len(others) + 3)
        out[k] = round(race["raw"] - 600.0 * math.exp(par), 3)
    return out


def rho_pf_fq(built, clean_keys):
    vals = []
    for b in built:
        if (b["meeting"], b["race"]) not in clean_keys or len(b["rows"]) < 5:
            continue
        a = [x["features"]["pace_figure_score"] for x in b["rows"]]
        c = [x["features"]["form_quality_score"] for x in b["rows"]]
        ra = np.argsort(np.argsort(a)); rc = np.argsort(np.argsort(c))
        if ra.std() > 0 and rc.std() > 0:
            vals.append(float(np.corrcoef(ra, rc)[0, 1]))
    return round(statistics.mean(vals), 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--dump", required=True)
    ap.add_argument("--races", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    dump = json.loads(Path(args.dump).read_text(encoding="utf-8"))
    races_by_key = json.loads(Path(args.races).read_text(encoding="utf-8"))
    runs = horse_runs(args.root, races_by_key)
    print("horse-runs", len(runs), flush=True)
    idx = build_index(races_by_key)

    clean = w.clean(dump["races"])
    gaps = sum(abs(y["features"]["pace_figure_score"] - x["features"]["pace_figure_score"]) > 1e-3
               for r in clean for x, y in zip(r["rows"], w.build(r, "R")["rows"]))
    print("replica rows off:", gaps, flush=True)
    if gaps:
        raise SystemExit("replica does not reproduce the engine — stop")

    arms = {"base": [], "SH": [], "G": []}
    stats = {a: defaultdict(int) for a in ("SH", "G")}
    cache = {}
    for i, race in enumerate(dump["races"]):
        arms["base"].append(w.build(race, "R"))
        for arm, use_track in (("SH", True), ("G", False)):
            ck = (race["date"], use_track)
            if ck not in cache:
                cache[ck] = new_deltas(runs, races_by_key, race["date"], use_track)
            arms[arm].append(w.build(remap(race, idx, cache[ck], stats[arm]), "R"))
        if i % 500 == 0:
            print("race", i, race["date"], flush=True)

    clean_keys = {(r["meeting"], r["race"]) for r in clean}
    def parts(built):
        bmap = {(b["meeting"], b["race"]): b for b in built}
        days = {}
        for r in clean:
            b = bmap[(r["meeting"], r["race"])]
            ok = [(y["features"]["pace_figure_score"], x["pos"] <= 3) for x, y in zip(r["rows"], b["rows"])
                  if r["pf_field"].get(str(x["n"]))]
            hit = tot = 0.0
            for a, pa in ok:
                for c, pc in ok:
                    if pa and not pc:
                        tot += 1; hit += 1.0 if a > c else 0.5 if a == c else 0.0
            h, t = days.get(r["date"], (0.0, 0.0)); days[r["date"]] = (h + hit, t + tot)
        return days
    bp = parts(arms["base"])
    desc = {"stats": {a: dict(s) for a, s in stats.items()},
            "leaf_auc_base": round(sum(h for h, _ in bp.values()) / sum(t for _, t in bp.values()), 5),
            "rho_pf_form_quality": {a: rho_pf_fq(arms[a], clean_keys) for a in arms}}
    for arm in ("SH", "G"):
        desc[f"leaf_auc_{arm}"] = w.paired(bp, parts(arms[arm]))
    from au_racing_engine.engine_core import _STANDARD_600M
    for arm, built in arms.items():
        for race, b in zip(dump["races"], built):
            tot = fb = 0
            for runs_ in race["pf_field"].values():
                for run in runs_:
                    k = match(run, idx)
                    if k:
                        tot += 1; fb += races_by_key[k]["track"] not in _STANDARD_600M
            b["tags"]["fallback_share"] = fb / tot if tot else 0.0
        (out / f"{arm}.json").write_text(json.dumps({"races": built}))
    print(json.dumps(desc, indent=1), flush=True)
    (out / "describe.json").write_text(json.dumps(desc, indent=1))


if __name__ == "__main__":
    main()
