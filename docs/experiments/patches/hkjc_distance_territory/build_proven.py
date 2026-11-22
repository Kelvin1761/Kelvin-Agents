"""EXP-20261122-25 預先登記（Kelvin 2026-11-22「證明咗係首本路程／上過名就唔扣」；回放尺 v5；Holm 家族 2）
上次 EXP-20261122-21 E1（加一項 β 抵銷）喺 v4 dev REJECT；今次係**取代**：大幅增程旗只畀「未證明」嘅馬。
  P1  D1' = [今仗 − 上仗 ≥ 400] 而且 今仗路程（完全同米數）香港往績冇上過名
  P2  D1' = [今仗 − 上仗 ≥ 400] 而且 今仗路程 ±100 米內冇上過名（1600／1650 當同一程）
做法：剷走 live D1（β −0.926 場內置中），加 β·D1'，β 逐季 walk-forward（只用之前季）、場內置中。
判：hkjc_replay_compare_v5.py；dev 唔過唔開 holdout；唔准換門檻救。
"""
import gzip, json, re, sys
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as b
D1_BETA = -0.926
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
def num(x):
    try: return float(str(x).strip())
    except ValueError: return None
def iso(dmy):
    d, m, y = dmy.split("/"); return f"{y}-{m}-{d}"
def hk(vt):
    vt = str(vt or ""); return vt.startswith("跑馬地") or vt.startswith("沙田")
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
runs = defaultdict(list)
for line in gzip.open("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/parsed/horses.jsonl.gz", "rt", encoding="utf-8"):
    r = json.loads(line); code = r["horse_id"].rsplit("_", 1)[-1]
    for q in r.get("runs") or []:
        try:
            if hk(q.get("venue_track")):
                ps = str(q.get("pos") or "").strip()
                runs[code].append((iso(q["date"]), num(q.get("distance")), int(ps) if ps.isdigit() else None))
        except Exception: pass
for v in runs.values(): v.sort()
idx = b.load_index(); code_of = {}
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        if m: code_of[(d, n, str(row.get("horse_no")))] = m.group(1)
F = {}; cnt = np.zeros(3)
for x in rows:
    dist = x.get("distance"); mat = []
    for h in x["horses"]:
        c = code_of.get((x["date"], x["race"], str(h["n"])))
        prev = [t for t in runs.get(c, []) if t[0] < x["date"] and t[1]]
        if prev and dist:
            jump = dist - prev[-1][1]
            pl = [t[1] for t in prev if t[2] and t[2] <= 3]
            exact = any(x == dist for x in pl); near = any(abs(x - dist) <= 100 for x in pl)
            v = [float(jump >= 400), float(jump >= 400 and not exact), float(jump >= 400 and not near)]
        else:
            v = [0.0, 0.0, 0.0]
        cnt += v; mat.append(v)
    F[id(x)] = np.array(mat)
print("D1", int(cnt[0]), "P1 未證明（同米數）", int(cnt[1]), "P2 未證明（±100）", int(cnt[2]), flush=True)
def strip_d1(x):
    d1 = F[id(x)][:, 0]; add = -D1_BETA * (d1 - d1.mean())
    return np.array([h["raw"] for h in x["horses"]]) + add
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
ARMS = {"P1": (True, 1), "P2": (True, 2)}
for arm, (strip, col) in ARMS.items():
    base_raw = {id(x): (strip_d1(x) if strip else np.array([h["raw"] for h in x["horses"]])) for x in rows}
    def fit(races):
        R, Z, Y = [], [], []
        for x in races:
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = base_raw[id(x)]
            R.append((r - r.mean())[keep]); Z.append(F[id(x)][keep, col]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        R, Z = np.concatenate(R), np.concatenate(Z)
        c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z]), Y).coef_[0]
        return c[1] / (c[0] / R.std())
    betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020}
    print(arm, {s: round(float(v), 2) for s, v in betas.items()}, flush=True)
    with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
        for x in rows:
            bb = betas.get(season(x["date"])); y = dict(x, arm=f"proven_{arm}")
            if bb is not None:
                z = F[id(x)][:, col] * bb; z = z - z.mean()
                new = base_raw[id(x)] + z
                y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
