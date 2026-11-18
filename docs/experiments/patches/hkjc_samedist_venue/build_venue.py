"""EXP-20261119-01 預先登記（Kelvin 2026-11-19「沙田1000直路同谷草1000轉彎係兩件事」；Holm 家族 2）
往績 = parsed/horses.jsonl.gz，日期嚴格早過今仗。場地 key = 谷草 / 沙田草地 / 沙田全天候。
指標 X = 同程有上名，但全部上名都唔喺今仗場地（live 依家照當「同程有上名」+0.4284）。
  V1  固定：X 嘅馬扣返 0.4284（即同程上名只認同場地；冇擬合）
  V2  X 指標 β 逐季 walk-forward（只用之前季），場內置中
判：hkjc_replay_compare_v4.py（Δlog-loss CI 上界 < 0、Gold／Good 下界 > −1.0pp、好過 null）；dev 唔過就唔開 holdout。
"""
import gzip, json, re, sys
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as b  # noqa: E402

def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
def num(x):
    try: return float(str(x).strip())
    except ValueError: return None
def pos(x):
    s = str(x or "").strip(); return int(s) if s.isdigit() else None
def iso(dmy):
    d, m, y = dmy.split("/"); return f"{y}-{m}-{d}"
def vkey(vt):
    vt = str(vt or "")
    if vt.startswith("跑馬地"): return "HV"
    if "全天候" in vt: return "AWT"
    if vt.startswith("沙田"): return "ST"
    return None

rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
runs = defaultdict(list)
for line in gzip.open("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/parsed/horses.jsonl.gz", "rt", encoding="utf-8"):
    r = json.loads(line); code = r["horse_id"].rsplit("_", 1)[-1]
    for q in r.get("runs") or []:
        try: runs[code].append((iso(q["date"]), num(q.get("distance")), pos(q.get("pos")), vkey(q.get("venue_track"))))
        except Exception: pass
idx = b.load_index(); code_of = {}
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        if m: code_of[(d, n, str(row.get("horse_no")))] = m.group(1)
F = {}; cnt = 0; tot = 0
for x in rows:
    today = "HV" if x.get("venue") == "跑馬地" else ("AWT" if x.get("awt") else "ST")
    v = []
    for h in x["horses"]:
        tot += 1; xi = 0.0
        c = code_of.get((x["date"], x["race"], str(h["n"])))
        if c in runs:
            pl = [t for t in runs[c] if t[0] < x["date"] and t[1] == x.get("distance") and t[2] and t[2] <= 3]
            xi = float(bool(pl) and not any(t[3] == today for t in pl))
        cnt += xi; v.append(xi)
    F[id(x)] = np.array(v)
print("馬次", tot, "X", int(cnt), flush=True)
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
def fit(races):
    R, Z, Y = [], [], []
    for x in races:
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
        r = np.array([h["raw"] for h in x["horses"]])
        R.append((r - r.mean())[keep]); Z.append(F[id(x)][keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
    R, Z = np.concatenate(R), np.concatenate(Z)
    c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z]), Y).coef_[0]
    return c[1] / (c[0] / R.std())
betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020}
print("V2 β", {s: round(float(v), 2) for s, v in betas.items()}, flush=True)
for arm in ("V1", "V2"):
    with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
        for x in rows:
            bb = -0.4284 if arm == "V1" else betas.get(season(x["date"]))
            y = dict(x, arm=f"samedist_venue_{arm}")
            if bb is not None:
                add = F[id(x)] * bb; add = add - add.mean()
                y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
