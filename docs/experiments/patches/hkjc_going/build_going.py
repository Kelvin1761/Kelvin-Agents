"""EXP-20261120-02 預先登記（Kelvin 2026-11-20「先做場地實驗」；Holm 家族 1，只得一個 arm）。
寫之前已睇：diag_going.py —— 草地黏地「冇經驗」dev −1.8／ho −1.0、「上過名」dev +2.4／ho +2.0，CI 全跨零；其他分組兩窗唔一致。
  G1  今仗係黏地（草地）或濕地（泥地）先生效：兩個指標「同場地類型同狀況上過名」「同場地類型同狀況冇跑過」，
      β 逐季 walk-forward（只用之前季）聯合 fit，場內置中；好地場次零改動。
判：hkjc_replay_compare_v4.py；dev 唔過唔開 holdout。用法：python3 build_going.py <base> <out.jsonl>
"""
import json, os, sys
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import diag_going as d  # noqa: E402

hist, race = d.build()
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
F = {}
for x in rows:
    g, awt, code = race.get((x["date"], x["race"]), (None, None, {}))
    v = []
    for h in x["horses"]:
        c = code.get(str(h["n"]))
        if g in (None, "好") or not c or c not in hist:
            v.append([0.0, 0.0]); continue
        f = d.features(hist[c], x["date"], awt, g)
        v.append([float(f["off_pl"] > 0), float(f["n_off"] == 0)])
    F[id(x)] = np.array(v)
print("上過名／冇經驗 馬次", np.sum([F[id(x)].sum(0) for x in rows], axis=0).astype(int).tolist(), flush=True)
by = defaultdict(list)
for x in rows: by[d.season(x["date"])].append(x)
def fit(races):
    R, Z, Y = [], [], []
    for x in races:
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
        r = np.array([h["raw"] for h in x["horses"]])
        R.append((r - r.mean())[keep]); Z.append(F[id(x)][keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
    R, Z = np.concatenate(R), np.concatenate(Z)
    c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z]), Y).coef_[0]
    return c[1:] / (c[0] / R.std())
betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020}
print("β（上過名, 冇經驗）", {s: [round(float(u), 2) for u in v] for s, v in betas.items()}, flush=True)
with open(sys.argv[2], "w") as f:
    for x in rows:
        y = dict(x, arm="going_G1"); bt = betas.get(d.season(x["date"]))
        if bt is not None and F[id(x)].any():
            add = F[id(x)] @ bt; add = add - add.mean()
            y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
            y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
        f.write(json.dumps(y, ensure_ascii=False) + "\n")
