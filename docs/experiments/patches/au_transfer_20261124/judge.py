#!/usr/bin/env python3
"""EXP-20261124-30 判決（見 PROTOCOL.md）。 judge.py BASE.json FEATS.json OUT.json"""
import collections, importlib.util, json, sys
from pathlib import Path
import numpy as np
S = Path(__file__).resolve().parent
SC = S.parents[3] / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SC)); sys.path.insert(0, str(SC.parents[2] / "shared_racing"))
import au_logloss_ruler as L  # noqa: E402
spec = importlib.util.spec_from_file_location("prj", S.parent / "au_perf_rating/judge.py"); PJ = importlib.util.module_from_spec(spec); spec.loader.exec_module(PJ)
base = L.eligible(json.loads(Path(sys.argv[1]).read_text())["races"]); F = json.loads(Path(sys.argv[2]).read_text())
by = collections.defaultdict(list)
for i, r in enumerate(base):
    by[r["date"]].append(i)
def fv(r, k):
    v = np.array([F.get(f"{r['meeting']}|{r['race']}|{x['n']}", {}).get(k, 0) for x in r["rows"]], float); return v - v.mean()
out = {}
for k in ("V2", "T1", "T2"):
    samples, cand, bl = [], [None] * len(base), []
    for j, d in enumerate(sorted(by)):
        beta = PJ.fit(samples) if j >= 20 and samples else 0.0
        if j >= 20: bl.append(beta)
        for i in by[d]:
            r = base[i]; v = fv(r, k)
            cand[i] = dict(r, rows=[dict(x, ability=float(x["ability"] + beta * q)) for x, q in zip(r["rows"], v)])
        for i in by[d]:
            r = base[i]; v = fv(r, k); a = np.array([x["ability"] for x in r["rows"]]); ac = a - a.mean()
            samples += [(ac[q], v[q], int(x["pos"] <= 3)) for q, x in enumerate(r["rows"])]
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
    v["p"] = float((np.array(bs) >= 0).mean()); v["beta_median"] = float(np.median(bl)); v["flagged"] = int(sum(F[f].get(k, 0) for f in F)); out[k] = v
    print(k, "flagged", v["flagged"], v["verdict"], v["reason"], [round(t, 6) for t in v["dlogloss"]], "p", v["p"], "β", round(v["beta_median"], 3),
          "G", [round(t, 2) for t in v["gold_pp"]], "Gd", [round(t, 2) for t in v["good_pp"]], "top2any", round(v["top2_any_hit_pp"], 2), flush=True)
ps = sorted((v["p"], k) for k, v in out.items())
for rank, (p, k) in enumerate(ps):
    out[k]["holm_p"] = min(1.0, max(min(1.0, (len(ps) - j) * ps[j][0]) for j in range(rank + 1)))
print({k: round(v["holm_p"], 4) for k, v in out.items()})
Path(sys.argv[3]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))
