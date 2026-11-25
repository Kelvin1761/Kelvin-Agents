"""Kelvin 2026-11-26（天下寵兒）：模型成日排頭二、市場成日買、但連續交唔到貨。殘差 = 入頭三 − 之前季校準 p（base 已含上仗賠率）。
往績 = idx horses runs（日期嚴格早過今仗），熱門 = 獨贏賠率 ≤ 5.0，交唔到貨 = 名次 ≥ 4。"""
import json, sys, datetime
import numpy as np
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_incidents")
import hkjc_history_replay_build as b
from diag import season
from diag_full import calibrate
def pdate(s):
    for f in ("%d/%m/%Y", "%d/%m/%y"):
        try: return datetime.datetime.strptime(s, f).strftime("%Y-%m-%d")
        except ValueError: pass
idx = b.load_index(); hist = {}
for hid, h in idx["horses"].items():
    rs = []
    for r in h.get("runs", []):
        d = pdate(r.get("date", ""))
        try: rs.append((d, int(r["pos"]), float(r["win_odds"])))
        except (KeyError, ValueError, TypeError): continue
    hist[hid.split("_")[-1]] = sorted(x for x in rs if x[0])
code = {}
for (d, n), v in idx["results"].items():
    for row in (v["results"] if isinstance(v["results"], list) else []):
        nm = row.get("horse_name", "")
        if "(" in nm: code[(d, int(n), str(row.get("horse_no")))] = nm[nm.rindex("(") + 1:-1]
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
calib = calibrate(rows); recs = []
for x in rows:
    s = season(x["date"])
    if s < 2020: continue
    hs = [h for h in x["horses"] if h["pos"]]
    r = np.array([h["raw"] for h in hs]); rc = r - r.mean(); a, bb = calib[s]
    rank = {h["n"]: i + 1 for i, h in enumerate(sorted(hs, key=lambda h: -h["raw"]))}
    for h, z in zip(hs, rc):
        c = code.get((x["date"], x["race"], str(h["n"])))
        prev = [t for t in hist.get(c, []) if t[0] < x["date"]][-3:]
        if not prev: continue
        fav = lambda t: t[2] <= 5.0
        fail = lambda t: t[1] >= 4
        l1 = prev[-1]
        k = 0
        for t in reversed(prev):
            if fav(t) and fail(t): k += 1
            else: break
        f = {"上仗熱門＋入位": fav(l1) and not fail(l1), "上仗熱門＋輸": fav(l1) and fail(l1),
             "連續 ≥2 仗熱門都輸": k >= 2, "連續 3 仗熱門都輸": k >= 3,
             "上仗熱門＋輸＋今仗模型頭二": fav(l1) and fail(l1) and rank[h["n"]] <= 2,
             "連續 ≥2 仗熱門都輸＋今仗模型頭二": k >= 2 and rank[h["n"]] <= 2,
             "上仗冷門（>10）＋輸": l1[2] > 10 and fail(l1)}
        recs.append(dict(s=s, y=int(h["pos"] <= 3), p=1/(1+np.exp(-(a+bb*z))), f=f))
rng = np.random.default_rng(0)
print("馬次", len(recs))
for k in recs[0]["f"]:
    out = []
    for lo, hi in ((2020, 2023), (2024, 2026)):
        sel = [r for r in recs if lo <= r["s"] <= hi and r["f"][k]]
        if len(sel) < 30: out.append(f"n={len(sel)}"); continue
        y = np.array([r["y"] - r["p"] for r in sel]); bt = [y[rng.integers(0, len(y), len(y))].mean() for _ in range(1000)]
        out.append(f"實{100*np.mean([r['y'] for r in sel]):.0f}%/估{100*np.mean([r['p'] for r in sel]):.0f}% 差{100*y.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] n={len(sel)}")
    print(f"{k:<22} dev {out[0]:<44} ho {out[1]}")
