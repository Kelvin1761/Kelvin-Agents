#!/usr/bin/env python3
"""EXP-20261116-21 手機部分：HKJC 式 FT（前段＋全程對頭三名標準、扣當日場地速度）arm H／H1／H2／H0。

    PYTHONDONTWRITEBYTECODE=1 python3 ft.py <raw/mob> <events.json> <outdir>

同 EXP-18（deep.py）一樣嘅場次、base、殘差 conditional logit、v3；k 網格換成預先登記嘅 {0.05, 0.10, 0.15, 0.25}。
"""
from __future__ import annotations

import collections
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import deep  # noqa: E402

ev = deep.ev
STD_BEFORE = "2026-11-06"
ARMS = ("H", "H1", "H2", "H0")
CLIP, MIN_STD, MIN_VAR, MAX_RUNS, MIN_RUNS = 2.5, 20, 8, 6, 2


def gfam(c):
    return deep.going_family(c)


def distinct_runs(pages):
    out = {}
    for _e, runners in pages:
        for r in runners:
            for run in r["runs"]:
                if run.get("unparsed") or run["time"] <= 0:
                    continue
                out.setdefault((deep.norm(r["name"]), run["date"], run["track"]), run)
    return out


def pos_int(run):
    try:
        return int(str(run.get("pos") or "").strip())
    except ValueError:
        return None


def early(run):
    ol = deep.own_l600(run)
    if ol is None or run["distance"] <= 800 or run["time"] - ol <= 0:
        return None
    return run["time"] - ol


def build(runs):
    top = collections.defaultdict(lambda: {"t": [], "e": []})
    for (_n, d, _t), run in runs.items():
        if d >= STD_BEFORE or (pos_int(run) or 99) > 3:
            continue
        for key in ((run["track"], run["distance"]), ("_", round(run["distance"], -2), gfam(run["condition"]))):
            top[key]["t"].append(run["time"])
            e = early(run)
            if e is not None:
                top[key]["e"].append(e)
    std = {k: {s: statistics.median(v) for s, v in d.items() if len(v) >= MIN_STD} for k, d in top.items()}

    def lookup(run, s):
        for key in ((run["track"], run["distance"]), ("_", round(run["distance"], -2), gfam(run["condition"]))):
            if s in std.get(key, {}):
                return std[key][s]
        return None

    dev = {}
    for k, run in runs.items():
        st = lookup(run, "t")
        d = {}
        if st is not None:
            d["total"] = (run["time"] - st) / (run["distance"] / 400)
        e, se = early(run), lookup(run, "e")
        if e is not None and se is not None:
            d["first"] = (e - se) / ((run["distance"] - 600) / 400)
        dev[k] = d
    day = collections.defaultdict(lambda: collections.defaultdict(list))
    for (n, d, t), x in dev.items():
        for s, v in x.items():
            day[(t, d)][s].append(v)
    var = {k: {s: statistics.median(v) for s, v in x.items() if len(v) >= MIN_VAR} for k, x in day.items()}
    vals = {}
    for (n, d, t), x in dev.items():
        vv = var.get((t, d), {})
        vals[(n, d, t)] = {
            "f": -(x["first"] - vv.get("first", 0.0)) if "first" in x else None,
            "t": -(x["total"] - vv.get("total", 0.0)) if "total" in x else None,
            "f0": -x["first"] if "first" in x else None,
            "t0": -x["total"] if "total" in x else None,
        }
    const = {}
    for s in ("f", "t", "f0", "t0"):
        pool = [v[s] for (n, d, t), v in vals.items() if d < STD_BEFORE and v[s] is not None]
        const[s] = (statistics.mean(pool), statistics.pstdev(pool))
    info = {"distinct_runs": len(runs), "std_cells": sum(1 for v in std.values() if v),
            "variant_cells": sum(1 for v in var.values() if v), "const": const}
    return vals, const, info


def horse_arms(name, runs_of_horse, day, vals, const):
    """runs_of_horse：嗰匹馬頁面上嘅往績行。→ {H, H1, H2, H0}。"""
    keyed = sorted(((r["date"], r["track"]) for r in runs_of_horse if not r.get("unparsed") and r["date"] < day), reverse=True)
    agg = {}
    for s in ("f", "t", "f0", "t0"):
        zs = []
        for d, t in keyed:
            v = vals.get((name, d, t), {}).get(s)
            if v is None:
                continue
            m, sd = const[s]
            zs.append(max(-CLIP, min(CLIP, (v - m) / sd)))
            if len(zs) == MAX_RUNS:
                break
        if len(zs) >= MIN_RUNS:
            w = [1 / (k + 1) for k in range(len(zs))]
            agg[s] = sum(a * b for a, b in zip(w, zs)) / sum(w)
    out = {"H1": agg.get("f"), "H2": agg.get("t")}
    out["H"] = (agg["f"] + agg["t"]) / 2 if "f" in agg and "t" in agg else None
    out["H0"] = (agg["f0"] + agg["t0"]) / 2 if "f0" in agg and "t0" in agg else None
    return out


