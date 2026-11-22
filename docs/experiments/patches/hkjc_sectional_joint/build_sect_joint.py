"""EXP-20261123-02 預先登記（Kelvin 2026-11-23「測 L400 同其他段速改動一齊試」；回放尺 v5.1；Holm 家族 2）
單獨過唔到閘、但 holdout 確認係真訊號嘅段速／場地四樣一齊入（細訊號單獨量唔到，EXP-20261122-32）：
  L1      L400 用 pit_sections 標準化（EXP-20261123-01 嘅 L1 回放 raw Δ，引擎重跑；單獨 dev −0.00010 CI 跨零）
  A1      泥地相對草地表現（泥地賽；EXP-20261114-11 篩選 dev/holdout 都過）
  A2      泥地前段對標準（泥地賽；同上）
  S3      直路 1000 往績（沙田草地 1000；同上）
base = live ＋ J3（`scratch/joint_plus/jl_J3.jsonl`，即 J3 上線後嘅模型）。
  SJ   base ＋ L1 Δ ＋ β·(A1, A2, S3)
  SJ0  base ＋ β·(A1, A2, S3)（冇 L1；用嚟睇 L1 有冇邊際貢獻）
A1／A2／S3：缺失 = 0，非該類賽事 = 0；逐季 walk-forward，線性 L2 C=0.1（同 J3），特徵按訓練季標準化，場內置中。
判：hkjc_replay_compare_v5.py（v5.1）；dev 唔過唔開 holdout；唔揀特徵、唔調 C。
用法：python3 build_sect_joint.py <jl_J3.jsonl> <l400_base.jsonl> <L1.jsonl> <feat_awt.pkl> <feat_straight.pkl> <out_prefix>
"""
import json, sys
from collections import defaultdict
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
base_p, lb_p, l1_p, fa_p, fs_p, out = sys.argv[1:7]
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
rows = [x for x in map(json.loads, open(base_p)) if "horses" in x]
def rawmap(p):
    m = {}
    for x in map(json.loads, open(p)):
        if "horses" in x:
            for h in x["horses"]: m[(x["meeting"], x["race"], h["n"])] = h["raw"]
    return m
lb, l1 = rawmap(lb_p), rawmap(l1_p)
feat = {}
for p, cols in ((fa_p, ("A1_awt_vs_turf", "A2_front_v")), (fs_p, ("S3_straight_pct",))):
    df = pd.read_pickle(p)
    for r in df.itertuples():
        k = (r.race[0], r.race[1], r.n)
        for c in cols:
            v = getattr(r, c)
            if v is not None and not pd.isna(v): feat.setdefault(k, {})[c] = float(v)
NAMES = ["A1_awt_vs_turf", "A2_front_v", "S3_straight_pct"]
X, D = {}, {}
miss = 0
for x in rows:
    m = np.array([[feat.get((x["meeting"], x["race"], h["n"]), {}).get(c, 0.0) for c in NAMES] for h in x["horses"]])
    X[id(x)] = m - m.mean(0)
    d = []
    for h in x["horses"]:
        k = (x["meeting"], x["race"], h["n"])
        if k in lb and k in l1: d.append(l1[k] - lb[k])
        else: d.append(0.0); miss += 1
    d = np.array(d); D[id(x)] = d - d.mean()
print("L1 Δ 搵唔到", miss, "；特徵非零", {c: int(sum((np.abs(X[id(x)][:, j]) > 1e-12).sum() for x in rows)) for j, c in enumerate(NAMES)}, flush=True)
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
for arm, use_l1 in (("SJ", True), ("SJ0", False)):
    def braw(x):
        r = np.array([h["raw"] for h in x["horses"]])
        return r + (D[id(x)] if use_l1 else 0.0)
    models = {}
    for s in sorted(by):
        if s < 2020: continue
        R, Z, Y = [], [], []
        for t in by:
            if not (2019 <= t < s): continue
            for x in by[t]:
                keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
                r = braw(x); R.append((r - r.mean())[keep]); Z.append(X[id(x)][keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        R, Z, Y = np.concatenate(R), np.vstack(Z), np.array(Y)
        sd = Z.std(0); sd[sd == 0] = 1; rs = R.std()
        c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / rs, Z / sd]), Y).coef_[0]
        models[s] = (c[1:] / sd) / (c[0] / rs)
    print(arm, {s: [round(float(v), 2) for v in b] for s, b in models.items()}, flush=True)
    with open(f"{out}_{arm}.jsonl", "w") as f:
        for x in rows:
            s = season(x["date"]); y = dict(x, arm=f"sect_{arm}")
            if s in models:
                new = braw(x) + X[id(x)] @ models[s]
                y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
