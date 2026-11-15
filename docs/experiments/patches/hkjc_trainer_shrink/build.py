"""EXP-20261115-17：練馬師收縮分數（Kelvin 2026-11-15）。
賽日 d 之前，每位練馬師嘅模型殘差 e = 入頭三 − σ(a_s + b_s·(raw − 場均))，(a_s, b_s) 用 d 所屬季之前嘅季 fit（2019/20 用自己，burn-in）。
T = Σe /（n + k），只用日期 < d 嘅出賽。k ∈ {200, 500}（預先登記）。候選 raw' = raw + β·(T − 場均)，β 逐季 walk-forward（標準化＋newton-cg）。
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


def calib(races):
    X, Y = [], []
    for x in races:
        hs = [h for h in x["horses"] if h["pos"]]
        r = np.array([h["raw"] for h in hs]); X += list(r - r.mean()); Y += [h["pos"] <= 3 for h in hs]
    m = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X).reshape(-1, 1), Y)
    return m.intercept_[0], m.coef_[0][0]


def main():
    import hkjc_history_replay_pit as p
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    out = Path(sys.argv[2])
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()]
    trainer = {}
    for r in df.itertuples():
        trainer.setdefault((str(r.Date)[:10], int(r.RaceNo), int(r.Rank)), []).append(r.Trainer)
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    cal = {s: calib([x for t in by if t < s for x in by[t]] or by[s]) for s in sorted(by)}
    feats = {200: {}, 500: {}}
    acc = defaultdict(lambda: [0.0, 0])
    for d in sorted({x["date"] for x in rows}):
        day = [x for x in rows if x["date"] == d] if False else None
    rows_by_date = defaultdict(list)
    for x in rows:
        rows_by_date[x["date"]].append(x)
    for d in sorted(rows_by_date):
        a, b = cal[season(d)]
        for x in rows_by_date[d]:
            for h in x["horses"]:
                t = trainer.get((x["date"], x["race"], h["pos"])) if h["pos"] else None
                t = t[0] if t and len(t) == 1 else None
                for k in feats:
                    s_, n_ = acc[t] if t else (0.0, 0)
                    feats[k][(x["date"], x["race"], h["n"])] = s_ / (n_ + k) if t else 0.0
        for x in rows_by_date[d]:
            hs = [h for h in x["horses"] if h["pos"]]
            r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
            for h, z in zip(hs, rc):
                t = trainer.get((x["date"], x["race"], h["pos"]))
                if t and len(t) == 1:
                    e = float(h["pos"] <= 3) - 1 / (1 + np.exp(-(a + b * z)))
                    acc[t[0]][0] += e; acc[t[0]][1] += 1

    def zf(x, k):
        v = np.array([feats[k].get((x["date"], x["race"], h["n"]), 0.0) for h in x["horses"]])
        return v - v.mean()

    def fit(races, k):
        R, Z, Y = [], [], []
        for x in races:
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = np.array([h["raw"] for h in x["horses"]])
            R.append((r - r.mean())[keep]); Z.append(zf(x, k)[keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        R, Z = np.concatenate(R), np.concatenate(Z)
        sr, sz = R.std(), Z.std() or 1.0
        c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / sr, Z / sz]), Y).coef_[0]
        return (c[1] / sz) / (c[0] / sr)

    for k in feats:
        betas = {s: fit([x for t in by if 2019 < t < min(s, 2024) for x in by[t]], k) for s in sorted(by) if s > 2020}
        with open(out / f"trainer_shrink_{k}.jsonl", "w") as f:
            for x in rows:
                bb = betas.get(season(x["date"]))
                y = dict(x, arm=f"trainer_shrink_{k}")
                if bb is not None:
                    add = zf(x, k) * bb
                    y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")
        print(k, {s: round(float(v), 1) for s, v in betas.items() if s <= 2024})


if __name__ == "__main__":
    main()
