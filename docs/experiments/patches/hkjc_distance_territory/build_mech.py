"""EXP-20261122-27 預先登記（Kelvin 2026-11-22「返首本都要扣分唔合理」；回放尺 v5；Holm 家族 2）
診斷（v5 校準）：大幅增程馬只係段速分高（頭三分一）先被高估（dev −3.2、holdout −6.5pp），段速低嘅冇事 →
機制假設：上仗短程嘅段速優勢搬去長程用唔到；一律扣 0.93 係錯嘅修法。
  M1  剷走 D1，改為 β·D1·(段速維度 − 場均)  —— 只打折大幅增程馬嘅段速優勢；段速唔高嘅唔扣
  M2  保留 D1，加 β·D1·(段速維度 − 場均)
D1 = 今仗 − 上仗 ≥ 400（同 live）。β 逐季 walk-forward（只用之前季）、場內置中。判：v5；dev 唔過唔開 holdout；唔准換切法救。
"""
import sys, json, numpy as np
from collections import defaultdict
from sklearn.linear_model import LogisticRegression
src = open("build_prep.py").read().split("nd1 = nprep = 0")[0]
out_prefix = sys.argv[2]; sys.argv = [sys.argv[0], sys.argv[1], "/dev/null"]
ns = {"__name__": "bp"}; exec(src, ns)
rows, runs, code_of, D1_BETA = ns["rows"], ns["runs"], ns["code_of"], ns["D1_BETA"]
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
D1 = {}; INT = {}
for x in rows:
    dist = x.get("distance"); d1 = []
    for h in x["horses"]:
        c = code_of.get((x["date"], x["race"], str(h["n"])))
        prev = [t for t in runs.get(c, []) if t[0] < x["date"] and t[1]]
        d1.append(float(bool(prev and dist and dist - prev[-1][1] >= 400)))
    d1 = np.array(d1); sec = np.array([h["m"]["sectional"] for h in x["horses"]])
    D1[id(x)] = d1; INT[id(x)] = d1 * (sec - sec.mean())
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
for arm, strip in (("M1", True), ("M2", False)):
    def base(x):
        r = np.array([h["raw"] for h in x["horses"]])
        if strip: d = D1[id(x)]; r = r - D1_BETA * (d - d.mean())
        return r
    def fit(races):
        R, Z, Y = [], [], []
        for x in races:
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = base(x); z = INT[id(x)]
            R.append((r - r.mean())[keep]); Z.append((z - z.mean())[keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        R, Z = np.concatenate(R), np.concatenate(Z)
        c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z]), Y).coef_[0]
        return c[1] / (c[0] / R.std())
    betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020}
    print(arm, {s: round(float(v), 3) for s, v in betas.items()}, flush=True)
    with open(f"{out_prefix}_{arm}.jsonl", "w") as f:
        for x in rows:
            bb = betas.get(season(x["date"])); y = dict(x, arm=f"mech_{arm}")
            if bb is not None:
                z = INT[id(x)] * bb; new = base(x) + (z - z.mean())
                y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
