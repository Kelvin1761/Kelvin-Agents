"""EXP-20261116-05 H：負磅殘差只喺高班修正（dump 候選）。由 build.py 改。

預先登記（揀法只用 dev 窗診斷：第一班 −7.96、第二班 −2.97 pp/10 磅；第三／四班 ≈0）：
  H   raw' = raw + β·(負磅 − 場均)/10，只限第一班、第二班同非讓磅賽（分級賽／新馬等）；其他班次唔郁。β 逐季 walk-forward。
用法：python3 build_hiclass.py <base.jsonl> <out_prefix>

原 docstring：Kelvin 2026-11-16「輕磅＋好檔」跟進：負磅殘差修正（dump 候選，唔重跑引擎）。

殘差診斷（v3，2020/21 起）：每 +10 磅（相對場均）殘差 −0.74pp [−1.32,−0.15]；第二班 −3.6、泥地 −1.9、長途 −1.4。
候選（預先登記兩個，固定）：
  G   raw' = raw + β·(負磅 − 場均)/10，β 逐季 walk-forward（只用之前季，2020/21 起，標準化＋newton-cg）
  C   同 G，但 β 按情境組（≤1200／1201–1650／≥1800 × 草／泥）各自 fit
負磅 = 賽果庫 ActualWt（實際負磅，已扣見習減磅；賽前已知）。用法：python3 build.py <base.jsonl> <out_prefix>
"""
import json
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def ctx(x):
    d = x["distance"]
    return ("S" if d <= 1200 else ("M" if d <= 1650 else "L")) + ("A" if x["awt"] else "T")


def main():
    import hkjc_history_replay_pit as p
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna() & df["ActualWt"].notna()]
    wt = defaultdict(list)
    cls = {}
    for r in df.itertuples():
        wt[(str(r.Date)[:10], int(r.RaceNo), int(r.Rank))].append(float(r.ActualWt))
        cls[(str(r.Date)[:10], int(r.RaceNo))] = str(r.RaceClass)

    def hi(x):
        c = cls.get((x["date"], x["race"]), "")
        return not c.startswith(("Class 3", "Class 4", "Class 5"))
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)

    def feat(x):
        v = []
        for h in x["horses"]:
            w = wt.get((x["date"], x["race"], h["pos"])) if h["pos"] else None
            v.append(w[0] if w and len(w) == 1 else np.nan)
        v = np.array(v)
        if np.isnan(v).all():
            return np.zeros(len(v))
        v = np.where(np.isnan(v), np.nanmean(v), v)
        return (v - v.mean()) / 10.0

    def fit(races):
        races = [x for x in races if hi(x)]
        R, Z, Y = [], [], []
        for x in races:
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = np.array([h["raw"] for h in x["horses"]])
            R.append((r - r.mean())[keep]); Z.append(feat(x)[keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        R, Z = np.concatenate(R), np.concatenate(Z)
        if len(Y) < 500 or Z.std() == 0:
            return 0.0
        c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z / Z.std()]), Y).coef_[0]
        return (c[1] / Z.std()) / (c[0] / R.std())

    seasons = sorted(by)
    bH = {s: fit([x for t in by if 2020 <= t < s for x in by[t]]) for s in seasons if s >= 2021}
    print("β H", {s: round(v, 2) for s, v in bH.items()})
    with open(f"{sys.argv[2]}_H.jsonl", "w") as f:
        for x in rows:
            bb = bH.get(season(x["date"]))
            y = dict(x, arm="weight_hiclass_H")
            if bb is not None and hi(x):
                add = feat(x) * bb
                y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
