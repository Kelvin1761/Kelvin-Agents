"""方向 (a) 候選（預先登記，diag.py 揀；Kelvin：負磅／評分效應應該係通用，唔好淨係一二班）：
  A1  所有讓賽（一至五班）raw += β·(評分 − 場均)/10，一個 β。
  A3  同上但分三組 β：一二班／三班／四五班。
分級賽、新馬、冇評分唔郁。同一場同一班 → 「班內位置」同「場內相對」只差常數，排名上等價，所以只用場內相對。
β 逐季 walk-forward（2019/20 起），評分 = 排位表（賽前已知）。用法：python3 build.py <I1.jsonl> <out_prefix>
"""
import json
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

from diag import TOP, load_cards, season

GROUP = {"第一班": 0, "第二班": 0, "第三班": 1, "第四班": 2, "第五班": 2}
card, rcls = load_cards()


def feats(x, arm):
    out = np.zeros((len(x["horses"]), 3))
    c = rcls.get((x["date"], x["race"]), "")
    if c not in TOP:
        return out
    rt = np.array([(card.get((x["date"], x["race"], int(h["n"]))) or {}).get("r") or np.nan for h in x["horses"]], dtype=float)
    if np.isnan(rt).sum() > len(rt) / 2:
        return out
    rt = np.where(np.isnan(rt), np.nanmean(rt), rt)
    out[:, 0 if arm == "A1" else GROUP[c]] = (rt - rt.mean()) / 10
    return out


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    for arm in ("A1", "A3"):
        F = {id(x): feats(x, arm) for x in rows}

        def fit(races):
            R, Z, Y = [], [], []
            for x in races:
                keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
                r = np.array([h["raw"] for h in x["horses"]]); R.append((r - r.mean())[keep]); Z.append(F[id(x)][keep])
                Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            R, Z = np.concatenate(R), np.vstack(Z); sd = Z.std(axis=0); use = sd > 0; sd[~use] = 1
            c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z[:, use] / sd[use]]), Y).coef_[0]
            beta = np.zeros(3); beta[use] = (c[1:] / sd[use]) / (c[0] / R.std()); return beta
        betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020}
        print(arm, {s: np.round(v, 2).tolist() for s, v in betas.items()}, flush=True)
        with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
            for x in rows:
                bb = betas.get(season(x["date"])); y = dict(x, arm=f"cp_{arm}")
                if bb is not None:
                    add = F[id(x)] @ bb
                    if np.any(add):
                        y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                        y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
