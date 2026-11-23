"""EXP-20261124-14 預先登記（Kelvin 2026-11-24「個 model 仲有冇嘢 refine」→ 成套維度權重重新 fit）。寫喺跑之前；尺 v5.2。
base = 最新 live harness 回放（表現數字、初出馬練馬師、直路、返首本）。
維度（非初出馬）：stability、trainer_signal、race_shape、horse_health、form_line、class_advantage（現行 0）；
唔郁：sectional（已由表現數字取代）、trackwork、distance_fit（centred）、初出馬（DEBUT 權重）、全部後置組件。
offset = raw − Σ 現行權重 × 維度分（= 後置組件＋唔郁嘅部分）；特徵 = 維度分 × 非初出（場內置中）。
logistic（offset 同特徵一齊標準化，L2 C=0.1，同 J3）；每季 walk-forward（季 s 只用 2019 ≤ 季 < s）；
新權重 = β_d ÷ β_offset；新 raw = offset + Σ 新權重 × 維度分（初出馬維度項 = 0 → 等於現行）。
判：全期 dev／holdout v5.2 PASS ＋ 兩窗頭二入頭三 Δ ≥ 0；11-22 否決。另印每季新權重，睇穩唔穩。
用法：python3 build_weight_refit.py <base.jsonl> <out_prefix>
"""
import json
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

DIMS = ["stability", "trainer_signal", "race_shape", "horse_health", "form_line", "class_advantage"]
CUR = {"stability": 0.2451, "trainer_signal": 0.3296, "race_shape": 0.1925, "horse_health": 0.0344,
       "form_line": 0.0699, "class_advantage": 0.0}


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    feats = {}
    for x in rows:
        nd = np.array([0.0 if h.get("debut") else 1.0 for h in x["horses"]])
        M = np.array([[float((h.get("m") or {}).get(d, 60.0) or 60.0) for d in DIMS] for h in x["horses"]]) * nd[:, None]
        raw = np.array([h["raw"] for h in x["horses"]])
        off = raw - M @ np.array([CUR[d] for d in DIMS])
        feats[(x["meeting"], x["race"])] = (off - off.mean(), M - M.mean(axis=0))
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    models = {}
    for s in sorted(by):
        if s < 2020:
            continue
        O, Z, Y = [], [], []
        for x in (x for t in by if 2019 <= t < s for x in by[t]):
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            o, m = feats[(x["meeting"], x["race"])]
            O.append(o[keep]); Z.append(m[keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        O, Z, Y = np.concatenate(O), np.vstack(Z), np.array(Y)
        os_, sd = O.std(), Z.std(axis=0); sd[sd == 0] = 1
        c = LogisticRegression(C=0.1, max_iter=20000).fit(np.column_stack([O / os_, Z / sd]), Y).coef_[0]
        models[s] = (c[1:] / sd) / (c[0] / os_)
    for s, w in models.items():
        print(s, {d: round(float(v), 4) for d, v in zip(DIMS, w)}, flush=True)
    with open(f"{sys.argv[2]}_WR.jsonl", "w") as f:
        for x in rows:
            s = season(x["date"]); y = dict(x, arm="weight_refit")
            if s in models:
                nd = np.array([0.0 if h.get("debut") else 1.0 for h in x["horses"]])
                M = np.array([[float((h.get("m") or {}).get(d, 60.0) or 60.0) for d in DIMS] for h in x["horses"]]) * nd[:, None]
                raw = np.array([h["raw"] for h in x["horses"]])
                new = raw - M @ np.array([CUR[d] for d in DIMS]) + M @ models[s]
                y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
