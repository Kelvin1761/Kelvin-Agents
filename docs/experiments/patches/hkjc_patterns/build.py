"""EXP-20261115-10 候選：12 個 pattern flag 合併（主檢定），逐季 walk-forward logistic（raw 放大唔受罰）；holdout 用全 dev。
--only a,b,... 只用部分 flag（ablation）。用法：python3 build.py <base.jsonl> <feat.pkl> <out.jsonl> [--only ...]"""
import json
import pickle
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

FLAGS = ["prevfav_layoff90", "prevfav_venue", "prevlong_placed", "classdrop_jchange", "stable_switch", "gear_removed",
         "gear_first", "pp_import_debut", "first_awt", "last_close_2nd_3rd", "quick_backup14", "dist_up200"]


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def race_feats(x, feat, flags):
    M = []
    for h in x["horses"]:
        f = feat.get((x["date"], x["race"], h["pos"])) if h["pos"] else None
        f = f[0] if f and len(f) == 1 else {}
        M.append([float(f.get(k, 0)) for k in flags])
    M = np.array(M, float)
    return M - M.mean(0)


def fit(races, feat, flags):
    R, Z, Y = [], [], []
    for x in races:
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
        r = np.array([h["raw"] for h in x["horses"]], float)
        R.append((r - r.mean())[keep]); Z.append(race_feats(x, feat, flags)[keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
    # 標準化＋newton-cg：舊版（raw×10＋lbfgs）喺部分季冇收斂，β 被壓到 ≈0（EXP-20261115-11 發現）
    R, Z = np.concatenate(R), np.vstack(Z)
    sr, sz = R.std(), Z.std(0)
    sz[sz == 0] = 1.0
    b = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / sr, Z / sz]), Y).coef_[0]
    return (b[1:] / sz) / (b[0] / sr)


def main():
    a = sys.argv
    flags = a[a.index("--only") + 1].split(",") if "--only" in a else FLAGS
    rows = [x for x in map(json.loads, open(a[1])) if "horses" in x]
    feat = pickle.load(open(a[2], "rb"))
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    betas = {s: fit([x for t in by if t < min(s, 2024) for x in by[t]], feat, flags) for s in sorted(by) if s > 2019}
    with open(a[3], "w") as f:
        for x in rows:
            b = betas.get(season(x["date"]))
            y = dict(x, arm="patterns")
            if b is not None:
                add = race_feats(x, feat, flags) @ b
                y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
    print("全 dev β（raw 分）：", {k: round(float(v), 2) for k, v in zip(flags, betas[2024])})
    print("逐季：", {s: np.round(v, 1).tolist() for s, v in betas.items() if s <= 2023})


if __name__ == "__main__":
    main()
