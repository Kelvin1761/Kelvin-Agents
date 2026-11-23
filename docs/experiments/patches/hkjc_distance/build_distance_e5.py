"""（原 EXP-20261122-21 結構）EXP-20261124-07 預先登記（Kelvin 2026-11-24「攞短距離熱身之後返首本，唔應該當大幅增程扣分」）。寫喺跑之前；base = live（db_DT）；尺 v5.2。
  E3 = 今仗比上仗長 ≥400 米（觸發 D1 大幅增程）而且上上仗或者再前一仗喺今仗路程 ±100 米跑過（熱身後返首本）；β walk-forward（預期正 = 抵銷 D1）。
  E4 = E3 嘅馬直接加返 D1 扣分 +0.926（唔 fit；即係「熱身後返首本唔扣」嘅正確性修正）。
  E5（第二輪，Kelvin 2026-11-24「去返自己首本路程都唔應該扣，唔好限熱身」；寫喺跑之前）：觸發 D1 而且
     （曾經喺今仗路程 ±100 米上名）或者（近三仗內喺今仗路程 ±100 米跑過）→ 加返 +0.926（唔扣）。判同 E4；Kelvin 預先批准：打和或者更好就上。
  判：E4 兩窗 v5.2 都唔差（Δlog-loss CI 下界 ≤ 0 即唔顯著變差，而且頭二入頭三 Δ ≥ 0）→ 可當正確性修正（Kelvin 決定）；E3 照 v5.2 PASS 規則。
原 docstring：EXP-20261122-21 預先登記：大幅增程（≥400 米）分「今仗路程上過名」（E1）／「從未跑過今仗路程」（E2）。
base = live（已含 D1）；每個 arm 喺 base 之上加 β·(指標 − 場均)，β 逐季 walk-forward（只用之前季，同 build_distance.py）。
用法：python3 build_distance_proven.py <base.jsonl> <out_prefix>
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
        return [0.0, 0.0, 0.0]
    dist, pd = F.num(rr[i].get("distance")), F.num(rr[i - 1].get("distance"))
    if not dist or not pd or dist - pd < 400:
        return [0.0, 0.0, 0.0]
    back = [F.num(q.get("distance")) for q in rr[max(0, i - 3):i - 1]]
    warm = any(b and abs(b - dist) <= 100 for b in back)
    proven = any((F.pos(q.get("pos")) or 99) <= 3 and abs((F.num(q.get("distance")) or 0) - dist) <= 100 for q in rr[:i])
    return [float(warm), float(warm), float(warm or proven)]


ARMS = {"E5": 2}


def main():
    import hkjc_history_replay_pit as p
    runs, _ = F.load()
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()].assign(d=lambda x: x["Date"].astype(str).str[:10])
    pos_in = {code: {q["d"]: i for i, q in enumerate(rr)} for code, rr in runs.items()}
    key = {}
    for r in df.itertuples():
        i = pos_in.get(r.HorseID, {}).get(r.d)
        key[(r.d, int(r.RaceNo), int(r.Rank))] = flags(runs[r.HorseID], i) if i is not None else [0.0, 0.0, 0.0]
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    ALL = {id(x): np.array([key.get((x["date"], x["race"], h["pos"]), [0.0, 0.0, 0.0]) if h["pos"] else [0.0, 0.0, 0.0]
                            for h in x["horses"]]) for x in rows}
    print("馬次", {a: int(sum(v[:, c].sum() for v in ALL.values())) for a, c in ARMS.items()}, flush=True)
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    for arm, col in ARMS.items():
        def fit(races):
            R, Z, Y = [], [], []
            for x in races:
                keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
                r = np.array([h["raw"] for h in x["horses"]])
                R.append((r - r.mean())[keep]); Z.append(ALL[id(x)][keep][:, [col]])
                Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
            R, Z = np.concatenate(R), np.vstack(Z)
            sd = Z.std(axis=0); sd[sd == 0] = 1
            c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z / sd]), Y).coef_[0]
            return float((c[1] / sd[0]) / (c[0] / R.std()))
        betas = ({s: fit([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020} if arm == "E3_unused"
                 else {s: 0.926 for s in sorted(by) if s >= 2020})
        print(arm, {s: round(b, 3) for s, b in betas.items()}, flush=True)
        with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
            for x in rows:
                b = betas.get(season(x["date"]))
                y = dict(x, arm=f"distance_{arm}")
                if b is not None:
                    add = ALL[id(x)][:, col] * b
                    add = add - add.mean()
                    y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
