"""HKJC 殘差篩（EXP-20261125-06 §6 嘅正式版）：v5 校準 p = σ(a+α·Δraw+γ·logit(3/N))，(a,α,γ) 只用之前季 fit；
組別 = 場內 z ≥ 1（或旗號）；dev／holdout 分開；賽日 bootstrap。只出假設，唔調參。"""
import json, sys
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
def feats(x):
    hs = [h for h in x["horses"] if h["pos"]]
    r = np.array([h["raw"] for h in hs]); N = len(hs)
    return hs, r - r.mean(), np.full(N, np.log(3/(N-3)) if N > 3 else 0.0)
cal = {}
for s in sorted(by):
    if s < 2020: continue
    X, Y = [], []
    for t in by:
        if t < s and t >= 2019:
            for x in by[t]:
                hs, d, l = feats(x); X += list(zip(d, l)); Y += [int(h["pos"] <= 3) for h in hs]
    cal[s] = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X), Y)
recs = []
for x in rows:
    s = season(x["date"])
    if s not in cal: continue
    hs, d, l = feats(x)
    p = cal[s].predict_proba(np.column_stack([d, l]))[:, 1]
    rank = {h["n"]: i + 1 for i, h in enumerate(sorted(hs, key=lambda h: -h["raw"]))}
    keys = list(hs[0]["m"]) + ["debut"]
    Z = {}
    for k in hs[0]["m"]:
        v = np.array([h["m"].get(k, 60) for h in hs], float); sd = v.std()
        Z[k] = (v - v.mean()) / sd if sd > 0 else np.zeros(len(v))
    for i, h in enumerate(hs):
        f = {f"{k} z≥1": Z[k][i] >= 1 for k in hs[0]["m"]}
        f.update({f"{k} z≤−1": Z[k][i] <= -1 for k in hs[0]["m"]})
        f["初出"] = bool(h.get("debut"))
        f["模型首選"] = rank[h["n"]] == 1
        f["模型 4–6"] = 4 <= rank[h["n"]] <= 6
        recs.append(dict(s=s, day=x["date"], y=int(h["pos"] <= 3), p=float(p[i]), f=f))
rng = np.random.default_rng(0)
def boot(sel):
    days = defaultdict(list)
    for r in sel: days[r["day"]].append(r["y"] - r["p"])
    ks = list(days); vals = []
    for _ in range(600):
        pick = rng.integers(0, len(ks), len(ks)); a = [v for j in pick for v in days[ks[j]]]
        vals.append(np.mean(a))
    return np.percentile(vals, [2.5, 97.5])
out = []
for k in recs[0]["f"]:
    line = []
    for lo, hi in ((2020, 2023), (2024, 2026)):
        sel = [r for r in recs if lo <= r["s"] <= hi and r["f"][k]]
        if len(sel) < 200: line.append(None); continue
        m = np.mean([r["y"] - r["p"] for r in sel]); lo_, hi_ = boot(sel)
        line.append((100*m, 100*lo_, 100*hi_, len(sel)))
    if None in line: continue
    both = (line[0][1] > 0 and line[1][1] > 0) or (line[0][2] < 0 and line[1][2] < 0)
    out.append((both, k, line))
for both, k, (d, h) in sorted(out, key=lambda t: (not t[0], -abs(t[2][0][0]))):
    print(f"{'★' if both else ' '} {k:<26} dev {d[0]:+.1f}[{d[1]:+.1f},{d[2]:+.1f}] n={d[3]:<6} ho {h[0]:+.1f}[{h[1]:+.1f},{h[2]:+.1f}] n={h[3]}")
