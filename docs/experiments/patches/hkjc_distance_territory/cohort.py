"""Kelvin：回首本路程嘅馬（之前縮程熱身）有冇真係跑差？v5 校準，有／冇 D1 兩個版本嘅實際 vs 預測。"""
import sys, numpy as np
sys.argv = [sys.argv[0], sys.argv[1], "/dev/null"]
ns = {"__name__": "bp"}
exec(open("build_proven.py").read().split("def strip_d1")[0], ns)
rows, F, season, D1_BETA = ns["rows"], ns["F"], ns["season"], ns["D1_BETA"]
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_replay_compare_v5 as v5
def raws(x, strip):
    r = np.array([h["raw"] for h in x["horses"]])
    if strip:
        d1 = F[id(x)][:, 0]; r = r - D1_BETA * (d1 - d1.mean())
    return r
dev = [x for x in rows if "2020-09-01" <= x["date"] <= "2024-07-31"]
for strip in (False, True):
    def fit(races):
        X, Y = [], []
        for x in races:
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = raws(x, strip)[keep]; rc = r - r.mean()
            X.append(np.column_stack([rc, np.full(len(rc), v5.field_logit(len(rc)))])); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        from sklearn.linear_model import LogisticRegression
        m = LogisticRegression(C=1e6, max_iter=5000).fit(np.vstack(X), Y); return m.intercept_[0], m.coef_[0]
    a, (b, g) = fit(dev)
    out = {}
    for x in rows:
        if x["date"] < "2020-09-01": continue
        w = "dev" if x["date"] <= "2024-07-31" else "holdout"
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
        r = raws(x, strip)[keep]; rc = r - r.mean(); n = len(keep)
        p = 1 / (1 + np.exp(-(a + b * rc + g * v5.field_logit(n))))
        rank = (-r).argsort().argsort() + 1
        for j, i in enumerate(keep):
            d1, unp = F[id(x)][i, 0], F[id(x)][i, 1]
            if not d1: continue
            grp = "增程≥400、回到上過名嘅路程" if not unp else "增程≥400、今仗路程未上過名"
            out.setdefault((grp, w), []).append((int(x["horses"][i]["pos"] <= 3), p[j], rank[j], n))
    print("=== D1", "剷走" if strip else "保留（live）")
    for k in sorted(out):
        v = np.array(out[k], dtype=float)
        print(f"{k[0]}｜{k[1]}｜n {len(v)}｜實際入頭三 {100*v[:,0].mean():.1f}%｜模型預測 {100*v[:,1].mean():.1f}%｜差 {100*(v[:,0]-v[:,1]).mean():+.1f}pp｜模型平均排第 {v[:,2].mean():.1f}／{v[:,3].mean():.1f}")
