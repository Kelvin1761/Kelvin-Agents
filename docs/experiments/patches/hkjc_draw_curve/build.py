"""EXP-20261115-18：檔位曲線（Kelvin「檔位分係咪最 optimise」）。
組別 = 跑馬地／沙田草／沙田泥／沙田直路 × 短（≤1200）／長；格 = (組別, 檔位號碼（13+ 合併）, 大場 ≥12／細場)。
格值 = 之前季（只用日期早過今仗嘅季）模型殘差平均 × n/(n+K)，K = 200（預先登記）；殘差校準用之前季。
候選 raw' = raw + β·(格值 − 場均)，β 逐季 walk-forward（標準化＋newton-cg）。用法：python3 build.py <base.jsonl> <out.jsonl>
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
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna() & df["Draw"].notna()]
    draw = {}
    for r in df.itertuples():
        draw.setdefault((str(r.Date)[:10], int(r.RaceNo), int(r.Rank)), []).append(int(r.Draw))
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)

    def cells(x):
        F = sum(1 for h in x["horses"] if h["pos"])
        out = []
        for h in x["horses"]:
            d = draw.get((x["date"], x["race"], h["pos"])) if h["pos"] else None
            out.append((grp(x), min(d[0], 13), F >= 12) if d and len(d) == 1 else None)
        return out

    def calib(races):
        X, Y = [], []
        for x in races:
            hs = [h for h in x["horses"] if h["pos"]]
            r = np.array([h["raw"] for h in hs]); X += list(r - r.mean()); Y += [h["pos"] <= 3 for h in hs]
        m = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X).reshape(-1, 1), Y)
        return m.intercept_[0], m.coef_[0][0]

    seasons = sorted(by)
    resid = {}          # season -> {cell: [sum, n]}（只含嗰季）
    for s in seasons:
        a, b = calib([x for t in by if t < s for x in by[t]] or by[s])
        acc = defaultdict(lambda: [0.0, 0])
        for x in by[s]:
            hs = x["horses"]; r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
            for h, z, c in zip(hs, rc, cells(x)):
                if c and h["pos"]:
                    acc[c][0] += float(h["pos"] <= 3) - 1 / (1 + np.exp(-(a + b * z))); acc[c][1] += 1
        resid[s] = acc

    def table(s):
        acc = defaultdict(lambda: [0.0, 0])
        for t in seasons:
            if t < s:
                for c, (sm, n) in resid[t].items():
                    acc[c][0] += sm; acc[c][1] += n
        return {c: sm / (n + K) for c, (sm, n) in acc.items()}

    tabs = {s: table(min(s, 2024)) for s in seasons}

    def feat(x, tab):
        v = np.array([tab.get(c, 0.0) if c else 0.0 for c in cells(x)])
        return v - v.mean()

    def fit(races, s):
        R, Z, Y = [], [], []
        for x in races:
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = np.array([h["raw"] for h in x["horses"]])
            R.append((r - r.mean())[keep]); Z.append(feat(x, tabs[season(x["date"])])[keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        R, Z = np.concatenate(R), np.concatenate(Z)
        c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z / Z.std()]), Y).coef_[0]
        return (c[1] / Z.std()) / (c[0] / R.std())

    betas = {s: fit([x for t in by if 2020 <= t < min(s, 2024) for x in by[t]], s) for s in seasons if s >= 2021}
    with open(sys.argv[2], "w") as f:
        for x in rows:
            bb = betas.get(season(x["date"]))
            y = dict(x, arm="draw_curve")
            if bb is not None:
                add = feat(x, tabs[season(x["date"])]) * bb
                y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
    print("β", {s: round(float(v), 1) for s, v in betas.items() if s <= 2024})


if __name__ == "__main__":
    main()
