"""EXP-20261115-04：HKJC 訊號互動項（預先登記，walk-forward）。

候選 raw' = raw + Σ β_j·z_j，z_j = (leaf − 場均) × 情境，情境 = {短途 ≤1200、長途 ≥1800、泥地、跑馬地}；
β 用 L2 logistic（入頭三，特徵場內置中、raw 置中做 offset 項一齊估）由**之前所有季**（2019/20 起）fit，逐季 walk-forward；
holdout／terminal 用全 dev（2019/20–2023/24）fit。β 乘返 raw 嘅尺度（除以 raw 係數）先加。
用法：python3 build.py <base.jsonl> <out.jsonl> [--C 0.05] [--level leaf|dim]（dim = 九個維度分 × 情境）
"""
import json
import sys

import numpy as np
from sklearn.linear_model import LogisticRegression

LEAVES = ["form_score", "speed_score", "class_score", "jockey_score", "trainer_score", "draw_score", "distance_score",
          "track_going_score", "weight_score", "consistency_score", "risk_score", "formline_strength_score",
          "margin_trend_score", "same_distance_signal_score", "trackwork_trend_score", "race_shape_context_score"]


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def ctx(x):
    return np.array([x["distance"] <= 1200, x["distance"] >= 1800, bool(x["awt"]), x["venue"] == "跑馬地"], float)


DIMS = ["stability", "trainer_signal", "sectional", "race_shape", "horse_health", "trackwork", "distance_fit", "form_line", "class_advantage"]
LEVEL = "leaf"


def feats(x):
    hs = x["horses"]
    if LEVEL == "dim":
        F = np.array([[h["m"].get(k, 60.0) for k in DIMS] for h in hs], float)
    else:
        F = np.array([[h["f"].get(k, 60.0) for k in LEAVES] for h in hs], float)
    F = (F - F.mean(0)) / 10.0
    r = np.array([h["raw"] for h in hs], float)
    Z = np.einsum("ij,k->ijk", F, ctx(x)).reshape(len(hs), -1)
    return r - r.mean(), Z


def fit(races, C):
    R, Z, Y = [], [], []
    for x in races:
        r, z = feats(x)
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
        R.append(r[keep]); Z.append(z[keep]); Y.append([int(x["horses"][i]["pos"] <= 3) for i in keep])
    R, Z, Y = np.concatenate(R), np.concatenate(Z), np.concatenate(Y)
    X = np.column_stack([R * 10.0, Z])     # raw 放大 100 倍，等 L2 實際上唔罰 raw 係數（只縮互動項）
    m = LogisticRegression(C=C, max_iter=5000).fit(X, Y)
    b = m.coef_[0]
    return b[1:] / (b[0] * 10.0)     # 換返 raw 尺度


def main():
    global LEVEL
    a = sys.argv
    LEVEL = a[a.index("--level") + 1] if "--level" in a else "leaf"
    C = float(a[a.index("--C") + 1]) if "--C" in a else 0.05
    rows = [x for x in map(json.loads, open(a[1])) if "horses" in x]
    by = {}
    for x in rows:
        by.setdefault(season(x["date"]), []).append(x)
    betas = {}
    for s in sorted(by):
        tr = [x for t in by if t < min(s, 2024) for x in by[t]]
        if tr:
            betas[s] = fit(tr, C)
    with open(a[2], "w") as out:
        for x in rows:
            b = betas.get(season(x["date"]))
            y = dict(x, arm="interactions")
            if b is not None:
                _, Z = feats(x)
                add = Z @ b
                y["horses"] = [dict(h, raw=round(h["raw"] + float(d), 4)) for h, d in zip(x["horses"], add)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            out.write(json.dumps(y, ensure_ascii=False) + "\n")
    last = betas[max(betas)]
    names = [f"{l}×{c}" for l in (DIMS if LEVEL == "dim" else LEAVES) for c in ("短", "長", "泥", "谷")]
    top = sorted(zip(names, last), key=lambda t: -abs(t[1]))[:12]
    print("全 dev β（raw 分／10 leaf 分）頭 12：", ", ".join(f"{n} {v:+.2f}" for n, v in top))


if __name__ == "__main__":
    main()
