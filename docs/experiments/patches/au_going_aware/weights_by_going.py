#!/usr/bin/env python3
"""EXP-20261121-39 B 組：軟地／大爛地各自維度權重（walk-forward，L2 5.0）。  weights_by_going.py BASE.json OUT.json"""
import collections, json, statistics, sys
from pathlib import Path
import numpy as np
W = Path(__file__).resolve().parents[4]
SCRIPTS = W / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SCRIPTS.parents[2] / "shared_racing"))
import au_logloss_ruler as L  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402

DIMS = list(MATRIX_WEIGHTS); L2 = 5.0; MIN_RACES = 50


def family(r):
    g = str(r["rows"][0].get("going") or "")
    return "Heavy" if "Heavy" in g else "Soft" if "Soft" in g else "other"


def design(r):
    dims = [map_features_to_matrix_scores(x["features"]) for x in r["rows"]]
    D = np.array([[d.get(k, 60.0) for k in DIMS] for d in dims], float)
    D = (D - D.mean(0)) / 10.0
    a = np.array([x["ability"] for x in r["rows"]], float)
    return a - a.mean(), D, np.array([int(x["pos"] <= 3) for x in r["rows"]])


def fit(A, D, Y):
    V = np.column_stack([np.ones(len(A)), A, D]); th = np.zeros(V.shape[1])
    P = np.eye(V.shape[1]) * L2; P[0, 0] = P[1, 1] = 0.0
    for _ in range(60):
        p = 1 / (1 + np.exp(-np.clip(V @ th, -30, 30))); w = p * (1 - p)
        g = V.T @ (Y - p) - P @ th; H = (V * w[:, None]).T @ V + P
        st = np.linalg.solve(H, g); th += st
        if np.abs(st).max() < 1e-8:
            break
    return th[1], th[2:]


def arm(base, fams):
    by = collections.defaultdict(list)
    for i, r in enumerate(base):
        by[r["date"]].append(i)
    hist = {f: [] for f in fams}; out = list(base); coefs = []
    for d in sorted(by):
        for f in fams:
            idx = [i for i in by[d] if family(base[i]) == f]
            if not idx:
                continue
            if len(hist[f]) >= MIN_RACES:
                A = np.concatenate([h[0] for h in hist[f]]); D = np.vstack([h[1] for h in hist[f]]); Y = np.concatenate([h[2] for h in hist[f]])
                b, c = fit(A, D, Y)
                if b > 0:
                    coefs.append((f, d, (c / b).tolist()))
                    for i in idx:
                        _a, Dm, _y = design(base[i]); adj = Dm @ (c / b)
                        out[i] = dict(base[i], rows=[dict(x, ability=x["ability"] + float(v)) for x, v in zip(base[i]["rows"], adj)])
            for i in idx:
                hist[f].append(design(base[i]))
    return out, coefs


def subset_gg(base, cand, f):
    g = gd = n = 0
    for b, c in zip(base, cand):
        if family(b) == f:
            mb, mc = L._metrics(b), L._metrics(c); g += mc[0] - mb[0]; gd += mc[1] - mb[1]; n += 1
    return round(100 * g / max(1, n), 2), round(100 * gd / max(1, n), 2), n


def main():
    base = L.eligible(json.loads(Path(sys.argv[1]).read_text())["races"]); out = {}
    for name, fams in (("WS", ["Soft"]), ("WH", ["Heavy"]), ("WSH", ["Soft", "Heavy"])):
        cand, coefs = arm(base, fams)
        v = L.evaluate(base, cand, nnull=100)
        v["soft_gold_good"] = subset_gg(base, cand, "Soft"); v["heavy_gold_good"] = subset_gg(base, cand, "Heavy")
        last = {}
        for f, d, c in coefs:
            last[f] = dict(zip(DIMS, [round(x * 10, 3) for x in c]))   # 每維度分（未除 10）嘅加減
        v["final_adjust_per_point"] = last
        out[name] = v
        print(name, v["verdict"], v["reason"], [round(t, 6) for t in v["dlogloss"]], "null", v["beats_null_share"],
              "G/G", [round(t, 2) for t in v["gold_pp"]], [round(t, 2) for t in v["good_pp"]],
              "soft", v["soft_gold_good"], "heavy", v["heavy_gold_good"], flush=True)
        print("   final", last, flush=True)
    Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
