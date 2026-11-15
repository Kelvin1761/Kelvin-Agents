"""EXP-20261116-01 上線用凍結：檔位 × 跑法（S 格）＋ 逐檔曲線（D 格）嘅格值同 β（SD 候選）。

構造同 build.py 一模一樣：格值 = 全部歷史殘差（殘差用嗰季之前嘅季校準）× n/(n+200)；
β = 合併 fit：2020/21 起每季用「嗰季之前」嘅表（as-of），標準化＋newton-cg（兩個特徵同時 fit）。
輸出 → hkjc_wong_choi_auto/resources/hkjc_draw_style.json。用法：python3 freeze.py <v3/base.jsonl> <out.json>
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


def grp(venue, awt, distance):
    g = "HV" if venue == "跑馬地" else ("AWT" if awt else ("STR" if distance == 1000 else "ST"))
    return g + ("S" if distance <= 1200 else "L")


def style_class(frac):
    return "U" if frac is None else ("F" if frac <= 0.3 else ("M" if frac <= 0.6 else "B"))


def draw_band(d):
    return "I" if d <= 4 else ("C" if d <= 9 else "O")


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
        sty = float(np.mean(h[-6:])) if len(h) >= 2 else None
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
        g = grp(x["venue"], x["awt"], x["distance"])
        sc, dc = [], []
        for h in x["horses"]:
            i = info.get((x["date"], x["race"], h["pos"])) if h["pos"] else None
            if not i or len(i) != 1 or i[0][1] != i[0][1]:
                sc.append(None); dc.append(None); continue
            sty, d = i[0]
            sc.append(f"{g}|{style_class(sty)}|{draw_band(d)}"); dc.append(f"{g}|{min(int(d), 13)}|{int(F >= 12)}")
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

    def table(upto, j):
        acc = defaultdict(lambda: [0.0, 0])
        for t in seasons:
            if t < upto:
                for c, (sm, n) in resid[t][j].items():
                    acc[c][0] += sm; acc[c][1] += n
        return {c: sm / (n + K) for c, (sm, n) in acc.items()}, {c: n for c, (_, n) in acc.items()}

    tabs = {s: (table(s, 0)[0], table(s, 1)[0]) for s in seasons}
    R, Z1, Z2, Y = [], [], [], []
    for x in (x for s in seasons if s >= 2020 for x in by[s]):
        sc, dc = cache[id(x)]; t1, t2 = tabs[season(x["date"])]
        v1 = np.array([t1.get(c, 0.0) if c else 0.0 for c in sc]); v2 = np.array([t2.get(c, 0.0) if c else 0.0 for c in dc])
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
        r = np.array([h["raw"] for h in x["horses"]])
        R.append((r - r.mean())[keep]); Z1.append((v1 - v1.mean())[keep]); Z2.append((v2 - v2.mean())[keep])
        Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
    R, Z1, Z2 = map(np.concatenate, (R, Z1, Z2))
    c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z1 / Z1.std(), Z2 / Z2.std()]), Y).coef_[0]
    b1 = float((c[1] / Z1.std()) / (c[0] / R.std())); b2 = float((c[2] / Z2.std()) / (c[0] / R.std()))
    s_full, s_n = table(max(seasons) + 1, 0)
    d_full, d_n = table(max(seasons) + 1, 1)
    out = {"version": 1, "experiment": "EXP-20261116-01", "K": K, "beta_style": round(b1, 3), "beta_curve": round(b2, 3),
           "last_date": max(x["date"] for x in rows), "races": len(rows),
           "style_rule": "之前最多 6 仗（賽果庫）第一個沿途位置 ÷ 完成匹數 平均；≥2 仗；≤0.3 F、≤0.6 M、其餘 B；冇 = U",
           "style_cells": {k: round(v, 5) for k, v in sorted(s_full.items())},
           "curve_cells": {k: round(v, 5) for k, v in sorted(d_full.items())},
           "style_n": dict(sorted(s_n.items())), "curve_n": dict(sorted(d_n.items()))}
    json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
    print("β_style", out["beta_style"], "β_curve", out["beta_curve"], "style cells", len(s_full), "curve cells", len(d_full))
    for g in ("HVS", "STS", "STL"):
        print(g, " ".join(f"{st}{db}:{100 * s_full.get(f'{g}|{st}|{db}', 0):+.1f}" for st in "FMBU" for db in "ICO"))


if __name__ == "__main__":
    main()
