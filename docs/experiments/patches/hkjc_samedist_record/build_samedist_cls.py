"""EXP-20261122-32 預先登記（Kelvin 2026-11-22「同程記錄要睇埋班次」；回放尺 v5；Holm 家族 2）
診斷（live 之上 v5 殘差；兩窗都睇過）：同程喺更高班上過名（今仗降班）dev +1.4 [+0.4,+2.4]、holdout +1.6 [+0.2,+3.2]（n 5,508／3,134）；
同程只喺更低班上過名（今仗升班）dev −1.8 [−3.4,−0.3]、holdout −0.9。同程「贏過」冇額外價值（−0.5／−0.2），唔做。
班次：HKJC 馬匹頁 class（1–5；分級賽／新馬 = 0 當最高）；今仗班次 = 賽果 RaceClass。同程 = 完全同米數（任何場地）。V1、V2 照留。
  K1  加 β·[同程喺比今仗高嘅班上過名]
  K2  加 β1·[同程喺更高班上過名] + β2·[同程上名全部喺更低班]
β 逐季 walk-forward（只用之前季）、場內置中。判：v5；dev 唔過唔開 holdout；唔准換定義救。
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
                ps = str(q.get("pos") or "").strip(); cl = str(q.get("class") or "").strip()
                runs[code].append((iso(q["date"]), float(q["distance"]), int(ps) if ps.isdigit() else None, int(cl) if cl.isdigit() else (0 if cl else None)))
        except Exception: pass
idx = b.load_index(); code_of = {}; CLS = {}
for (d, n), race in idx["results"].items():
    c = str((race.get("_header") or {}).get("RaceClass") or "")
    m = re.match(r"Class (\d)", c); CLS[(d, n)] = int(m.group(1)) if m else (0 if c.startswith(("Group", "Griffin")) else None)
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
        hi = lo = 0.0
        tc = CLS.get((x["date"], x["race"]))
        if prev and dist and tc is not None:
            plc = [t[3] for t in prev if t[1] == dist and t[2] and t[2] <= 3 and t[3] is not None]
            hi = float(any(c2 < tc for c2 in plc)); lo = float(bool(plc) and all(c2 > tc for c2 in plc))
        cnt[0] += hi; cnt[1] += 1
        mat.append([0.0, hi, lo])
    F[id(x)] = np.array(mat)
print("馬次", cnt[1], "更高班同程上名", int(cnt[0]), flush=True)
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
for arm, cols in (("K1", [1]), ("K2", [1, 2])):
    def fit(races):
        R, Z, Y = [], [], []
        for x in races:
            keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
            r = np.array([h["raw"] for h in x["horses"]]); z = F[id(x)][:, cols]
            R.append((r - r.mean())[keep]); Z.append((z - z.mean(0))[keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
        R, Z = np.concatenate(R), np.vstack(Z)
        c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z]), Y).coef_[0]
        return c[1:] / (c[0] / R.std())
    betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020}
    print(arm, {s: [round(float(v), 2) for v in bb] for s, bb in betas.items()}, flush=True)
    with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
        for x in rows:
            bb = betas.get(season(x["date"])); y = dict(x, arm=f"samedist_cls_{arm}")
            if bb is not None:
                z = F[id(x)][:, cols] @ bb; new = np.array([h["raw"] for h in x["horses"]]) + (z - z.mean())
                y["horses"] = [dict(h, raw=round(float(v), 4)) for h, v in zip(x["horses"], new)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
