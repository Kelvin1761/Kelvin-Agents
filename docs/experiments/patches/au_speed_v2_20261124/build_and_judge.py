#!/usr/bin/env python3
"""EXP-20261124-40（見 PROTOCOL.md）。 build_and_judge.py BASE.json OUT.json"""
import collections, importlib.util, json, sys
from pathlib import Path
import numpy as np
S = Path(__file__).resolve().parent
SC = S.parents[3] / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SC)); sys.path.insert(0, str(SC.parents[1])); sys.path.insert(0, str(SC.parents[2] / "shared_racing"))
import au_logloss_ruler as L  # noqa: E402
import au_speed_venue_audit as A  # noqa: E402
from au_leaf_power import norm  # noqa: E402
spec = importlib.util.spec_from_file_location("prj", S.parent / "au_perf_rating/judge.py"); PJ = importlib.util.module_from_spec(spec); spec.loader.exec_module(PJ)

ROOT = Path("/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/AU_Racing")
base = L.eligible(json.loads(Path(sys.argv[1]).read_text())["races"])
obs, conflicts = A.collect_reference_races(ROOT)
stds = A.build_asof_standards(obs, sorted({r["date"] for r in base}))
speed = {}
for race in A.load_races(ROOT, "2026-08-05", stds):
    for ru in race["runners"]:
        speed[(race["date"], race["race"], ru["key"])] = ru["speed"]
print("reference races", len(obs), "conflicts", conflicts, "runner keys", len(speed), flush=True)

def zvec(r):
    v = [speed.get((r["date"], r["race"], norm(x.get("name") or ""))) for x in r["rows"]]
    return np.array(A._zs(v), float), sum(x is not None for x in v)

Z, cov, tot = [], 0, 0
for r in base:
    z, c = zvec(r); Z.append(z); cov += c; tot += len(r["rows"])
print("speed coverage", cov, tot, round(cov / tot, 3), flush=True)
by = collections.defaultdict(list)
for i, r in enumerate(base):
    by[r["date"]].append(i)

def fixed(k):
    return [dict(r, rows=[dict(x, ability=float(x["ability"] + k * q)) for x, q in zip(r["rows"], Z[i])]) for i, r in enumerate(base)]

def wf():
    samples, cand, bl = [], [None] * len(base), []
    for j, d in enumerate(sorted(by)):
        beta = PJ.fit(samples) if j >= 20 and samples else 0.0
        if j >= 20: bl.append(beta)
        for i in by[d]:
            r = base[i]; cand[i] = dict(r, rows=[dict(x, ability=float(x["ability"] + beta * q)) for x, q in zip(r["rows"], Z[i])])
        for i in by[d]:
            r = base[i]; a = np.array([x["ability"] for x in r["rows"]]); ac = a - a.mean()
            samples += [(ac[q], Z[i][q], int(x["pos"] <= 3)) for q, x in enumerate(r["rows"])]
    return cand, float(np.median(bl))

out = {}
s2, b2 = wf()
for name, cand in (("S1", fixed(0.5)), ("S2", s2)):
    v = L.evaluate(base, cand, nnull=100)
    cb, cc = L.calibrations(base), L.calibrations(cand); rr = []
    for b_, c_ in zip(base, cand):
        if b_["date"] in cb:
            lb, nn = L._nll(b_, cb[b_["date"]]); lc, _ = L._nll(c_, cc[c_["date"]]); rr.append((b_["date"], lc - lb, nn))
    byd = collections.defaultdict(list)
    for ii, q in enumerate(rr):
        byd[q[0]].append(ii)
    days = sorted(byd); dl = np.array([q[1] for q in rr]); nnn = np.array([q[2] for q in rr]); rng = np.random.default_rng(0); bs = []
    for _ in range(2000):
        jj = np.concatenate([byd[days[q]] for q in rng.integers(0, len(days), len(days))]); bs.append(dl[jj].sum() / nnn[jj].sum())
    v["p"] = float((np.array(bs) >= 0).mean())
    if name == "S2": v["beta_median"] = b2
    out[name] = v
    print(name, v["verdict"], v["reason"], [round(t, 6) for t in v["dlogloss"]], "p", v["p"], "β", round(v.get("beta_median", 0.5), 3),
          "G", [round(t, 2) for t in v["gold_pp"]], "Gd", [round(t, 2) for t in v["good_pp"]], "cap5", round(v["capture5_pp"], 2),
          "top2any", round(v["top2_any_hit_pp"], 2), "checks", v["checks"], flush=True)
ps = sorted((v["p"], k) for k, v in out.items())
for rank, (p, k) in enumerate(ps):
    out[k]["holm_p"] = min(1.0, max(min(1.0, (len(ps) - j) * ps[j][0]) for j in range(rank + 1)))
print({k: round(v["holm_p"], 4) for k, v in out.items()})
Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))
