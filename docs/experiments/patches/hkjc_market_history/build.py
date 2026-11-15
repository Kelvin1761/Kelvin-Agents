"""EXP-20261115-07：HKJC 市場歷史特徵（Kelvin 2026-11-15 明文批准「測 可以睇下有咩訊號」）。

只用**之前賽事**嘅 HKJC 最終獨贏賠率（賽前已知；今仗賠率唔用）。三個預先登記候選（Holm 3）：
  A  上仗 log 賠率
  B  近三仗平均 log 賠率
  C  上仗跑贏市場：上仗市場排名 − 上仗實際名次（正 = 跑得好過市場預期），按上仗出賽數 /(F−1) 標準化
冇上仗嘅馬：特徵 = 場均 + 指示變數。β 用 logistic（入頭三，raw 放大令佢唔受罰）由之前所有季 walk-forward fit，holdout 用全 dev。
用法：python3 build.py <base.jsonl> <outdir>
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def history():
    import hkjc_history_replay_pit as p
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna() & df["Odds"].notna()].copy()
    df["d"] = df["Date"].astype(str).str[:10]
    # 場內市場排名同出賽數
    df["mrank"] = df.groupby(["d", "RaceNo"])["Odds"].rank(method="average")
    df["F"] = df.groupby(["d", "RaceNo"])["Odds"].transform("count")
    df = df.sort_values(["d", "RaceNo"])
    past = defaultdict(list)          # HorseID -> [(d, logodds, beat)]
    feat = {}
    for r in df.itertuples():
        h = [x for x in past[r.HorseID] if x[0] < r.d]
        k = (r.d, int(r.RaceNo), int(r.Rank))
        if h:
            feat.setdefault(k, []).append((h[-1][1], float(np.mean([x[1] for x in h[-3:]])), h[-1][2]))
        else:
            feat.setdefault(k, []).append(None)
        beat = (r.mrank - float(r.Rank)) / max(r.F - 1, 1)
        past[r.HorseID].append((r.d, float(np.log(r.Odds)), float(beat)))
    return feat


def race_feats(x, feat, which):
    hs = x["horses"]
    vals, miss = [], []
    for h in hs:
        f = feat.get((x["date"], x["race"], h["pos"])) if h["pos"] else None
        f = f[0] if f and len(f) == 1 else None
        v = None if f is None else f[{"A": 0, "B": 1, "C": 2}[which]]
        vals.append(v)
        miss.append(v is None)
    obs = [v for v in vals if v is not None]
    fill = float(np.mean(obs)) if obs else 0.0
    v = np.array([fill if a is None else a for a in vals], float)
    m = np.array(miss, float)
    return np.column_stack([v - v.mean(), m - m.mean()])


def fit(races, feat, which):
    R, Z, Y = [], [], []
    for x in races:
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
        r = np.array([h["raw"] for h in x["horses"]], float)
        z = race_feats(x, feat, which)
        R.append((r - r.mean())[keep]); Z.append(z[keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
    X = np.column_stack([np.concatenate(R) * 10, np.vstack(Z)])
    b = LogisticRegression(C=1e6, max_iter=5000).fit(X, Y).coef_[0]
    return b[1:] / (b[0] * 10)


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    out = Path(sys.argv[2])
    feat = history()
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    for which in "ABC":
        betas = {s: fit([x for t in by if t < min(s, 2024) for x in by[t]], feat, which) for s in sorted(by) if s > 2019}
        with open(out / f"market_{which}.jsonl", "w") as f:
            for x in rows:
                b = betas.get(season(x["date"]))
                y = dict(x, arm=f"market_{which}")
                if b is not None:
                    add = race_feats(x, feat, which) @ b
                    y["horses"] = [dict(h, raw=round(h["raw"] + float(a), 4)) for h, a in zip(x["horses"], add)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")
        print(which, {s: np.round(b, 2).tolist() for s, b in betas.items() if s <= 2024})


if __name__ == "__main__":
    main()
