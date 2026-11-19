"""EXP-20261119-02 預先登記（Kelvin 2026-11-19「通情達理排第 2 唔合理，要搵盲點」；Holm 家族 2）。
指標 X = 今仗跑馬地、香港往績（日期嚴格早過今仗）≤3 仗、而且從未跑過跑馬地。
  F1  X 指標 β 逐季 walk-forward（只用之前季，最早 2019/20），場內置中。
  F2  固定、冇擬合：X 而且上仗沙田草地 → 扣返轉場組件「田草轉谷草」+1.12（即經驗淺嘅初次谷草唔畀轉場加分）。
往績 = 外置碟 parsed/horses.jsonl.gz（馬匹頁全職業生涯）。
判：hkjc_replay_compare_v4.py（Δlog-loss CI 上界 < 0、Gold／Good 下界 > −1.0pp、好過 null）；dev 唔過就唔開 holdout。
用法：python3 build_first_hv.py <base.jsonl> <out_prefix>
"""
import gzip, json, re, sys
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as b  # noqa: E402

MAX_STARTS = 3
ST_TO_HV = 1.12        # surface_move.BETA["st_to_hv"]

def season(d): return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1
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
        try:
            v = vkey(q.get("venue_track"))
            if v: runs[code].append((iso(q["date"]), v))
        except Exception: pass
for v in runs.values(): v.sort()
idx = b.load_index(); code_of = {}
for (d, n), race in idx["results"].items():
    for row in race.get("results", []):
        m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
        if m: code_of[(d, n, str(row.get("horse_no")))] = m.group(1)
X, LAST_ST = {}, {}
cnt = cnt2 = tot = 0
for x in rows:
    xs, ls = [], []
    for h in x["horses"]:
        tot += 1; xi = li = 0.0
        c = code_of.get((x["date"], x["race"], str(h["n"])))
        if x.get("venue") == "跑馬地" and c in runs:
            prev = [t for t in runs[c] if t[0] < x["date"]]
            if prev and len(prev) <= MAX_STARTS and not any(t[1] == "HV" for t in prev):
                xi = 1.0; li = float(prev[-1][1] == "ST")
        cnt += xi; cnt2 += li; xs.append(xi); ls.append(li)
    X[id(x)] = np.array(xs); LAST_ST[id(x)] = np.array(ls)
print("馬次", tot, "X", int(cnt), "X且上仗田草", int(cnt2), flush=True)
by = defaultdict(list)
for x in rows: by[season(x["date"])].append(x)
def fit(races):
    R, Z, Y = [], [], []
    for x in races:
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
        r = np.array([h["raw"] for h in x["horses"]])
        R.append((r - r.mean())[keep]); Z.append(X[id(x)][keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
    R, Z = np.concatenate(R), np.concatenate(Z)
    c = LogisticRegression(C=1e6, max_iter=20000, solver="newton-cg").fit(np.column_stack([R / R.std(), Z]), Y).coef_[0]
    return c[1] / (c[0] / R.std())
betas = {s: fit([x for t in by if 2019 <= t < s for x in by[t]]) for s in sorted(by) if s >= 2020}
betas[max(by) + 1] = fit([x for t in by if 2019 <= t for x in by[t]])
print("F1 β", {s: round(float(v), 2) for s, v in betas.items()}, flush=True)
for arm in ("F1", "F2"):
    with open(f"{sys.argv[2]}_{arm}.jsonl", "w") as f:
        for x in rows:
            y = dict(x, arm=f"first_hv_{arm}")
            add = X[id(x)] * betas[season(x["date"])] if arm == "F1" and season(x["date"]) in betas else \
                  (-ST_TO_HV * X[id(x)] * LAST_ST[id(x)] if arm == "F2" else None)
            if add is not None:
                add = add - add.mean()
                y["horses"] = [dict(h, raw=round(h["raw"] + float(v), 4)) for h, v in zip(x["horses"], add)]
                y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
