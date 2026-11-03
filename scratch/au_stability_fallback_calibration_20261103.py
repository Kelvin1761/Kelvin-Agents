#!/usr/bin/env python3
"""EXP-20261103-11：後備組合同場內 z 兩把尺有冇對齊（乾淨窗口 08-05 起）。

    python3 scratch/au_stability_fallback_calibration_20261103.py PATHS.json DUMP.json

超額 = 實際上名（頭 3）− 期望；期望 = 全部馬喺同一個 (模型名次, 馬群大細桶) 嘅上名率。
如果後備馬系統性超額正 → 被低估；負 → 被高估。CI = 按日期 block bootstrap 2,000 次。
"""
import collections
import json
import random
import sys

paths = json.load(open(sys.argv[1]))
races = [r for r in json.load(open(sys.argv[2]))["races"] if r["date"] >= (sys.argv[3] if len(sys.argv) > 3 else "2026-08-05")]


def fbucket(n):
    return "<=8" if n <= 8 else "9-12" if n <= 12 else "13+"


rows = []
for r in races:
    order = sorted(range(len(r["rows"])), key=lambda i: -r["rows"][i]["ability"])
    rank = {i: k + 1 for k, i in enumerate(order)}
    for i, h in enumerate(r["rows"]):
        p = paths.get(f"{r['meeting']}|{r['race']}|{h['n']}") or {}
        rows.append({"date": r["date"], "rank": min(rank[i], 6), "fb": fbucket(len(r["rows"])),
                     "place": int(h["pos"] <= 3), "path": p.get("path"), "career": p.get("career"),
                     "fq": h["features"].get("form_quality_score", 60)})
cell = collections.defaultdict(list)
for x in rows:
    cell[(x["rank"], x["fb"])].append(x["place"])
for x in rows:
    v = cell[(x["rank"], x["fb"])]
    x["excess"] = x["place"] - sum(v) / len(v)
print("horses", len(rows), "paths:", collections.Counter(x["path"] for x in rows).most_common())


def ci(sub):
    by = collections.defaultdict(list)
    for x in sub:
        by[x["date"]].append(x["excess"])
    days = sorted(by)
    rng = random.Random(11)
    est = sum(x["excess"] for x in sub) / len(sub)
    boots = []
    for _ in range(2000):
        pick = [by[d] for d in (rng.choice(days) for _ in days)]
        flat = [e for g in pick for e in g]
        boots.append(sum(flat) / len(flat))
    boots.sort()
    return est, boots[50], boots[1949]


def show(label, sub):
    if len(sub) < 30:
        print(f"{label:38s} n={len(sub)} (too few)")
        return
    est, lo, hi = ci(sub)
    flag = " ⚠️" if lo > 0 or hi < 0 else ""
    print(f"{label:38s} n={len(sub):6d} place {100*sum(x['place'] for x in sub)/len(sub):5.1f}%  "
          f"excess {100*est:+5.2f}pp [{100*lo:+.2f}, {100*hi:+.2f}]{flag}")


FB, Z = "form_quality_fallback_composite", "form_quality_field_relative"
for name, key in (("後備組合", FB), ("場內 z", Z), ("海外代理", "form_quality_overseas_rating_proxy")):
    show(name, [x for x in rows if x["path"] == key])
print("\n後備組合 × 生涯場數")
for lab, f in (("0（初出）", lambda c: c == 0), ("1", lambda c: c == 1), ("2-3", lambda c: c in (2, 3)),
               ("4+", lambda c: c is not None and c >= 4)):
    show("  career " + lab, [x for x in rows if x["path"] == FB and f(x["career"])])
print("\n後備組合 × 模型名次")
for k in range(1, 7):
    show(f"  rank {k}{'+' if k == 6 else ''}", [x for x in rows if x["path"] == FB and x["rank"] == k])
print("\n後備組合 × 近績質素分")
for lab, lo, hi in (("<55", -1, 55), ("55-60", 55, 60), ("60-65", 60, 65), ("65-70", 65, 70), (">=70", 70, 999)):
    show("  fq " + lab, [x for x in rows if x["path"] == FB and lo <= x["fq"] < hi])
print("\n場內 z × 近績質素分")
for lab, lo, hi in (("<55", -1, 55), ("55-60", 55, 60), ("60-65", 60, 65), ("65-70", 65, 70), (">=70", 70, 999)):
    show("  fq " + lab, [x for x in rows if x["path"] == Z and lo <= x["fq"] < hi])
