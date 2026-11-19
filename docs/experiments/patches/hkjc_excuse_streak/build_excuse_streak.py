"""EXP-20261119-06 預先登記（Kelvin 2026-11-19「上兩仗以上連續塞車／意外／跑法被質疑，呢場會唔會加番分」；Holm 家族 2）。
寫之前已睇：diag_excuse_streak.py（dev＋holdout 殘差，見記錄）。
嚴格藉口 = 受阻／搵唔到位｜走外疊冇遮擋｜騎法被質疑（策騎指示交代／被查詢／被告誡、未有力策）；只用日期嚴格早過今仗嘅事件報告。
  X1  指標「上兩仗都有嚴格藉口＋兩仗都未入位」β 逐季 walk-forward（只用之前季），場內置中
  X2  指標「上兩仗都有嚴格藉口」β 逐季 walk-forward
判：hkjc_replay_compare_v4.py；dev 唔過唔開 holdout。用法：python3 build_excuse_streak.py <base> <old_incidents.json> <out_prefix>
"""
import json, os, sys
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import diag_excuse_streak as d  # noqa: E402

runs = d.load_runs(sys.argv[2])
idx = d.b.load_index(); pos = {}
for (dt, n), race in idx["results"].items():
    for row in race.get("results", []):
        try: pos[(dt, n, str(row.get("horse_no")))] = int(str(row.get("pos")).strip())
        except ValueError: pos[(dt, n, str(row.get("horse_no")))] = None
runs = {c: [(dt, n, s, no, pos.get((dt, n, no))) for dt, n, s, no in v] for c, v in runs.items()}
code_of = {(dt, n, hn): c for c, v in runs.items() for dt, n, _, hn, _ in v}
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
KEYS = {"X1": "嚴格：上兩仗都有藉口＋兩仗都未入位", "X2": "嚴格：上兩仗都有藉口"}
F = {}
for x in rows:
    v = []
    for h in x["horses"]:
        c = code_of.get((x["date"], x["race"], str(h["n"])))
        f = d.features([t for t in runs[c] if t[0] < x["date"]]) if c else None
        v.append([float(bool(f and f[KEYS[a]])) for a in ("X1", "X2")])
    F[id(x)] = np.array(v)
print("X1／X2 馬次", np.sum([F[id(x)].sum(0) for x in rows], axis=0).astype(int).tolist(), flush=True)
by = defaultdict(list)
for x in rows: by[d.season(x["date"])].append(x)
def fit(races, j):
    R, Z, Y = [], [], []
    for x in races:
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
        r = np.array([h["raw"] for h in x["horses"]])
        R.append((r - r.mean())[keep]); Z.append(F[id(x)][keep, j]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
    R, Z = np.concatenate(R), np.concatenate(Z)
    c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z]), Y).coef_[0]
    return c[1] / (c[0] / R.std())
for j, arm in enumerate(("X1", "X2")):
    betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]], j) for s in sorted(by) if s >= 2020}
    print(arm, "β", {s: round(float(v), 2) for s, v in betas.items()}, flush=True)
    with open(f"{sys.argv[3]}_{arm}.jsonl", "w") as f:
        for x in rows:
            y = dict(x, arm=f"excuse_streak_{arm}"); bt = betas.get(d.season(x["date"]))
            if bt is not None:
                add = F[id(x)][:, j] * bt; add = add - add.mean()
                y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
