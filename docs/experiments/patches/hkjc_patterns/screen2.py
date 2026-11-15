import json, pickle, sys
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, sys.path[0])
import feat2
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
feat = feat2.build(); pickle.dump(feat, open(sys.argv[2], "wb"))
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x and 2020 <= season(x["date"]) <= 2023]
X, Y = [], []
for x in rows:
    hs = [h for h in x["horses"] if h["pos"]]; r = np.array([h["raw"] for h in hs]); X += list(r - r.mean()); Y += [h["pos"] <= 3 for h in hs]
m = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X).reshape(-1, 1), Y); a, b = m.intercept_[0], m.coef_[0][0]
res = defaultdict(list); combo = defaultdict(list)
for x in rows:
    hs = [h for h in x["horses"] if h["pos"]]; r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
    for h, z in zip(hs, rc):
        f = feat.get((x["date"], x["race"], h["pos"]))
        if not f or len(f) != 1: continue
        e = float(h["pos"] <= 3) - 1 / (1 + np.exp(-(a + b * z)))
        for k, v in f[0].items():
            if v: res[k].append((x["date"], e))
        f0 = f[0]
        combo[("降班換騎", f0.get("classdrop_jchange", 0), "跌返贏馬分", f0.get("back_on_win_mark", 0))].append((x["date"], e))
rng = np.random.default_rng(0)
def ci(v):
    days = defaultdict(list)
    for d, e in v: days[d].append(e)
    dk = list(days); bs = [np.mean([q for i in rng.integers(0, len(dk), len(dk)) for q in days[dk[i]]]) for _ in range(500)]
    return np.percentile(bs, [2.5, 97.5]) * 100
for k, v in sorted(res.items(), key=lambda t: -np.mean([q[1] for q in t[1]])):
    lo, hi = ci(v); print(f"{'✅' if lo > 0 or hi < 0 else '  '} {k:26s} n={len(v):6d} 殘差 {np.mean([q[1] for q in v]) * 100:+6.2f}pp [{lo:+.2f},{hi:+.2f}]")
print("—— 降班＋換騎 × 跌返贏馬分（三至五班）")
for k, v in sorted(combo.items()):
    if len(v) >= 100: lo, hi = ci(v); print(f"   {k}  n={len(v)} 殘差 {np.mean([q[1] for q in v]) * 100:+.2f}pp [{lo:+.2f},{hi:+.2f}]")
