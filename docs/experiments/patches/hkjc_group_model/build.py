"""Kelvin 2026-11-16 方向 (c)：分級賽專用模型（dump 候選，base = live I1）。只郁分級賽（一／二／三級賽），其他場次不變。

預先登記（Holm 2）：
  G2a  分級賽 raw += Σγ_k·(維度_k − 場均) + β_r·(評分 − 場均)/10 + β_w·(負磅 − 場均)/10，
       γ／β 由之前季**分級賽**逐季 walk-forward 嘅 L2 logistic（入頭三）fit；raw 欄放大 100 倍令佢唔受罰；C = 0.01（標準化特徵）
  G2b  同上，C = 0.1
  維度 = dump 嘅 9 個外層維度分（m）。評分／負磅 = 排位表（賽前已知）。
點解要 L2：分級賽每季約 30 場，9 個維度＋2 個磅評項自由 fit 一定過擬合；罰項將佢哋拉向「同其他場次一樣」（γ=0）。
尺：v4 全窗（唔淨係分級賽，避免改尺）。用法：python3 build.py <I1.jsonl> <out_prefix>
"""
import glob
import json
import re
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

M = "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/replay_all"
DIMS = ["stability", "trainer_signal", "sectional", "race_shape", "horse_health", "trackwork", "distance_fit", "form_line", "class_advantage"]


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def load_cards():
    card, rcls = {}, {}
    for f in glob.glob(f"{M}/*/*排位表.md"):
        t = open(f, encoding="utf-8").read()
        d = re.search(r"日期:\s*(\S+)", t).group(1); rn = int(re.search(r"場次:\s*第(\d+)場", t).group(1))
        rcls[(d, rn)] = (re.search(r"班次:\s*(\S+)", t) or [None, ""])[1]
        for b in re.split(r"\n(?=馬號:)", t)[1:]:
            def g(k):
                m = re.search(rf"{k}:\s*(-?\d+)", b)
                return float(m.group(1)) if m else np.nan
            if not np.isnan(g("馬號")):
                card[(d, rn, int(g("馬號")))] = (g("評分"), g("負磅"))
    return card, rcls


card, rcls = load_cards()


def feats(x):
    if "級賽" not in rcls.get((x["date"], x["race"]), ""):
        return None
    hs = x["horses"]
    Z = np.array([[float(h.get("m", {}).get(k, 60.0)) for k in DIMS] for h in hs])
    cw = np.array([card.get((x["date"], x["race"], int(h["n"])), (np.nan, np.nan)) for h in hs], float)
    for j in (0, 1):
        col = cw[:, j]
        cw[:, j] = np.where(np.isnan(col), np.nanmean(col) if not np.isnan(col).all() else 0.0, col) / 10
    Z = np.column_stack([Z, cw])
    return Z - Z.mean(axis=0)


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    F = {id(x): feats(x) for x in rows}
    grp = [x for x in rows if F[id(x)] is not None]
    print("分級賽場數", len(grp), {s: sum(season(x["date"]) == s for x in grp) for s in sorted({season(x["date"]) for x in grp})})
    by = defaultdict(list)
    for x in grp:
        by[season(x["date"])].append(x)
    for arm, C in (("G2a", 0.01), ("G2b", 0.1)):
        def fit(races):
            R, Z, Y = [], [], []
            for x in races:
                keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
                r = np.array([h["raw"] for h in x["horses"]]); R.append((r - r.mean())[keep]); Z.append(F[id(x)][keep])
                Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            R, Z = np.concatenate(R), np.vstack(Z); sd = Z.std(axis=0); sd[sd == 0] = 1
            rs = R.std()
            c = LogisticRegression(C=C, max_iter=20000).fit(np.column_stack([R / rs * 100, Z / sd]), Y).coef_[0]
            return (c[1:] / sd) / (c[0] * 100 / rs)
        betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020}
        print(arm, {s: np.round(v, 2).tolist() for s, v in betas.items()}, flush=True)
        with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
            for x in rows:
                bb = betas.get(season(x["date"])); y = dict(x, arm=f"group_{arm}")
                if bb is not None and F[id(x)] is not None:
                    add = F[id(x)] @ bb
                    y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
