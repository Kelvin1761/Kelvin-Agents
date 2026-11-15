"""Kelvin 2026-11-16「負磅定檔位要正式改好」：檔位 × 跑法殘差格（dump 候選）。

診斷（v3，2020/21–2023/24 vs 之後，同方向）：外檔吃虧集中喺後上／中置（沙田草短後上外 −6.1／−6.1pp），
前置外檔幾乎冇事；沙田長途前置內檔反而 −4.7／−3.2。現行檔位分同逐檔曲線都冇按跑法分。
跑法 = 賽前慣性早段位置：之前最多 6 仗「第一個沿途位置 ÷ 出賽數」平均（≥2 仗；之前冇就「未知」），≤0.3 前置、≤0.6 中置、其餘後上。
候選（預先登記，固定）：
  S    格 = (組別 HV/ST/AWT/STR × 短長, 跑法 4 類, 檔位段 內1–4／中5–9／外10+)；之前季殘差 × n/(n+200)；raw' = raw + β·(格值 − 場均)
  SD   S 格值 ＋ EXP-18 逐檔曲線格值（兩個特徵，各自 β）
β 逐季 walk-forward（2020/21 起，只用之前季），標準化＋newton-cg。用法：python3 build.py <base.jsonl> <out_prefix>
"""
import json
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
K = 200


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def grp(x):
    g = "HV" if x["venue"] == "跑馬地" else ("AWT" if x["awt"] else ("STR" if x["distance"] == 1000 else "ST"))
    return g + ("S" if x["distance"] <= 1200 else "L")


def main():
    import hkjc_history_replay_pit as p
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()].copy()
    df["d"] = df["Date"].astype(str).str[:10]
    df = df.sort_values("d")
    df["F"] = df.groupby(["d", "RaceNo"])["Rank"].transform("count")
    hist = defaultdict(list)
    info = defaultdict(list)
    for r in df.itertuples():
        h = hist[r.HorseID]
        sty = np.mean(h[-6:]) if len(h) >= 2 else None
        info[(r.d, int(r.RaceNo), int(r.Rank))].append((sty, r.Draw))
        rp = str(r.RunningPos or "").split()
        if rp and rp[0].isdigit() and r.F:
            h.append(int(rp[0]) / r.F)
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)

    def cells(x):
        F = sum(1 for h in x["horses"] if h["pos"])
        sc, dc = [], []
        for h in x["horses"]:
            i = info.get((x["date"], x["race"], h["pos"])) if h["pos"] else None
            if not i or len(i) != 1 or i[0][1] != i[0][1]:
                sc.append(None); dc.append(None); continue
            sty, d = i[0]
            st = "U" if sty is None else ("F" if sty <= 0.3 else ("M" if sty <= 0.6 else "B"))
            db = "I" if d <= 4 else ("C" if d <= 9 else "O")
            sc.append((grp(x), st, db)); dc.append((grp(x), min(int(d), 13), F >= 12))
        return sc, dc

    def calib(races):
        X, Y = [], []
        for x in races:
            hs = [h for h in x["horses"] if h["pos"]]
            r = np.array([h["raw"] for h in hs]); X += list(r - r.mean()); Y += [h["pos"] <= 3 for h in hs]
        m = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X).reshape(-1, 1), Y)
        return m.intercept_[0], m.coef_[0][0]

    seasons = sorted(by)
    cache = {id(x): cells(x) for x in rows}
    resid = {}
    for s in seasons:
        a, b = calib([x for t in by if t < s for x in by[t]] or by[s])
        acc = [defaultdict(lambda: [0.0, 0]), defaultdict(lambda: [0.0, 0])]
        for x in by[s]:
            hs = x["horses"]; r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
            sc, dc = cache[id(x)]
            for h, z, c1, c2 in zip(hs, rc, sc, dc):
                if h["pos"] and c1:
                    e = float(h["pos"] <= 3) - 1 / (1 + np.exp(-(a + b * z)))
                    acc[0][c1][0] += e; acc[0][c1][1] += 1; acc[1][c2][0] += e; acc[1][c2][1] += 1
        resid[s] = acc

    def table(s, j):
        acc = defaultdict(lambda: [0.0, 0])
        for t in seasons:
            if t < s:
                for c, (sm, n) in resid[t][j].items():
                    acc[c][0] += sm; acc[c][1] += n
        return {c: sm / (n + K) for c, (sm, n) in acc.items()}
    tabs = {s: (table(s, 0), table(s, 1)) for s in seasons}

    def feats(x):
        sc, dc = cache[id(x)]
        t1, t2 = tabs[season(x["date"])]
        v1 = np.array([t1.get(c, 0.0) if c else 0.0 for c in sc]); v2 = np.array([t2.get(c, 0.0) if c else 0.0 for c in dc])
        return v1 - v1.mean(), v2 - v2.mean()

    def fit(races, two):
        R, Z1, Z2, Y = [], [], [], []
        for x in races:
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = np.array([h["raw"] for h in x["horses"]]); f1, f2 = feats(x)
            R.append((r - r.mean())[keep]); Z1.append(f1[keep]); Z2.append(f2[keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        R, Z1, Z2 = map(np.concatenate, (R, Z1, Z2))
        cols = [R / R.std(), Z1 / Z1.std()] + ([Z2 / Z2.std()] if two else [])
        c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack(cols), Y).coef_[0]
        b1 = (c[1] / Z1.std()) / (c[0] / R.std())
        b2 = (c[2] / Z2.std()) / (c[0] / R.std()) if two else 0.0
        return b1, b2

    for arm, two in (("S", False), ("SD", True)):
        betas = {s: fit([x for t in by if 2020 <= t < s for x in by[t]], two) for s in seasons if s >= 2021}
        print(arm, {s: (round(float(a), 1), round(float(b), 1)) for s, (a, b) in betas.items()})
        with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
            for x in rows:
                bb = betas.get(season(x["date"]))
                y = dict(x, arm=f"draw_style_{arm}")
                if bb is not None:
                    f1, f2 = feats(x)
                    add = f1 * bb[0] + f2 * bb[1]
                    y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
