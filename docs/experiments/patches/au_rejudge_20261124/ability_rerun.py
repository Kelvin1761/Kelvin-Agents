#!/usr/bin/env python3
"""EXP-20261124-22 重跑 EXP-20261122-07（base = 真 live dump）。 run.py FEATS.json OUT.json"""
import importlib.util, json, sys
from pathlib import Path
import numpy as np
S = Path(__file__).resolve().parent
ARGV = list(sys.argv[1:])
spec = importlib.util.spec_from_file_location("live", S / "live_lib.py"); M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
LIVE, base, by, L, J = M.LIVE, M.base, M.by, M.L, M.J
F = json.loads(Path(ARGV[0]).read_text())
rows_fq = [x["features"]["form_quality_score"] for r in base for x in r["rows"]]
fq_m, fq_s = float(np.mean(rows_fq)), float(np.std(rows_fq))
pz = {}
for k in ("PR1", "PR2", "PR3"):
    v = np.array([F[key][k] for key in F], float); pz[k] = (float(v.mean()), float(v.std()))
print("FQ mean/sd", round(fq_m, 3), round(fq_s, 3), "PR mean/sd", {k: [round(a, 2) for a in v] for k, v in pz.items()}, flush=True)
def pr(r, x, k):
    v = F.get(f"{r['meeting']}|{r['race']}|{x['n']}", {}).get(k)
    return None if v is None else fq_m + fq_s * (v - pz[k][0]) / pz[k][1]
def fixed(k):
    out = []
    for i, r in enumerate(base):
        new = []
        for x, lx in zip(r["rows"], LIVE[i]["rows"]):
            p = pr(r, x, k)
            if p is None:
                new.append(lx); continue
            f0 = x["features"]; f1 = dict(f0, form_quality_score=max(0.0, min(100.0, 0.5 * f0["form_quality_score"] + 0.5 * p)))
            new.append(dict(lx, ability=lx["ability"] - J.compose(f0) + J.compose(f1)))
        out.append(dict(LIVE[i], rows=new))
    return out
def wf():
    def prep(i):
        r = base[i]; lv = LIVE[i]
        a = np.array([lx["ability"] - J.compose(x["features"]) + J.compose(dict(x["features"], form_quality_score=60.0))
                      for x, lx in zip(r["rows"], lv["rows"])])
        X = np.array([[x["features"]["form_quality_score"], pr(r, x, "PR2") if pr(r, x, "PR2") is not None else np.nan] for x in r["rows"]], float)
        for c in range(2):
            col = X[:, c]; m = np.nanmean(col) if np.isfinite(col).any() else 0.0; col[~np.isfinite(col)] = m; X[:, c] = col - col.mean()
        return a, X
    samples = []; out = [None] * len(base); betas = []
    for k, d in enumerate(sorted(by)):
        th = J.fit(samples) if k >= 20 and samples else None
        beta = np.clip(th[2:] / th[1], -3, 3) if th is not None and th[1] > 0 else None
        if beta is not None: betas.append(beta)
        for i in by[d]:
            a, X = prep(i)
            out[i] = LIVE[i] if beta is None else dict(LIVE[i], rows=[dict(lx, ability=float(v)) for lx, v in zip(LIVE[i]["rows"], a + X @ beta)])
        for i in by[d]:
            a, X = prep(i); ac = a - a.mean(); y = [int(x["pos"] <= 3) for x in base[i]["rows"]]
            samples += [[ac[j], *X[j], y[j]] for j in range(len(y))]
    print("S4 beta median [近績質素分, PR2分]", np.median(np.array(betas), 0).round(3).tolist(), flush=True)
    return out
arms = {"S1": fixed("PR2"), "S2": fixed("PR3"), "S3": fixed("PR1"), "S4": wf()}
out = {}
import collections
for name, cand in arms.items():
    v = L.evaluate(LIVE, cand, nnull=100)
    cb, cc = L.calibrations(LIVE), L.calibrations(cand); rr = []
    for b_, c_ in zip(LIVE, cand):
        if b_["date"] in cb:
            lb, nn = L._nll(b_, cb[b_["date"]]); lc, _ = L._nll(c_, cc[c_["date"]]); rr.append((b_["date"], lc - lb, nn))
    byd = collections.defaultdict(list)
    for ii, q in enumerate(rr):
        byd[q[0]].append(ii)
    days = sorted(byd); dl = np.array([q[1] for q in rr]); nnn = np.array([q[2] for q in rr]); rng = np.random.default_rng(0); bs = []
    for _ in range(2000):
        jj = np.concatenate([byd[days[q]] for q in rng.integers(0, len(days), len(days))]); bs.append(dl[jj].sum() / nnn[jj].sum())
    v["p"] = float((np.array(bs) >= 0).mean()); out[name] = v
    print(name, v["verdict"], v["reason"], [round(t, 6) for t in v["dlogloss"]], "p", v["p"], "G", [round(t, 2) for t in v["gold_pp"]],
          "Gd", [round(t, 2) for t in v["good_pp"]], "cap5", round(v["capture5_pp"], 2), "top2any", round(v["top2_any_hit_pp"], 2), flush=True)
ps = sorted((v["p"], k) for k, v in out.items())
for rank, (p, k) in enumerate(ps):
    out[k]["holm_p"] = min(1.0, max(min(1.0, (len(ps) - j) * ps[j][0]) for j in range(rank + 1)))
print({k: round(v["holm_p"], 4) for k, v in out.items()})
json.dump(out, open(ARGV[1], "w"), ensure_ascii=False, indent=1, default=float)
