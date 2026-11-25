#!/usr/bin/env python3
"""EXP-20261125-06 HKJC 簡版：同 AU 一樣嘅分歧組別（第 1–2 步），用回放 jsonl ＋ 最終獨贏賠率（market_ruler.hkjc_odds）。

    PYTHONDONTWRITEBYTECODE=1 python3 hkjc_disagree.py base_live_20261122.jsonl [--since 2020-09-01]

注意：回放 = 用今日 code 重行歷史（唔係 live 紀錄）；賠率只做評估基準。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import disagree as D

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / ".agents/skills/shared_racing/scripts"))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("base"); ap.add_argument("--since", default="2020-09-01")
    ap.add_argument("--boot", type=int, default=400)
    a = ap.parse_args()
    import market_ruler
    odds = market_ruler.hkjc_odds()
    races = []
    for line in open(a.base, encoding="utf-8"):
        x = json.loads(line)
        if "horses" not in x or x["date"] < a.since:
            continue
        venue = str(x.get("venue") or "").replace("AWT", "")
        rows = []
        for h in x["horses"]:
            if not h.get("pos"):
                continue
            sp = odds.get((x["date"], venue, int(x["race"]), int(h["pos"])))
            rows.append({"n": h["n"], "pos": int(h["pos"]), "ability": float(h["raw"]), "sp": sp,
                         "debut": bool(h.get("debut")), "f": dict(h.get("f") or {}), "mm": dict(h.get("m") or {})})
        if len(rows) < 5 or any(not r["sp"] or r["sp"] <= 1 for r in rows):
            continue
        races.append({"date": x["date"], "rows": rows})
    keys = sorted({k for r in races for x in r["rows"] for k in x["f"]}) + sorted({"m:" + k for r in races for x in r["rows"] for k in x["mm"]})
    for r in races:
        rows = r["rows"]
        for i, x in enumerate(sorted(rows, key=lambda x: -x["ability"])):
            x["m"] = i + 1
        for i, x in enumerate(sorted(rows, key=lambda x: x["sp"])):
            x["k"] = i + 1
        inv = np.array([1 / x["sp"] for x in rows]); p = inv / inv.sum()
        for x, pi in zip(rows, p):
            x["mkt_p"] = float(pi); x["placed"] = int(x["pos"] <= 3); x["date"] = r["date"]; x["field_n"] = len(rows)
        for k in keys + ["ability"]:
            v = np.array([float((x["mm"].get(k[2:]) if k.startswith("m:") else x["f"].get(k, x.get(k))) or 0) for x in rows])
            sd = v.std(); z = (v - v.mean()) / sd if sd > 1e-9 else np.zeros_like(v)
            for x, zi in zip(rows, z):
                x.setdefault("z", {})[k] = float(zi)
    co = defaultdict(list)
    for r in races:
        for x in r["rows"]:
            if x["k"] <= 2:
                co["K2"].append(x)
                if x["m"] >= 4:
                    co["D"].append(x); co["A" if x["placed"] else "D_miss"].append(x)
                elif x["m"] <= 3 and x["placed"]:
                    co["C"].append(x)
            if x["m"] <= 2:
                co["M2"].append(x)
                if x["k"] >= 4:
                    co["MD"].append(x); co["M" if x["placed"] else "MD_miss"].append(x)
    allx = [x for r in races for x in r["rows"]]
    y = np.array([x["placed"] for x in allx], float)
    fld = np.array([math.log(x["field_n"]) for x in allx])
    def cal(v):
        b, ll = D.logit_fit(np.column_stack([v, fld]), y)
        return 1 / (1 + np.exp(-(b[0] + b[1] * v + b[2] * fld))), ll
    pmod, llmod = cal(np.array([x["z"]["ability"] for x in allx]))
    pmkt, llmkt = cal(np.array([math.log(x["mkt_p"]) for x in allx]))
    for x, a1, a2 in zip(allx, pmod, pmkt):
        x["pmod"], x["pmkt"] = float(a1), float(a2)
    n_r = len(races)
    res = {"races": n_r, "runners": len(allx), "dates": [races[0]["date"], races[-1]["date"]] if races else None,
           "sizes": {k: len(v) for k, v in co.items()},
           "rates": {"market_top2_place": float(np.mean([x["placed"] for x in co["K2"]])),
                     "model_top2_place": float(np.mean([x["placed"] for x in co["M2"]])),
                     "A_per_race": len(co["A"]) / n_r, "M_per_race": len(co["M"]) / n_r},
           "expect": {g: {"actual": float(np.mean([x["placed"] for x in co[g]])),
                          "market_expected": float(np.mean([x["pmkt"] for x in co[g]])),
                          "model_expected": float(np.mean([x["pmod"] for x in co[g]]))} for g in ("D", "MD")},
           "ll_top3": {"model": llmod, "market": llmkt}}
    dates = sorted({r["date"] for r in races})
    rng = np.random.default_rng(11)
    W = rng.multinomial(len(dates), np.ones(len(dates)) / len(dates), size=a.boot).astype(float)
    tab = {}
    for lab, (ga, gb) in {"A_vs_C": (co["A"], co["C"]), "D_place_vs_miss": (co["A"], co["D_miss"])}.items():
        t = {k: D.boot_smd(ga, gb, lambda x, k=k: x["z"].get(k), dates, W) for k in keys}
        t["debut"] = D.boot_smd(ga, gb, lambda x: float(x["debut"]), dates, W)
        t["field_n"] = D.boot_smd(ga, gb, lambda x: float(x["field_n"]), dates, W)
        tab[lab] = dict(sorted(t.items(), key=lambda kv: -abs(kv[1]["smd"] if kv[1]["smd"] == kv[1]["smd"] else 0)))
    res["smd"] = tab
    # 模型殘差：leaf z>=1 組別
    rm = y - pmod; rk = y - pmkt
    gaps = {}
    for k in keys:
        s = np.array([x["z"][k] >= 1 for x in allx])
        if 0.03 < s.mean() < 0.5:
            gaps[k] = {"coverage": round(float(s.mean()), 3), "model_resid_pp": round(100 * (rm[s].mean() - rm[~s].mean()), 2),
                       "market_resid_pp": round(100 * (rk[s].mean() - rk[~s].mean()), 2)}
    res["resid_gaps_z_ge_1"] = dict(sorted(gaps.items(), key=lambda kv: -abs(kv[1]["model_resid_pp"])))
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
