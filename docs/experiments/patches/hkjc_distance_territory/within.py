"""EXP-20261122-22：殘差拆場間／場內（重用 build_terr.py 嘅特徵）。用法：python3 within.py <base.jsonl>"""
import sys, numpy as np
sys.argv = [sys.argv[0], sys.argv[1], "/dev/null"]
src = open("build_terr.py").read().split("def strip_d1")[0]
ns = {"__name__": "build_terr"}
exec(src, ns)
rows, season, F = ns["rows"], ns["season"], ns["F"]
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_incidents")
from diag_full import calibrate
calib = calibrate(rows)
from collections import defaultdict
out = defaultdict(list)
for x in rows:
    s = season(x["date"])
    if s < 2020: continue
    keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
    r = np.array([x["horses"][i]["raw"] for i in keep]); rc = r - r.mean(); a, bb = calib[s]
    p = 1/(1+np.exp(-(a+bb*rc))); y = np.array([int(x["horses"][i]["pos"] <= 3) for i in keep])
    resid = y - p; resid_w = resid - resid.mean()       # 場內置中殘差（排名層面）
    for col, name in ((1, "新領域≥200"), (2, "對上仗≥200"), (0, "D1")):
        f = F[id(x)][keep, col]; frac = f.mean()
        w = "dev" if s <= 2023 else "hold"
        for fi, ri, rw in zip(f, resid, resid_w):
            if fi: out[(name, w, "全部")].append((ri, rw)); out[(name, w, "場內≤30%有旗" if frac <= 0.3 else "場內>30%有旗")].append((ri, rw))
for k in sorted(out):
    v = np.array(out[k]); print(k, f"n={len(v)} 原殘差 {100*v[:,0].mean():+.1f}pp  場內置中殘差 {100*v[:,1].mean():+.1f}pp")
