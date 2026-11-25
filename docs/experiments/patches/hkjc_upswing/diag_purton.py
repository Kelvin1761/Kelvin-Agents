import json, sys, ast
from collections import defaultdict
import numpy as np
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_incidents")
import hkjc_history_replay_build as b
from diag import season
from diag_full import calibrate
idx = b.load_index()
info = {}
for (d, n), v in idx["results"].items():
    res = v["results"] if isinstance(v["results"], list) else []
    for row in res:
        try: dr = int(row.get("draw"))
        except (TypeError, ValueError): dr = None
        info[(d, int(n), str(row.get("horse_no")))] = (row.get("jockey", ""), dr)
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
calib = calibrate(rows); recs = []
for x in rows:
    s = season(x["date"])
    if s < 2020: continue
    hs = [h for h in x["horses"] if h["pos"]]
    r = np.array([h["raw"] for h in hs]); rc = r - r.mean(); a, bb = calib[s]
    order = sorted(hs, key=lambda h: -h["raw"]); rank = {h["n"]: i + 1 for i, h in enumerate(order)}
    gap = order[0]["raw"] - order[1]["raw"]
    for h, z in zip(hs, rc):
        j, dr = info.get((x["date"], x["race"], str(h["n"])), ("", None))
        recs.append(dict(s=s, hv=x["venue"] == "跑馬地", y=int(h["pos"] <= 3), p=1/(1+np.exp(-(a+bb*z))), j=j, dr=dr, rk=rank[h["n"]], gap=gap if rank[h["n"]] == 1 else None))
rng = np.random.default_rng(0)
def show(name, f):
    out = []
    for lo, hi in ((2020, 2023), (2024, 2026)):
        sel = [r for r in recs if lo <= r["s"] <= hi and f(r)]
        if len(sel) < 30: out.append(f"n={len(sel)}"); continue
        y = np.array([r["y"] - r["p"] for r in sel]); bt = [y[rng.integers(0, len(y), len(y))].mean() for _ in range(1000)]
        out.append(f"實{100*np.mean([r['y'] for r in sel]):.0f}%/估{100*np.mean([r['p'] for r in sel]):.0f}% 差{100*y.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] n={len(sel)}")
    print(f"{name:<22} dev {out[0]:<44} ho {out[1]}")
P = lambda r: "潘頓" in r["j"]
show("潘頓 全部", P)
show("潘頓 跑馬地", lambda r: P(r) and r["hv"])
show("潘頓 跑馬地 1–3 檔", lambda r: P(r) and r["hv"] and r["dr"] and r["dr"] <= 3)
show("潘頓 模型首選", lambda r: P(r) and r["rk"] == 1)
show("潘頓 跑馬地 模型首選", lambda r: P(r) and r["hv"] and r["rk"] == 1)
show("非潘頓 模型首選", lambda r: not P(r) and r["rk"] == 1)
show("跑馬地 首選 1–3 檔", lambda r: r["hv"] and r["rk"] == 1 and r["dr"] and r["dr"] <= 3)
show("首選 拋離 ≥ 第90百分位", lambda r: r["gap"] is not None and r["gap"] >= np.percentile([q["gap"] for q in recs if q["gap"] is not None], 90))
show("首選 拋離 ≥90 且潘頓", lambda r: P(r) and r["gap"] is not None and r["gap"] >= np.percentile([q["gap"] for q in recs if q["gap"] is not None], 90))
