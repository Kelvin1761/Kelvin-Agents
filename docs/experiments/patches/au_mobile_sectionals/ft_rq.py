#!/usr/bin/env python3
"""EXP-20261116-21 QLD 部分：HKJC 式 FT arm 喺 RQ XML（全場逐駒分段）。

    PYTHONDONTWRITEBYTECODE=1 python3 ft_rq.py --out OUT.json

`first` = 完成時間 − 最後 3 段（去到 600m 標記）、`total` = 完成時間；標準 = train 期（< 2026-07-01）頭三名 (場地, 路程) 中位；
當日場地速度 = 同日同場全部馬對標準偏差中位（n ≥ 8）；每 400m；1/k 最近 6 仗、最少 2 仗；z 常數 train 期、截 ±2.5。
疊加喺 `fin.w6`（EXP-42 尺）上 test 期 log-lik／AUC；對我哋模型分殘差（≥ 08-05）。
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics as st
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import deep  # noqa: E402
import rq_deep  # noqa: E402

TARGET_FROM, TEST_FROM, CLEAN_FROM = rq_deep.TARGET_FROM, rq_deep.TEST_FROM, rq_deep.CLEAN_FROM
CLIP, MIN_STD, MIN_VAR, MAX_RUNS, MIN_RUNS = 2.5, 20, 8, 6, 2
ARMS = ("H", "H1", "H2", "H0")


def per_run(races):
    top = collections.defaultdict(lambda: {"t": [], "e": []})
    for (course, date, rno), R in races.items():
        if date >= TEST_FROM:
            continue
        for h in sorted(R["horses"], key=lambda h: h["fin"])[:3]:
            key = (course, h["dist"])
            top[key]["t"].append(h["fin"])
            if h["dist"] > 800:
                top[key]["e"].append(h["early"])
    std = {k: {s: st.median(v) for s, v in d.items() if len(v) >= MIN_STD} for k, d in top.items()}
    dev = []
    for (course, date, rno), R in races.items():
        s = std.get((course, R["horses"][0]["dist"]), {})
        for h in R["horses"]:
            d = {}
            if "t" in s:
                d["total"] = (h["fin"] - s["t"]) / (h["dist"] / 400)
            if "e" in s and h["dist"] > 800:
                d["first"] = (h["early"] - s["e"]) / ((h["dist"] - 600) / 400)
            dev.append((h["horse"], date, course, d))
    day = collections.defaultdict(lambda: collections.defaultdict(list))
    for _h, date, course, d in dev:
        for k, v in d.items():
            day[(course, date)][k].append(v)
    var = {k: {s: st.median(v) for s, v in x.items() if len(v) >= MIN_VAR} for k, x in day.items()}
    runs = collections.defaultdict(list)
    for h, date, course, d in dev:
        vv = var.get((course, date), {})
        runs[h].append((date, {"f": -(d["first"] - vv.get("first", 0)) if "first" in d else None,
                               "t": -(d["total"] - vv.get("total", 0)) if "total" in d else None,
                               "f0": -d["first"] if "first" in d else None,
                               "t0": -d["total"] if "total" in d else None}))
    const = {}
    for s in ("f", "t", "f0", "t0"):
        pool = [v[s] for x in runs.values() for d, v in x if d < TEST_FROM and v[s] is not None]
        const[s] = (st.mean(pool), st.pstdev(pool))
    for x in runs.values():
        x.sort(key=lambda t: t[0], reverse=True)
    return runs, const, {"std_cells": sum(1 for v in std.values() if v), "variant_cells": len(var)}


def arms(runs, const, horse, date):
    agg = {}
    for s in ("f", "t", "f0", "t0"):
        zs = []
        for d, v in runs.get(horse, []):
            if d >= date or v[s] is None:
                continue
            m, sd = const[s]
            zs.append(max(-CLIP, min(CLIP, (v[s] - m) / sd)))
            if len(zs) == MAX_RUNS:
                break
        if len(zs) >= MIN_RUNS:
            w = [1 / (k + 1) for k in range(len(zs))]
            agg[s] = sum(a * b for a, b in zip(w, zs)) / sum(w)
    return {"H1": agg.get("f"), "H2": agg.get("t"),
            "H": (agg["f"] + agg["t"]) / 2 if "f" in agg and "t" in agg else None,
            "H0": (agg["f0"] + agg["t0"]) / 2 if "f0" in agg and "t0" in agg else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--rq", default=str(Path(open(rq_deep.REPO / ".wongchoi_au_data_root").read().strip()).parent / "AU_Racing_Time_Evidence"))
    args = ap.parse_args()
    races = rq_deep.parse(args.rq)
    rel_runs, _info = rq_deep.relative(races)          # fin.w6 / Lpos.w6（EXP-18 定義）
    runs, const, info = per_run(races)
    data = rq_deep.build(races, rel_runs, rq_deep.load_scores())
    keys = ARMS
    for r in data:
        vals = {k: [] for k in keys}
        for x in r["rows"]:
            a = arms(runs, const, x["horse"], r["day"])
            x["ft"] = a
            for k in keys:
                vals[k].append(a[k])
        for k in keys:
            for x, z in zip(r["rows"], deep.zin(vals[k])):
                x["z"][k] = z
    train = [r for r in data if r["day"] < TEST_FROM]; test = [r for r in data if r["day"] >= TEST_FROM]
    rep = {"target_races": len(data), "train": len(train), "test": len(test), "info": info,
           "const": {k: [round(a, 4), round(b, 4)] for k, (a, b) in const.items()},
           "coverage": {k: sum(1 for r in data for x in r["rows"] if x["ft"][k] is not None) for k in keys},
           "horses": sum(len(r["rows"]) for r in data)}
    mean = lambda xs: st.mean(xs) if xs else None  # noqa: E731
    rep["standalone"] = {k: {"place_auc": deep.boot_days(rq_deep.auc_by_day(data, k), mean),
                             "win_auc": deep.boot_days(rq_deep.auc_by_day(data, k, "w"), mean)[0]} for k in keys}
    rep["over_fin"] = {k: rq_deep.test_ll_auc(train, test, ["fin.w6"], ["fin.w6", k]) for k in keys}
    rep["over_fin"]["H+Lpos"] = rq_deep.test_ll_auc(train, test, ["fin.w6"], ["fin.w6", "Lpos.w6", "H"])
    rep["over_fin_plus_Lpos"] = rq_deep.test_ll_auc(train, test, ["fin.w6", "Lpos.w6"], ["fin.w6", "Lpos.w6", "H"])
    based = [r for r in data if r["has_base"]]
    rep["vs_our_model"] = {"races": len(based)}
    if len(based) >= 30:
        rep["vs_our_model"].update({k: deep.boot_clogit(based, "place", ["base", k], n=400) for k in keys})
    Path(args.out).write_text(json.dumps(rep, indent=1, default=str))
    print(json.dumps(rep, indent=1, default=str)[:5000])


if __name__ == "__main__":
    main()
