"""篩選：每個 flag 對現行 raw（含上仗賠率，walk-forward）嘅 dev 殘差。"""
import json
import pickle
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, sys.path[0])
import features  # noqa: E402


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


feat = features.build()
pickle.dump(feat, open(sys.argv[2], "wb"))
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x and 2020 <= season(x["date"]) <= 2023]
X, Y = [], []
for x in rows:
    hs = [h for h in x["horses"] if h["pos"]]
    r = np.array([h["raw"] for h in hs]); X += list(r - r.mean()); Y += [h["pos"] <= 3 for h in hs]
m = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X).reshape(-1, 1), Y)
a, b = m.intercept_[0], m.coef_[0][0]
res = defaultdict(list)
for x in rows:
    hs = [h for h in x["horses"] if h["pos"]]
    r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
    for h, z in zip(hs, rc):
        f = feat.get((x["date"], x["race"], h["pos"]))
        if not f or len(f) != 1:
            continue
        e = float(h["pos"] <= 3) - 1 / (1 + np.exp(-(a + b * z)))
        for k, v in f[0].items():
            if v:
                res[k].append((x["date"], e))
rng = np.random.default_rng(0)
for k, v in sorted(res.items(), key=lambda t: -abs(np.mean([q[1] for q in t[1]]))):
    days = defaultdict(list)
    for d, e in v:
        days[d].append(e)
    dk = list(days)
    bs = [np.mean([q for i in rng.integers(0, len(dk), len(dk)) for q in days[dk[i]]]) for _ in range(500)]
    lo, hi = np.percentile(bs, [2.5, 97.5]) * 100
    mark = "✅" if lo > 0 or hi < 0 else "  "
    print(f"{mark} {k:22s} n={len(v):6d} 殘差 {np.mean([q[1] for q in v]) * 100:+6.2f}pp [{lo:+.2f},{hi:+.2f}]")