def main():
    mob, evs, out = Path(sys.argv[1]), json.load(open(sys.argv[2])), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    pages = ev.load_pages(mob, evs)
    runs = distinct_runs(pages)
    vals, const, info = build(runs)
    J, _C = deep.joined_runs(pages, {})
    S = deep.build_standards(J)
    lpos = {(e["id"], deep.norm(r["name"])): deep.horse_features(pairs, S).get(("Lpos", "avg4")) for e, r, pairs in J}
    results = ev.load_results()
    races, sc_cache = [], {}
    for e, runners in pages:
        if e["folder"] not in sc_cache:
            sc_cache[e["folder"]] = deep.load_rows(e["folder"])
        sc = sc_cache[e["folder"]].get(e["race"], {})
        res = results.get((e["day"], deep.norm(e["venue"]), e["race"]), {})
        if not sc or not res:
            continue
        by = {deep.norm(r["name"]): r["runs"] for r in runners}
        rows = []
        for n, row in sc.items():
            if n not in res:
                continue
            f = horse_arms(n, by.get(n, []), e["day"], vals, const)
            f["Lpos"] = lpos.get((e["id"], n))
            rows.append({"n": n, "base": row["final"], "pos": res[n], "f": f})
        if len(rows) >= 4:
            races.append({"day": e["day"], "id": e["id"], "rows": rows})
    races.sort(key=lambda r: (r["day"], r["id"]))
    keys = ARMS + ("Lpos",)
    for r in races:
        bz = deep.zin([x["base"] for x in r["rows"]])
        for x, b in zip(r["rows"], bz):
            x["z"] = {"base": b}
        for k in keys:
            for x, z in zip(r["rows"], deep.zin([x["f"].get(k) for x in r["rows"]])):
                x["z"][k] = z
    rep = {"info": info, "races": len(races),
           "coverage": {k: sum(1 for r in races for x in r["rows"] if x["f"].get(k) is not None) for k in keys},
           "horses": sum(len(r["rows"]) for r in races)}
    stand, resid, pv = {}, {}, {}
    for k in keys:
        wa, pa, cb = (collections.defaultdict(list) for _ in range(3))
        for r in races:
            have = [x for x in r["rows"] if x["f"].get(k) is not None]
            if len(have) < 4:
                continue
            v = [x["f"][k] for x in have]
            for byd, tgt in ((wa, [x["pos"] == 1 for x in have]), (pa, [x["pos"] <= 3 for x in have])):
                a = ev.race_auc(v, tgt)
                if a is not None:
                    byd[r["day"]].append(a)
            if statistics.pstdev(v) > 0 and statistics.pstdev([x["base"] for x in have]) > 0:
                cb[r["day"]].append(ev.pearson(v, [x["base"] for x in have]))
        mean = lambda xs: statistics.mean(xs) if xs else None  # noqa: E731
        stand[k] = {"win_auc": deep.boot_days(wa, mean), "place_auc": deep.boot_days(pa, mean),
                    "corr_with_base": deep.boot_days(cb, mean)[0]}
        resid[k] = deep.boot_clogit(races, "place", ["base", k])
        if k in ARMS:
            pv[k] = resid[k]["p_boot"]
    rep["standalone"], rep["residual"], rep["holm"] = stand, resid, deep.holm_adjust(pv)
    rep["joint_H_Lpos"] = deep.boot_clogit(races, "place", ["base", "Lpos", "H"])
    deep.K_GRID = (0.05, 0.10, 0.15, 0.25)

    def integ(key):
        res = deep.integrate([dict(r, rows=[dict(x, z={**x["z"], f"{key}.avg4": x["z"][key]}) for x in r["rows"]])
                              for r in races], f"{key}.avg4")
        return res
    rep["integration"] = {k: integ(k) for k in keys}
    (out / "ft_report.json").write_text(json.dumps(rep, indent=1, default=str, ensure_ascii=False))
    print(json.dumps({k: rep[k] for k in ("info", "races", "coverage", "holm")}, indent=1, default=str))


if __name__ == "__main__":
    main()
