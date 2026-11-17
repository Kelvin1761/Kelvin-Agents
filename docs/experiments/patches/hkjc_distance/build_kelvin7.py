"""EXP-20261117-06 預先登記（Kelvin 2026-11-17 七個標籤構思；診斷 diag_kelvin7.py）：Holm 家族 3
  K1  初落呢班＋同程上過名
  K2  轉場：谷草→田草、田草→谷草、初次田草、初次泥地（4 個特徵各自 β）
  K3  騎師同場揀馬：上仗騎師（騎過 ≥3 次）今場騎另一匹 → 被棄；被揀
β 逐季 walk-forward（2019/20 起只用之前季），標準化＋newton-cg，場內置中（同 build_distance.py）。base = dist_D1（live）。
用法：python3 build_kelvin7.py <dist_D1.jsonl> <kelvin7_feats.pkl> <out_prefix>
"""
import json
import pickle
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

ARMS = {
    "K1": ["3 初落呢班＋同程上過名"],
    "K2": ["7 谷草→田草", "7 田草→谷草", "7 初次田草", "7 初次泥地"],
    "K3": ["4b 上仗騎師（騎過≥3次）今場同場騎另一匹 → 被棄", "4b 被揀（騎師棄咗佢上仗騎、騎過≥3次嗰匹）"],
}


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    feats = pickle.load(open(sys.argv[2], "rb"))
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    for arm, keys in ARMS.items():
        F = {id(x): np.array([[float(bool((feats.get((x["date"], x["race"], h["pos"])) or {}).get(k))) if h["pos"] else 0.0
                               for k in keys] for h in x["horses"]]) for x in rows}

        def fit(races):
            R, Z, Y = [], [], []
            for x in races:
                keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
                r = np.array([h["raw"] for h in x["horses"]])
                R.append((r - r.mean())[keep]); Z.append(F[id(x)][keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            R, Z = np.concatenate(R), np.vstack(Z)
            sd = Z.std(axis=0); sd[sd == 0] = 1
            c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z / sd]), Y).coef_[0]
            return (c[1:] / sd) / (c[0] / R.std())
        betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020}
        print(arm, {s: [round(float(b), 2) for b in v] for s, v in betas.items()}, flush=True)
        with open(f"{sys.argv[3]}_{arm}.jsonl", "w") as f:
            for x in rows:
                bb = betas.get(season(x["date"]))
                y = dict(x, arm=f"kelvin7_{arm}")
                if bb is not None:
                    add = F[id(x)] @ bb
                    add = add - add.mean()
                    y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
