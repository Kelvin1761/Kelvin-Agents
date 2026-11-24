#!/usr/bin/env python3
"""EXP-20261124-50 判決（見 PROTOCOL.md）。 judge.py BASE.json EVENTS.json OUT.json"""
import bisect, collections, importlib.util, json, sys
from pathlib import Path
import numpy as np
S = Path(__file__).resolve().parent
SC = S.parents[3] / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SC)); sys.path.insert(0, str(SC.parents[2] / "shared_racing"))
import au_logloss_ruler as L  # noqa: E402
spec = importlib.util.spec_from_file_location("prj", S.parent / "au_perf_rating/judge.py"); PJ = importlib.util.module_from_spec(spec); spec.loader.exec_module(PJ)
K, CUT = 10, "2026-08-05"
base = L.eligible(json.loads(Path(sys.argv[1]).read_text())["races"])
E = json.loads(Path(sys.argv[2]).read_text())
ev = E["events"]
pre = [e for e in ev if e[0] < CUT]
p0 = sum(e[2] for e in pre) / len(pre)
by_tr = collections.defaultdict(list)            # 練馬師 → [(日期, 入位)]，已排序
for d, tr, p in ev:
    by_tr[tr].append((d, p))
dates_tr = {tr: [d for d, _ in v] for tr, v in by_tr.items()}
cum_tr = {tr: np.concatenate([[0], np.cumsum([p for _, p in v])]) for tr, v in by_tr.items()}

def rate(tr, date):
    if not tr or tr not in by_tr:
        return p0
    i = bisect.bisect_left(dates_tr[tr], date)    # 只計賽日之前
    return (cum_tr[tr][i] + p0 * K) / (i + K)

pre_r = [rate(tr, d) for d, tr, _ in pre]
mu, sd = float(np.mean(pre_r)), float(np.std(pre_r))
print(f"p0 {p0:.4f} z mean {mu:.4f} sd {sd:.4f} (pre {len(pre)})", flush=True)

def zvec(r):
    z, isd = [], []
    for x in r["rows"]:
        key = f"{r['meeting']}|{r['race']}|{x['n']}"
        d = E["debut"].get(key, 0)
        isd.append(d)
        z.append((rate(E["trainer"].get(key), r["date"]) - mu) / sd if d else 0.0)
    z = np.array(z, float)
    if any(isd):
        z = z - z.mean()
    return z, sum(isd)

Z, ND = zip(*[zvec(r) for r in base])
print("races", len(base), "with debut", sum(1 for n in ND if n), "debut runners", sum(ND), flush=True)
by = collections.defaultdict(list)
for i, r in enumerate(base):
    by[r["date"]].append(i)
samples, cand, bl = [], [None] * len(base), []
for j, d in enumerate(sorted(by)):
    beta = PJ.fit(samples) if j >= 20 and samples else 0.0
    if j >= 20: bl.append(beta)
    for i in by[d]:
        r = base[i]; cand[i] = dict(r, rows=[dict(x, ability=float(x["ability"] + beta * q)) for x, q in zip(r["rows"], Z[i])])
    for i in by[d]:
        r = base[i]; a = np.array([x["ability"] for x in r["rows"]]); ac = a - a.mean()
        samples += [(ac[q], Z[i][q], int(x["pos"] <= 3)) for q, x in enumerate(r["rows"]) if ND[i]]

def judge(b, c, tag):
    v = L.evaluate(b, c, nnull=200)
    print(tag, v["verdict"], v["reason"], [round(t, 6) for t in v["dlogloss"]], "G", [round(t, 2) for t in v["gold_pp"]],
          "Gd", [round(t, 2) for t in v["good_pp"]], "cap5", round(v["capture5_pp"], 2), "top2", round(v["top2_any_hit_pp"], 2),
          v["checks"], flush=True)
    return v

out = {"beta_median": float(np.median(bl)), "beta_last": float(bl[-1]) if bl else None, "p0": p0, "z_mean": mu, "z_sd": sd}
print("β median", round(out["beta_median"], 3), "last", round(out["beta_last"] or 0, 3), flush=True)
out["DT"] = judge(base, cand, "DT 全語料")
idx = [i for i in range(len(base)) if ND[i]]
out["DT_debut_races"] = judge([base[i] for i in idx], [cand[i] for i in idx], "DT 有初出馬場（唔係閘）")

def debut_auc(races):
    num = den = 0.0
    for r in races:
        rows = [x for x in r["rows"] if E["debut"].get(f"{r['meeting']}|{r['race']}|{x['n']}", 0)]
        pos = [x["ability"] for x in rows if x["pos"] <= 3]; neg = [x["ability"] for x in rows if x["pos"] > 3]
        for p in pos:
            for q in neg:
                num += (p > q) + 0.5 * (p == q); den += 1
    return num / den if den else None
out["debut_auc"] = [debut_auc(base), debut_auc(cand)]
print("初出馬之間 AUC base→DT", [round(x, 4) for x in out["debut_auc"]], flush=True)
Path(sys.argv[3]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))
