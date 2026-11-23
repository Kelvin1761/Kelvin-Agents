"""EXP-20261123-14 預先登記（Kelvin 2026-11-23「仲有冇咩改善初出馬表現嘅嘢」）。寫喺跑之前；尺 v5.2；base = SW＋DT（EXP-20261123-13 上線版）。

觸發（SW base 診斷，EXP-20261123-13）：模型排頭三嘅初出馬實際入頭三 49.4% vs 預計 35.7%（89 匹）；排第 4 之後 15.8% vs 16.5% →
初出馬之間分數拉得太窄（模型唔敢將好嘅初出馬排高）。
DW  特徵（場內置中）：deb = 係咪初出馬；debx = 初出馬 ×（raw − 場均）÷10。線性 L2 C=0.1、每季 walk-forward β（同 J3），加落 raw。
    debx β > 0 = 初出馬分數要拉闊；deb β = 初出馬整體加／減。
判：全期 v5.2 dev PASS ＋ 頭二入頭三 Δ ≥ 0；holdout 照判（SW 嘅 holdout 診斷用過，唔完全獨立）；六季有初出馬嘅場報；11-22 否決。
用法：python3 build_debut_spread.py <SW_DT.jsonl> <out_prefix>
"""
import json
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    feats = {}
    for x in rows:
        r = np.array([h["raw"] for h in x["horses"]]); d = np.array([float(bool(h.get("debut"))) for h in x["horses"]])
        m = np.column_stack([d, d * (r - r.mean()) / 10.0])
        feats[(x["date"], x["race"])] = m - m.mean(axis=0)
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    models = {}
    for s in sorted(by):
        if s < 2020:
            continue
        R, Z, Y = [], [], []
        for x in (x for t in by if 2019 <= t < s for x in by[t]):
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = np.array([h["raw"] for h in x["horses"]])
            R.append((r - r.mean())[keep]); Z.append(feats[(x["date"], x["race"])][keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        R, Z, Y = np.concatenate(R), np.vstack(Z), np.array(Y)
        sd = Z.std(axis=0); sd[sd == 0] = 1; rs = R.std()
        c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([R / rs, Z / sd]), Y).coef_[0]
        models[s] = (c[1:] / sd) / (c[0] / rs)
    print("DW", {s: [round(float(b), 2) for b in m] for s, m in models.items()}, flush=True)
    with open(f"{sys.argv[2]}_DW.jsonl", "w") as f:
        for x in rows:
            s = season(x["date"]); y = dict(x, arm="debut_DW")
            if s in models:
                new = np.array([h["raw"] for h in x["horses"]]) + feats[(x["date"], x["race"])] @ models[s]
                y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
