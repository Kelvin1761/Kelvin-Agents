"""EXP-20261123-04 預先登記（Kelvin 2026-11-23「J3 要做到唔會擠走今日頭二入位嘅馬先上」；寫喺建任何 arm 之前）
同一組 J3 17 個訊號（`scratch/joint_plus/X_live.pkl`，場內置中），base = live（base_live_20261122）。四個 arm，逐季 walk-forward：
  J3w   目標改「頭二 Plackett–Luce」（邊匹第一、邊匹第二），條件 logit，L2 同 J3（Σloss + ‖w‖²/(2·0.1)）
  J3t2  目標改「入頭二」（pos ≤ 2），logistic L2 C=0.1，其他同 J3
  J3h   J3 Δ × 0.5（半力度）
  J3p   J3 Δ，再俾 base 頭二嘅馬 +1.0 raw（保護：要被超過 >1 分先會擠出頭二）
揀法（寫死）：v5.2 dev PASS 而且 dev「頭二入頭三總匹數差」≥ 0 → 開 holdout（J3 家族 holdout 已睇過一次，披露）；
holdout 都要 v5.2 PASS 而且頭二入頭三 ≥ 0。最後 Kelvin 條件：11-22 舊版頭二入位嘅 14 匹，一匹都唔准跌出頭二。
11-22 唔參與揀 arm、唔調任何參數。
用法：python3 build_j3_top2.py <base_live> <jl_J3> <X_live.pkl> <out_prefix>
"""
import json, pickle, sys
from collections import defaultdict
import numpy as np
from scipy.optimize import minimize
from sklearn.linear_model import LogisticRegression
base_p, j3_p, x_p, out = sys.argv[1:5]
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
rows = [x for x in map(json.loads, open(base_p)) if "horses" in x]
J3 = {(x["meeting"], x["race"]): {h["n"]: h["raw"] for h in x["horses"]} for x in map(json.loads, open(j3_p)) if "horses" in x}
X = pickle.load(open(x_p, "rb"))
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
def design(races, target):
    R, Z, Y, G = [], [], [], []
    for gi, x in enumerate(races):
        k = (x["meeting"], x["race"])
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
        r = np.array([h["raw"] for h in x["horses"]])
        R.append((r - r.mean())[keep]); Z.append(X[k][keep])
        Y += [x["horses"][i]["pos"] for i in keep]; G += [gi] * len(keep)
    return np.concatenate(R), np.vstack(Z), np.array(Y), np.array(G)
def fit_t2(races):
    R, Z, Y, _ = design(races, None); sd = Z.std(0); sd[sd == 0] = 1; rs = R.std()
    c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / rs, Z / sd]), (Y <= 2).astype(int)).coef_[0]
    return (c[1:] / sd) / (c[0] / rs)
def fit_w(races):
    R, Z, Y, G = design(races, None); sd = Z.std(0); sd[sd == 0] = 1; rs = R.std()
    A = np.column_stack([R / rs, Z / sd]); groups = [np.where(G == g)[0] for g in np.unique(G)]
    groups = [g for g in groups if (Y[g] == 1).sum() == 1 and (Y[g] == 2).sum() >= 1]
    def f(w):
        L, gr = 0.0, np.zeros_like(w)
        for g in groups:
            a = A[g]; z = a @ w; z = z - z.max(); e = np.exp(z); s = e.sum(); p = e / s
            i1 = np.where(Y[g] == 1)[0][0]; i2 = np.where(Y[g] == 2)[0][0]
            L -= np.log(p[i1]); gr -= a[i1] - p @ a
            e2 = e.copy(); e2[i1] = 0; s2 = e2.sum(); p2 = e2 / s2
            L -= np.log(p2[i2]); gr -= a[i2] - p2 @ a
        return L + (w @ w) / 0.2, gr + w / 0.1
    w0 = np.zeros(A.shape[1]); w0[0] = 1.0
    w = minimize(f, w0, jac=True, method="L-BFGS-B").x
    return (w[1:] / sd) / (w[0] / rs)
for arm in ("J3w", "J3t2", "J3h", "J3p"):
    betas = {}
    if arm in ("J3w", "J3t2"):
        for s in sorted(by):
            if s < 2020: continue
            tr = [x for t in by if 2019 <= t < s for x in by[t]]
            betas[s] = fit_w(tr) if arm == "J3w" else fit_t2(tr)
        print(arm, {s: [round(float(v), 2) for v in b[:4]] + ["…"] for s, b in betas.items()}, flush=True)
    with open(f"{out}_{arm}.jsonl", "w") as fh:
        for x in rows:
            k = (x["meeting"], x["race"]); s = season(x["date"]); r = np.array([h["raw"] for h in x["horses"]])
            if arm in ("J3w", "J3t2"):
                if s not in betas: fh.write(json.dumps(x, ensure_ascii=False) + "\n"); continue
                new = r + X[k] @ betas[s]
            else:
                jd = np.array([J3[k].get(h["n"], h["raw"]) - h["raw"] for h in x["horses"]]) if k in J3 else np.zeros(len(r))
                if arm == "J3h": new = r + 0.5 * jd
                else:
                    top2 = set(x["picks"][:2]); new = r + jd + np.array([1.0 if h["n"] in top2 else 0.0 for h in x["horses"]])
            y = dict(x, arm=arm, horses=[dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)])
            y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            fh.write(json.dumps(y, ensure_ascii=False) + "\n")
    if arm in ("J3w", "J3t2"):
        pickle.dump(betas, open(f"{out}_{arm}_betas.pkl", "wb"))
