"""Kelvin 2026-11-15「保留現有檔位分，再加逐檔殘差曲線」→ forward shadow `draw_curve_shadow` 嘅凍結表。

構造同 EXP-20261115-18／19「現有＋曲線」一模一樣（build.py），base = 回放 v3（現行 main，含上仗賠率）：
  格 = (組別 HV/ST/AWT/STR × 短≤1200／長, 檔號 1–13+, 大場 ≥12)
  格值 = 全部歷史殘差平均 × n/(n+200)（殘差 = 入頭三 − 校準 p；校準用嗰季之前嘅季）
  β = 合併 fit：2020/21 起每季用「嗰季之前」嘅表（as-of，同 walk-forward 一樣），標準化＋newton-cg
live：raw' = raw + β·(格值 − 場均)。凍結之後唔再改；forward 係判斷。
用法：python3 freeze.py <v3/base.jsonl> <out.json>
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
            out.append(f"{grp(x['venue'], x['awt'], x['distance'])}|{min(d[0], 13)}|{int(F >= 12)}" if d and len(d) == 1 else None)
        return out

    def calib(races):
        X, Y = [], []
        for x in races:
            hs = [h for h in x["horses"] if h["pos"]]
            r = np.array([h["raw"] for h in hs]); X += list(r - r.mean()); Y += [h["pos"] <= 3 for h in hs]
        m = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X).reshape(-1, 1), Y)
        return m.intercept_[0], m.coef_[0][0]

    seasons = sorted(by)
    resid = {}
    for s in seasons:
        a, b = calib([x for t in by if t < s for x in by[t]] or by[s])
        acc = defaultdict(lambda: [0.0, 0])
        for x in by[s]:
            hs = x["horses"]; r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
            for h, z, c in zip(hs, rc, cells(x)):
                if c and h["pos"]:
                    acc[c][0] += float(h["pos"] <= 3) - 1 / (1 + np.exp(-(a + b * z))); acc[c][1] += 1
        resid[s] = acc

    def table(upto):
        acc = defaultdict(lambda: [0.0, 0])
        for t in seasons:
            if t < upto:
                for c, (sm, n) in resid[t].items():
                    acc[c][0] += sm; acc[c][1] += n
        return {c: sm / (n + K) for c, (sm, n) in acc.items()}, {c: n for c, (sm, n) in acc.items()}

    def feat(x, tab):
        v = np.array([tab.get(c, 0.0) if c else 0.0 for c in cells(x)])
        return v - v.mean()

    R, Z, Y = [], [], []
    tabs = {s: table(s)[0] for s in seasons}
    for x in (x for s in seasons if s >= 2020 for x in by[s]):
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
        r = np.array([h["raw"] for h in x["horses"]])
        R.append((r - r.mean())[keep]); Z.append(feat(x, tabs[season(x["date"])])[keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
    R, Z = np.concatenate(R), np.concatenate(Z)
    c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z / Z.std()]), Y).coef_[0]
    beta = float((c[1] / Z.std()) / (c[0] / R.std()))
    full, n = table(max(seasons) + 1)
    out = {"K": K, "beta": round(beta, 3), "last_date": max(x["date"] for x in rows), "races": len(rows),
           "cells": {k: round(v, 5) for k, v in sorted(full.items())}, "n": dict(sorted(n.items()))}
    json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
    print("β", out["beta"], "cells", len(out["cells"]), "last", out["last_date"])
    for g in ("HVS", "STS", "STL", "HVL"):
        for big in (1, 0):
            print(g, big, " ".join(f"{d}:{100 * full.get(f'{g}|{d}|{big}', 0):+.1f}" for d in range(1, 14)))


if __name__ == "__main__":
    main()
