"""EXP-20261117-04 forward shadow 嘅 β（預先登記；只用嚟 forward，唔上線）：
  W  下仗 ≤7 日後再出（事後近似「已報下一場」）
  R  上仗入位＋評分跌返贏馬分（唔降班）
β = fit 2019/20–2025/26 全部回放季（同 build_distance.py 一樣方法），base = live dump I1。
用法：python3 fit_forward_betas.py <I1.jsonl>
"""
import json
import sys
from datetime import date

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_patterns")
import features as F  # noqa: E402


def flags(rr, i):
    t = rr[i]
    nx = rr[i + 1] if i + 1 < len(rr) else None
    w = float(nx is not None and (date.fromisoformat(nx["d"]) - date.fromisoformat(t["d"])).days <= 7)
    past = rr[:i]
    tr, tc = F.num(t.get("rating")), F.num(t.get("class"))
    wins = [F.num(q.get("rating")) for q in past if F.pos(q.get("pos")) == 1 and F.num(q.get("rating")) is not None]
    r = 0.0
    if past and wins and tr is not None:
        lc, lp = F.num(past[-1].get("class")), F.pos(past[-1].get("pos"))
        drop = bool(tc and lc and tc > lc)
        r = float(tr <= wins[-1] and not drop and lp is not None and lp <= 3)
    return [w, r]


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
    R, Z, Y = [], [], []
    for x in rows:
        keep = [h for h in x["horses"] if h["pos"]]
        r = np.array([h["raw"] for h in keep])
        R.append(r - r.mean())
        Z.append(np.array([key.get((x["date"], x["race"], h["pos"]), [0.0, 0.0]) for h in keep]))
        Y += [int(h["pos"] <= 3) for h in keep]
    R, Z = np.concatenate(R), np.vstack(Z)
    for j, name in enumerate(("W 下仗 ≤7 日", "R 上仗入位＋跌返")):
        z = Z[:, j]
        c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), z / z.std()]), Y).coef_[0]
        print(name, "觸發率", round(float(z.mean()), 4), "β(raw)", round(float((c[1] / z.std()) / (c[0] / R.std())), 3))


if __name__ == "__main__":
    main()
