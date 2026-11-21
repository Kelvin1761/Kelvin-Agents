#!/usr/bin/env python3
"""EXP-20261121-39 B2（改正版）：軟地／大爛地各自維度倍數，向現行權重收縮。  weights_by_going_b2.py BASE.json OUT.json"""
import collections, json, sys
from pathlib import Path
import numpy as np
W = Path(__file__).resolve().parents[4]
SCRIPTS = W / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SCRIPTS.parents[2] / "shared_racing"))
import au_logloss_ruler as L  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402

DIMS = list(MATRIX_WEIGHTS); WD = np.array([MATRIX_WEIGHTS[k] for k in DIMS]); L2 = 5.0; MIN_RACES = 50


def family(r):
    g = str(r["rows"][0].get("going") or "")
    return "Heavy" if "Heavy" in g else "Soft" if "Soft" in g else "other"


def parts(r):
    D = np.array([[map_features_to_matrix_scores(x["features"]).get(k, 60.0) for k in DIMS] for x in r["rows"]], float)
    contrib = D * WD                                  # w_d × 維度_d
    a = np.array([x["ability"] for x in r["rows"]], float)
    rest = a - contrib.sum(1)                         # overlay 等
    X = np.column_stack([contrib - contrib.mean(0), rest - rest.mean()])
    return X, a - a.mean(), np.array([int(x["pos"] <= 3) for x in r["rows"]])


def logit(V, Y, prior, pen):
    th = np.r_[0.0, prior].astype(float); P = np.diag(np.r_[0.0, np.full(len(prior), pen)])
    p0 = np.r_[0.0, prior]
    for _ in range(80):
        p = 1 / (1 + np.exp(-np.clip(np.column_stack([np.ones(len(V)), V]) @ th, -30, 30))); w = p * (1 - p)
        Vv = np.column_stack([np.ones(len(V)), V])
        g = Vv.T @ (Y - p) - P @ (th - p0); H = (Vv * w[:, None]).T @ Vv + P
        st = np.linalg.solve(H, g); th += st
        if np.abs(st).max() < 1e-9:
            break
    return th[1:]


def arm(base, fams):
    by = collections.defaultdict(list)
    for i, r in enumerate(base):
        by[r["date"]].append(i)
    allA, allY = [], []; hist = {f: [] for f in fams}; out = list(base); last = {}
    for d in sorted(by):
        alpha = logit(np.concatenate(allA)[:, None], np.concatenate(allY), np.array([0.0]), 0.0)[0] if allA else None
        for f in fams:
            idx = [i for i in by[d] if family(base[i]) == f]
            if idx and alpha and alpha > 0 and len(hist[f]) >= MIN_RACES:
                X = np.vstack([h[0] for h in hist[f]]); Y = np.concatenate([h[2] for h in hist[f]])
                beta = logit(X, Y, np.full(X.shape[1], alpha), L2)     # 收縮向「現行權重」（倍數 1）
                mult = beta / alpha; last[f] = dict(zip(DIMS + ["rest"], np.round(mult, 3).tolist()))
                for i in idx:
                    Xi, ac, _y = parts(base[i]); new = Xi @ mult
                    out[i] = dict(base[i], rows=[dict(x, ability=x["ability"] - float(o) + float(n))
                                                 for x, o, n in zip(base[i]["rows"], ac, new)])
            for i in idx:
                hist[f].append(parts(base[i]))
        for i in by[d]:
            _X, ac, y = parts(base[i]); allA.append(ac); allY.append(y)
    return out, last


def subset_gg(base, cand, f):
    g = gd = n = 0
    for b, c in zip(base, cand):
        if family(b) == f:
            mb, mc = L._metrics(b), L._metrics(c); g += mc[0] - mb[0]; gd += mc[1] - mb[1]; n += 1
    return round(100 * g / max(1, n), 2), round(100 * gd / max(1, n), 2), n


def main():
    base = L.eligible(json.loads(Path(sys.argv[1]).read_text())["races"]); out = {}
    for name, fams in (("B2S", ["Soft"]), ("B2H", ["Heavy"]), ("B2SH", ["Soft", "Heavy"])):
        cand, last = arm(base, fams)
        v = L.evaluate(base, cand, nnull=100)
        v["soft_gold_good"] = subset_gg(base, cand, "Soft"); v["heavy_gold_good"] = subset_gg(base, cand, "Heavy"); v["final_multipliers"] = last
        out[name] = v
        print(name, v["verdict"], v["reason"], [round(t, 6) for t in v["dlogloss"]], "null", v["beats_null_share"],
              "G/G", [round(t, 2) for t in v["gold_pp"]], [round(t, 2) for t in v["good_pp"]],
              "soft", v["soft_gold_good"], "heavy", v["heavy_gold_good"], flush=True)
        print("   multipliers", last, flush=True)
    Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
