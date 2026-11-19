"""Kelvin 2026-11-19（11-18 R9 耀寶：近3仗末段全場最快、名次 5-7-5，模型排 4，由第 9 位贏）：
「末段跑得快但名次差」嘅馬，live 之上殘差。L400 = 分段時間最後一段；名次 rank 喺嗰場之內（1 = 最快）。只用日期嚴格早過今仗嘅賽事。
用法：python3 diag_fast_closer.py <live dump>
"""
import gzip, json, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_incidents")
from diag import season  # noqa: E402
from diag_full import calibrate  # noqa: E402
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as b  # noqa: E402
import re

runs = defaultdict(list)    # code -> [(date, l400_rank, finish, field)]
for line in gzip.open("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/parsed/sectionals.jsonl.gz", "rt", encoding="utf-8"):
    r = json.loads(line)
    hs = [h for h in r["horses"] if h.get("sections") and str(h.get("finish", "")).isdigit()]
    t = [(h["code"], h["sections"][-1].get("time"), int(h["finish"])) for h in hs if isinstance(h["sections"][-1].get("time"), (int, float))]
    if len(t) < 6: continue
    order = {c: i + 1 for i, (c, _, _) in enumerate(sorted(t, key=lambda x: x[1]))}
    for c, _, f in t: runs[c].append((r["date"], order[c], f, len(t)))
for v in runs.values(): v.sort()
idx = b.load_index(); code_of = {}
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        if m: code_of[(d, n, str(row.get("horse_no")))] = m.group(1)

def feats(prev):
    if not prev: return None
    l = prev[-1]; l3 = prev[-3:]
    fast_bad = lambda t: t[1] <= 3 and t[2] >= 5
    return {
        "上仗 L400 前三快＋名次 ≥5": fast_bad(l),
        "上仗 L400 最快＋名次 ≥5": l[1] == 1 and l[2] >= 5,
        "近3仗 ≥2 仗 L400 前三快＋名次 ≥5": len(l3) >= 2 and sum(fast_bad(t) for t in l3) >= 2,
        "近3仗 L400 平均名次 ≤3、平均名次 ≥5": len(l3) == 3 and np.mean([t[1] for t in l3]) <= 3 and np.mean([t[2] for t in l3]) >= 5,
        "上仗 L400 前三快＋入位（對照）": l[1] <= 3 and l[2] <= 3,
        "上仗 L400 慢（後半）＋名次 ≥5（對照）": l[1] > l[3] / 2 and l[2] >= 5,
    }

rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
calib = calibrate(rows); recs = []
for x in rows:
    s = season(x["date"])
    if s < 2020: continue
    hs = [h for h in x["horses"] if h["pos"]]
    r = np.array([h["raw"] for h in hs]); rc = r - r.mean(); a, bb = calib[s]
    rank = {h["n"]: i + 1 for i, h in enumerate(sorted(hs, key=lambda h: -h["raw"]))}
    for h, z in zip(hs, rc):
        c = code_of.get((x["date"], x["race"], str(h["n"])))
        f = feats([t for t in runs.get(c, []) if t[0] < x["date"]]) if c else None
        if f is None: continue
        recs.append(dict(s=s, y=int(h["pos"] <= 3), p=1 / (1 + np.exp(-(a + bb * z))), f=f, rk=rank[h["n"]]))
print("馬次", len(recs))
rng = np.random.default_rng(0)
for k in recs[0]["f"]:
    out = []
    for lo, hi in ((2020, 2023), (2024, 2025)):
        sub = [r for r in recs if lo <= r["s"] <= hi]; sel = [r for r in sub if r["f"][k]]
        if len(sel) < 30: out.append(f"n={len(sel)}"); continue
        y = np.array([r["y"] - r["p"] for r in sel]); bt = [y[rng.integers(0, len(y), len(y))].mean() for _ in range(1000)]
        mid = [r for r in sel if 3 <= r["rk"] <= 6]
        out.append(f"{100*y.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] n={len(sel)}({100*len(sel)/len(sub):.1f}%) 模型排3–6 實{100*np.mean([r['y'] for r in mid]) if mid else 0:.0f}%/估{100*np.mean([r['p'] for r in mid]) if mid else 0:.0f}%")
    seas = [f"{100*np.mean([r['y']-r['p'] for r in recs if r['s']==s and r['f'][k]]):+.0f}" if sum(1 for r in recs if r['s']==s and r['f'][k]) >= 20 else "." for s in sorted({r['s'] for r in recs})]
    print(f"{k}\n   dev {out[0]}\n   ho  {out[1]}\n   逐季 {' '.join(seas)}")
