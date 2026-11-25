"""EXP-20261126-22 預先登記（Kelvin 2026-11-26「go ahead on all 3」第 1 項：市場啱模型錯嘅失手研究；寫喺跑之前；尺 v5.2；Holm 家族 2）。
來源：hk_resid_screen.py（v5 校準＋walk-forward，base e5_E5）：狀態與穩定性 z≥1 dev −2.6／ho −1.3、評分與經驗 z≥1 dev −2.3／ho −1.6，
兩窗 CI 都 <0；EXP-20261125-06 §6 in-sample 同方向。**披露：holdout 殘差已睇過 → holdout 唔係獨立確認。**
唔郁騎練（Kelvin：唔想再加潘頓分）。
  T1  指標 1[場內 z(stability) ≥ 1]
  T2  指標 1[場內 z(class_advantage) ≥ 1]（呢維度權重 0、只作參考；指標係新項）
  β 逐季 walk-forward（只用之前季；raw 標準化＋指標 LogisticRegression，同 J3／U1 做法），場內置中加落 raw。
判：v5.2 dev PASS 先開 holdout；唔調門檻 1.0。用法：python3 build_top_tail.py <base> <out_prefix>
"""
import json, sys
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
ARMS = {"T1": "stability", "T2": "class_advantage"}
def ind(x, key):
    v = np.array([h["m"].get(key, 60) for h in x["horses"]], float)
    sd = v.std()
    return ((v - v.mean()) / sd >= 1).astype(float) if sd > 0 else np.zeros(len(v))
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
for arm, key in ARMS.items():
    F = {id(x): ind(x, key) for x in rows}
    def fit(races):
        R, Z, Y = [], [], []
        for x in races:
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = np.array([h["raw"] for h in x["horses"]])
            R.append((r - r.mean())[keep]); Z.append(F[id(x)][keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        R, Z = np.concatenate(R), np.concatenate(Z)
        c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z]), Y).coef_[0]
        return c[1] / (c[0] / R.std())
    betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020}
    print(arm, key, "覆蓋", int(sum(v.sum() for v in F.values())), "β", {s: round(float(v), 2) for s, v in betas.items()}, flush=True)
    with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
        for x in rows:
            y = dict(x, arm=f"top_tail_{arm}"); bt = betas.get(season(x["date"]))
            if bt is not None and F[id(x)].any():
                add = F[id(x)] * bt; add = add - add.mean()
                y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
