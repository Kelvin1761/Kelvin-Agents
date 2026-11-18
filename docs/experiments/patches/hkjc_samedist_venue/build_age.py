"""EXP-20261119-01 預先登記（Kelvin 2026-11-19「9 歲係咪太老？」；Holm 家族 2）
馬齡代理 = 賽事年份 − 進口年份（horse_id）+ 3（新馬類）/ 4（其他）。
  A1  指標 馬齡≥8，β 逐季 walk-forward，場內置中
  A2  線性 max(0, 馬齡−6)，β 逐季 walk-forward，場內置中
"""
import json, re, sys
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as b
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
idx = b.load_index(); imp = {}; code_of = {}
for hid, v in idx["horses"].items():
    m = re.match(r"HK_(\d{4})_([A-Z]\d{3})", hid)
    if m: imp[m.group(2)] = (int(m.group(1)), 3 if "新馬" in (v["profile"].get("進口類別") or "") else 4)
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        if m: code_of[(d, n, str(row.get("horse_no")))] = m.group(1)
F = {}
for x in rows:
    v = []
    for h in x["horses"]:
        c = code_of.get((x["date"], x["race"], str(h["n"])))
        age = int(x["date"][:4]) - imp[c][0] + imp[c][1] if c in imp else 6
        v.append([float(age >= 8), max(0.0, age - 6.0)])
    F[id(x)] = np.array(v)
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
for col, arm in ((0, "A1"), (1, "A2")):
    def fit(races):
        R, Z, Y = [], [], []
        for x in races:
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = np.array([h["raw"] for h in x["horses"]])
            R.append((r - r.mean())[keep]); Z.append(F[id(x)][keep, col]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        R, Z = np.concatenate(R), np.concatenate(Z)
        c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z]), Y).coef_[0]
        return c[1] / (c[0] / R.std())
    betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020}
    print(arm, {s: round(float(v), 2) for s, v in betas.items()}, flush=True)
    with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
        for x in rows:
            bb = betas.get(season(x["date"])); y = dict(x, arm=f"age_{arm}")
            if bb is not None:
                add = F[id(x)][:, col] * bb; add = add - add.mean()
                y["horses"] = [dict(h, raw=round(h["raw"] + float(a), 4)) for h, a in zip(x["horses"], add)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
