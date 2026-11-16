"""EXP-20261117-03 預先登記（Kelvin 2026-11-17「增程係真訊號，check 可唔可以入分、乜情況入」）：
  D1  raw += β·[大幅增程：今仗路程 − 上仗路程 ≥ 400 米]
  D2  raw += β·[短途轉一哩以上：上仗 ≤ 1200 米、今仗 ≥ 1600 米]
β 逐季 walk-forward（2019/20 起，只用之前季），標準化＋newton-cg（同 build_round3.py）。base = live dump（I1）。
往績 = HKJC 馬匹頁（只用日期早過今仗）。用法：python3 build_distance.py <I1.jsonl> <out_prefix>
"""
import json
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_patterns")
import features as F  # noqa: E402


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def flags(rr, i):
    if i == 0:
        return [0.0, 0.0]
    dist, pd = F.num(rr[i].get("distance")), F.num(rr[i - 1].get("distance"))
    if not dist or not pd:
        return [0.0, 0.0]
    return [float(dist - pd >= 400), float(pd <= 1200 and dist >= 1600)]


ARMS = {"D1": [0], "D2": [1]}


def main():
    import hkjc_history_replay_pit as p
    runs, _ = F.load()
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()].assign(d=lambda x: x["Date"].astype(str).str[:10])
    pos_in = {code: {q["d"]: i for i, q in enumerate(rr)} for code, rr in runs.items()}
    key = {}
    for r in df.itertuples():
        i = pos_in.get(r.HorseID, {}).get(r.d)
        key[(r.d, int(r.RaceNo), int(r.Rank))] = flags(runs[r.HorseID], i) if i is not None else [0.0, 0.0]
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    ALL = {id(x): np.array([key.get((x["date"], x["race"], h["pos"]), [0.0, 0.0]) if h["pos"] else [0.0, 0.0]
                            for h in x["horses"]]) for x in rows}
    print("觸發率", {a: round(float(np.mean([v[:, c[0]].mean() for v in ALL.values()])), 4) for a, c in ARMS.items()})
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    for arm, cols in ARMS.items():
        Fm = {k: v[:, cols] for k, v in ALL.items()}

        def fit(races):
            R, Z, Y = [], [], []
            for x in races:
                keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
                r = np.array([h["raw"] for h in x["horses"]])
                R.append((r - r.mean())[keep]); Z.append(Fm[id(x)][keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            R, Z = np.concatenate(R), np.vstack(Z)
            sd = Z.std(axis=0); sd[sd == 0] = 1
            c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z / sd]), Y).coef_[0]
            return (c[1:] / sd) / (c[0] / R.std())
        betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020}
        print(arm, {s: [round(float(b), 3) for b in v] for s, v in betas.items()}, flush=True)
        with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
            for x in rows:
                bb = betas.get(season(x["date"]))
                y = dict(x, arm=f"distance_{arm}")
                if bb is not None:
                    add = Fm[id(x)] @ bb
                    add = add - add.mean()
                    y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
