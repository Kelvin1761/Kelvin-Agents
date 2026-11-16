"""EXP-20261116-07 候選（預先登記，拆解見 wr_split）：
  HR  一二班（讓賽）raw += β_r1·(評分 − 場均)/10；分級賽 raw += β_w·(負磅 − 場均)/10 + β_rg·(評分 − 場均)/10；其他班唔郁。
  HG  只做分級賽部分。
β 逐季 walk-forward（2019/20 起）。評分／負磅 = 排位表（賽前已知）。用法：python3 build_hr.py <base.jsonl> <out_prefix>
"""
import json, re, sys, glob
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
M = "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/replay_all"
card, rcls = {}, {}
for f in glob.glob(f"{M}/*/*排位表.md"):
    t = open(f, encoding="utf-8").read()
    d = re.search(r"日期:\s*(\S+)", t).group(1); rn = int(re.search(r"場次:\s*第(\d+)場", t).group(1))
    rcls[(d, rn)] = (re.search(r"班次:\s*(\S+)", t) or [None, ""])[1]
    for b in re.split(r"\n(?=馬號:)", t)[1:]:
        g = lambda k: (re.search(rf"{k}:\s*(-?\d+)", b) or [None, None])[1]
        if g("馬號"):
            card[(d, rn, int(g("馬號")))] = (g("評分"), g("負磅"))
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
def kind(x):
    c = rcls.get((x["date"], x["race"]), "")
    return "H12" if c in ("第一班", "第二班") else ("G" if "級賽" in c else None)
def feats(x, arm):
    k = kind(x)
    out = np.zeros((len(x["horses"]), 3))
    if k is None or (arm == "HG" and k != "G"):
        return out
    rt, w = [], []
    for h in x["horses"]:
        c = card.get((x["date"], x["race"], int(h["n"])))
        rt.append(float(c[0]) if c and c[0] is not None else np.nan); w.append(float(c[1]) if c and c[1] is not None else np.nan)
    rt, w = np.array(rt), np.array(w)
    if np.isnan(rt).all() or np.isnan(w).all():
        return out
    rt = np.where(np.isnan(rt), np.nanmean(rt), rt); w = np.where(np.isnan(w), np.nanmean(w), w)
    rt = (rt - rt.mean()) / 10; w = (w - w.mean()) / 10
    if k == "H12": out[:, 0] = rt
    else: out[:, 1] = w; out[:, 2] = rt
    return out
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
for arm in ("HR", "HG"):
    F = {id(x): feats(x, arm) for x in rows}
    def fit(races):
        R, Z, Y = [], [], []
        for x in races:
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = np.array([h["raw"] for h in x["horses"]]); R.append((r - r.mean())[keep]); Z.append(F[id(x)][keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        R, Z = np.concatenate(R), np.vstack(Z); sd = Z.std(axis=0); use = sd > 0; sd[~use] = 1
        c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z[:, use] / sd[use]]), Y).coef_[0]
        beta = np.zeros(3); beta[use] = (c[1:] / sd[use]) / (c[0] / R.std()); return beta
    betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020}
    print(arm, {s: np.round(v, 2).tolist() for s, v in betas.items()})
    with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
        for x in rows:
            bb = betas.get(season(x["date"])); y = dict(x, arm=f"wr_{arm}")
            if bb is not None:
                add = F[id(x)] @ bb
                if np.any(add):
                    y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
