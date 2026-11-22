#!/usr/bin/env python3
"""EXP-20261122-05 判決（見 PROTOCOL.md）。 judge.py BASE.json feats.json OUT.json"""
import collections, json, sys
from pathlib import Path
import numpy as np
SC = Path(__file__).resolve().parents[4] / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SC)); sys.path.insert(0, str(SC.parents[2] / "shared_racing"))
import au_logloss_ruler as L  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import compose_matrix_score  # noqa: E402


def fit(S):
    X = np.array(S, float); a = b = c = 0.0
    for _ in range(60):
        p = 1 / (1 + np.exp(-np.clip(a + b * X[:, 0] + c * X[:, 1], -30, 30))); w = p * (1 - p)
        V = np.column_stack([np.ones(len(X)), X[:, 0], X[:, 1]])
        try:
            st = np.linalg.solve((V * w[:, None]).T @ V, V.T @ (X[:, 2] - p))
        except np.linalg.LinAlgError:
            return 0.0
        a, b, c = a + st[0], b + st[1], c + st[2]
        if np.abs(st).max() < 1e-8:
            break
    return float(max(-3, min(3, c / b))) if b > 0 else 0.0


def compose(f):
    return compose_matrix_score(map_features_to_matrix_scores(f))


def main():
    base = L.eligible(json.loads(Path(sys.argv[1]).read_text())["races"]); F = json.loads(Path(sys.argv[2]).read_text())
    by = collections.defaultdict(list)
    for i, r in enumerate(base):
        by[r["date"]].append(i)
    def featvec(r, key):
        v = np.array([F.get(f"{r['meeting']}|{r['race']}|{x['n']}", {}).get(key, np.nan) for x in r["rows"]], float)
        m = np.nanmean(v) if np.isfinite(v).any() else 0.0; v[~np.isfinite(v)] = m; return v - v.mean()
    no_fq = [[x["ability"] - compose(x["features"]) + compose(dict(x["features"], form_quality_score=60.0)) for x in r["rows"]] for r in base]
    out = {}; betas = {}
    for name, key, replace in (("PR1", "PR1", False), ("PR2", "PR2", False), ("PR3", "PR3", False), ("PR4", "PR2", True)):
        samples = []; cand = [None] * len(base); bl = []
        for k, d in enumerate(sorted(by)):
            beta = fit(samples) if k >= 20 and samples else 0.0
            if k >= 20: bl.append(beta)
            for i in by[d]:
                r = base[i]; fv = featvec(r, key)
                b0 = np.array(no_fq[i] if replace and beta else [x["ability"] for x in r["rows"]])
                cand[i] = dict(r, rows=[dict(x, ability=float(a + beta * v)) for x, a, v in zip(r["rows"], b0, fv)])
            for i in by[d]:
                r = base[i]; fv = featvec(r, key); a = np.array(no_fq[i] if replace else [x["ability"] for x in r["rows"]]); ac = a - a.mean()
                samples += [(ac[j], fv[j], int(x["pos"] <= 3)) for j, x in enumerate(r["rows"])]
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
        v["p"] = float((np.array(bs) >= 0).mean()); v["beta_median"] = float(np.median(bl)); out[name] = v
        print(name, v["verdict"], v["reason"], [round(t, 6) for t in v["dlogloss"]], "p", v["p"], "β", round(v["beta_median"], 3),
              "G/G", [round(t, 2) for t in v["gold_pp"]], [round(t, 2) for t in v["good_pp"]], "top2any", round(v["top2_any_hit_pp"], 2), flush=True)
    ps = sorted((v["p"], k) for k, v in out.items())
    for rank, (p, k) in enumerate(ps):
        out[k]["holm_p"] = min(1.0, max(min(1.0, (len(ps) - j) * ps[j][0]) for j in range(rank + 1)))
    print({k: round(v["holm_p"], 4) for k, v in out.items()})
    Path(sys.argv[3]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
