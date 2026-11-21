#!/usr/bin/env python3
"""EXP-20261121-38 大爛地 overlay 篩選（見 PROTOCOL.md）。  run.py BASE.json OUT.json"""
import collections, json, statistics, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))
import au_logloss_ruler as L  # noqa: E402

LEAVES = ["class_score", "confidence_score", "consistency_score", "distance_score", "form_quality_score", "form_score",
          "formline_score", "health_score", "jockey_horse_fit_score", "jockey_score", "pace_figure_score", "pace_map_score",
          "performance_quality_score", "preparation_score", "rating_score", "sectional_score", "track_score", "trainer_score",
          "trial_score", "trial_speed_score", "weight_score"]


def heavy(r):
    return "Heavy" in str(r["rows"][0].get("going") or "")


def value(x, key, r):
    if key == "wet":
        return float(x.get("wet") or 0.0)
    if key == "FRONT":
        s = str(x.get("style") or "")
        return float(any(t in s for t in ("前置", "前領", "跟前")))
    if key == "BARRIER":
        b = x.get("barrier")
        return float(b) / max(1, len(r["rows"])) if isinstance(b, (int, float)) else 0.0
    return float((x.get("features") or {}).get(key, 60.0))


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
    return float(max(-1.5, min(1.5, c / b))) if b > 0 else 0.0


def arm(base, key):
    samples, nheavy, cand, betas = [], 0, [], []
    by = collections.defaultdict(list)
    for i, r in enumerate(base):
        by[r["date"]].append(i)
    out = list(base)
    for d in sorted(by):
        idx = [i for i in by[d] if heavy(base[i])]
        beta = fit(samples) if nheavy >= 30 else 0.0
        for i in idx:
            r = base[i]; vals = [value(x, key, r) for x in r["rows"]]; m = statistics.mean(vals)
            out[i] = dict(r, rows=[dict(x, ability=x["ability"] + beta * (v - m)) for x, v in zip(r["rows"], vals)])
            betas.append(beta)
        for i in idx:
            r = base[i]; vals = [value(x, key, r) for x in r["rows"]]; m = statistics.mean(vals)
            ma = statistics.mean(x["ability"] for x in r["rows"])
            samples += [(x["ability"] - ma, v - m, int(x["pos"] <= 3)) for x, v in zip(r["rows"], vals)]
            nheavy += 1
    return out, betas


def pvalue(base, cand):
    cb, cc = L.calibrations(base), L.calibrations(cand); rows = []
    for b, c in zip(base, cand):
        if b["date"] in cb:
            lb, n = L._nll(b, cb[b["date"]]); lc, _ = L._nll(c, cc[c["date"]]); rows.append((b["date"], lc - lb, n))
    by = collections.defaultdict(list)
    for i, r in enumerate(rows):
        by[r[0]].append(i)
    days = sorted(by); dl = np.array([r[1] for r in rows]); nn = np.array([r[2] for r in rows]); rng = np.random.default_rng(0); bs = []
    for _ in range(2000):
        ii = np.concatenate([by[days[j]] for j in rng.integers(0, len(days), len(days))]); bs.append(dl[ii].sum() / nn[ii].sum())
    return float((np.array(bs) >= 0).mean())


def heavy_gg(base, cand):
    g = gd = 0.0; n = 0
    for b, c in zip(base, cand):
        if heavy(b):
            mb, mc = L._metrics(b), L._metrics(c); g += mc[0] - mb[0]; gd += mc[1] - mb[1]; n += 1
    return round(100 * g / n, 2), round(100 * gd / n, 2), n


def main():
    base = L.eligible(json.loads(Path(sys.argv[1]).read_text())["races"])
    out = {}
    for key in LEAVES + ["wet", "FRONT", "BARRIER"]:
        cand, betas = arm(base, key)
        v = L.evaluate(base, cand, nnull=100); v["p"] = pvalue(base, cand)
        nz = [b for b in betas if b]; v["beta_median"] = statistics.median(nz) if nz else 0.0; v["heavy_gold_good"] = heavy_gg(base, cand)
        out[key] = v
        print(key, v["verdict"], v["reason"], [round(t, 6) for t in v["dlogloss"]], "p", v["p"], "β", round(v["beta_median"], 3),
              "heavy G/G", v["heavy_gold_good"], flush=True)
    ps = sorted((v["p"], k) for k, v in out.items()); m = len(ps)
    for rank, (p, k) in enumerate(ps):
        out[k]["holm_p"] = min(1.0, max(min(1.0, (m - j) * ps[j][0]) for j in range(rank + 1)))
        out[k]["final"] = "PASS" if out[k]["verdict"] == "PASS" and out[k]["holm_p"] < 0.05 else "REJECT"
    print({k: (v["final"], round(v["holm_p"], 3)) for k, v in sorted(out.items(), key=lambda kv: kv[1]["holm_p"])})
    Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
