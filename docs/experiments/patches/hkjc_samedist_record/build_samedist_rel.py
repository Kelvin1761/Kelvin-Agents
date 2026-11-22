"""EXP-20261122-31 預先登記（Kelvin 2026-11-22「要好好整同程記錄」；回放尺 v5；Holm 家族 2）
診斷（live 之上 v5 殘差；兩窗都睇過，同 EXP-20261117-06 做法一樣）：同程 ≥2 戰、同程上名率比匹馬整體上名率低 >0.25
→ dev −4.0 [−6.1,−1.6]、holdout −4.1 [−7.3,−0.9]；好過整體嗰邊唔顯著。現行 V1 只問「同程有冇上過名」。
往績 = parsed/horses.jsonl.gz 香港賽事，日期嚴格早過今仗；同程 = 完全同米數（任何場地；V2 同場地組件照留）。
  R1  保留 V1，加 β·[同程 ≥2 戰 而且 同程上名率 − 整體上名率 < −0.25]
  R2  剷走 V1（同程有上名 +0.4284／有跑冇上名 −0.166），改為連續 β·n/(n+2)·(同程上名率 − 整體上名率)，n = 同程戰數
β 逐季 walk-forward（只用之前季）、場內置中。判：v5；dev 唔過唔開 holdout；唔准換門檻救。
"""
import gzip, json, re, sys
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as b
V1 = {"placed": 0.4284, "unplaced": -0.166005}
def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
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
                ps = str(q.get("pos") or "").strip(); runs[code].append((iso(q["date"]), float(q["distance"]), int(ps) if ps.isdigit() else None))
        except Exception: pass
idx = b.load_index(); code_of = {}
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        if m: code_of[(d, n, str(row.get("horse_no")))] = m.group(1)
F = {}; cnt = [0, 0]
for x in rows:
    dist = x.get("distance"); mat = []
    for h in x["horses"]:
        c = code_of.get((x["date"], x["race"], str(h["n"])))
        prev = [t for t in runs.get(c, []) if t[0] < x["date"]]
        v1 = ind = cont = 0.0
        if prev and dist:
            sd = [t for t in prev if t[1] == dist]; n = len(sd); pl = sum(1 for t in sd if t[2] and t[2] <= 3)
            allr = sum(1 for t in prev if t[2] and t[2] <= 3) / len(prev)
            if n:
                v1 = V1["placed"] if pl else V1["unplaced"]
                diff = pl / n - allr
                cont = n / (n + 2) * diff
                ind = float(n >= 2 and diff < -0.25)
        cnt[0] += ind; cnt[1] += 1
        mat.append([v1, ind, cont])
    F[id(x)] = np.array(mat)
print("馬次", cnt[1], "R1 旗", int(cnt[0]), flush=True)
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
for arm, strip, col in (("R1", False, 1), ("R2", True, 2)):
    def base(x):
        r = np.array([h["raw"] for h in x["horses"]])
        if strip: v = F[id(x)][:, 0]; r = r - (v - v.mean())
        return r
    def fit(races):
        R, Z, Y = [], [], []
        for x in races:
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = base(x); z = F[id(x)][:, col]
            R.append((r - r.mean())[keep]); Z.append((z - z.mean())[keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        R, Z = np.concatenate(R), np.concatenate(Z)
        c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z]), Y).coef_[0]
        return c[1] / (c[0] / R.std())
    betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020}
    print(arm, {s: round(float(v), 2) for s, v in betas.items()}, flush=True)
    with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
        for x in rows:
            bb = betas.get(season(x["date"])); y = dict(x, arm=f"samedist_{arm}")
            if bb is not None:
                z = F[id(x)][:, col] * bb; new = base(x) + (z - z.mean())
                y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
