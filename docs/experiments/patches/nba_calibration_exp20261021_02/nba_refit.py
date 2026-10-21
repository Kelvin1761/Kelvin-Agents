#!/usr/bin/env python3
"""EXP-20261021-04 — fitted adjustment layer (analysis only). Protocol frozen in
docs/experiments/EXP-20261021-04-nba-adjustment-layer-refit.md.
  python3 nba_refit.py run --rows OUT3/rows.csv --out OUT4
All fitting uses dev only; H1 and H2 are each evaluated once.
"""
import argparse, json, os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import nba_calib as nc

TERMS = ["trend", "cov", "buffer", "sip_n04", "sip_n01", "b2b", "home_away"]
FEATS = ["lc", "lb"] + ["t_" + t for t in TERMS]      # standardised, penalised
DUMMIES = ["REB", "AST", "FG3M"]
LAMBDAS = [0, 10, 100, 1000, 10000, 100000]
INNER_SPLIT = ("2025-12-01", "2026-01-01")             # validation = [2025-12-01, 2026-01-01)
COEF_BOOT_N = 300
ZONE = 0.70


def sigmoid(z):
    return 1 / (1 + np.exp(-np.clip(z, -35, 35)))


def fit_l2(X, y, w, lam, pen_mask, iters=60):
    beta = np.zeros(X.shape[1])
    P = np.diag(lam * pen_mask.astype(float))
    for _ in range(iters):
        p = sigmoid(X @ beta)
        g = X.T @ (w * (y - p)) - P @ beta
        H = (X * (w * p * (1 - p))[:, None]).T @ X + P + 1e-9 * np.eye(X.shape[1])
        step = np.linalg.solve(H, g)
        beta += step
        if np.max(np.abs(step)) < 1e-8:
            break
    return beta


def base_feats(df, params):
    P = nc.cand_probs(df, params)
    out = pd.DataFrame(index=df.index)
    out["lc"] = nc.logit(P["c"]); out["lb"] = nc.logit(P["b"])
    for t in TERMS:
        out["t_" + t] = df["t_" + t].to_numpy(float)
    return out, P


def design(df, params, scaler):
    F, P = base_feats(df, params)
    Z = (F[FEATS] - scaler["mu"]) / scaler["sd"]
    cols = [np.ones(len(df))] + [Z[c].to_numpy() for c in FEATS] + [(df["stat"] == s).to_numpy().astype(float) for s in DUMMIES]
    return np.column_stack(cols), P


NAMES = ["intercept"] + FEATS + ["d_" + s for s in DUMMIES]
PEN = np.array([0] + [1] * len(FEATS) + [0] * len(DUMMIES))


def fit_scaler(df, params):
    F, _ = base_feats(df, params)
    return {"mu": F[FEATS].mean(), "sd": F[FEATS].std().replace(0, 1.0)}


def recal_fit(df, P, w=None):
    """(A): per-stat a + b*logit(p_c)."""
    out = {}
    for s in nc.STATS:
        mk = (df["stat"] == s).to_numpy()
        x = nc.logit(P["c"][mk]); y = df["y"].to_numpy()[mk].astype(float)
        out[s] = nc.fit_logit(x, y, None if w is None else w[mk])
    return out


def recal_pred(df, P, coef):
    p = np.empty(len(df))
    for s in nc.STATS:
        mk = (df["stat"] == s).to_numpy()
        a, b = coef[s]
        p[mk] = sigmoid(a + b * nc.logit(P["c"][mk]))
    return p


def predict_all(df, params, scaler, models):
    X, P = design(df, params, scaler)
    out = {"a": P["a"], "c": P["c"], "A": recal_pred(df, P, models["A"]),
           "B": sigmoid(X @ models["B"]), "C": sigmoid(X @ models["C"])}
    return out


def fit_models(dev, params, scaler, lam_c):
    X, P = design(dev, params, scaler)
    y = dev["y"].to_numpy().astype(float); w = np.ones(len(dev))
    return {"A": recal_fit(dev, P), "B": fit_l2(X, y, w, 0, PEN), "C": fit_l2(X, y, w, lam_c, PEN)}, (X, P, y)


def choose_lambda(dev, params, scaler):
    tr = dev[dev.date < INNER_SPLIT[0]]; va = dev[(dev.date >= INNER_SPLIT[0]) & (dev.date < INNER_SPLIT[1])]
    Xt, _ = design(tr, params, scaler); Xv, _ = design(va, params, scaler)
    yt = tr["y"].to_numpy().astype(float); yv = va["y"].to_numpy().astype(float)
    res = {}
    for lam in LAMBDAS:
        b = fit_l2(Xt, yt, np.ones(len(tr)), lam, PEN)
        res[lam] = float(nc.brier_loss(sigmoid(Xv @ b), yv).mean())
    best = min(res.values())
    lam = max(l for l, v in res.items() if v <= best + 1e-12)   # tie -> larger lambda
    return lam, res, {"n_train": int(len(tr)), "n_val": int(len(va))}


def raw_coefs(beta, scaler):
    """Standardised -> per-unit coefficients for the 9 features; 'kept' = per-pp / 0.04 for t_* terms."""
    out = {}
    for i, n in enumerate(FEATS, start=1):
        sd = float(scaler["sd"][n]); out[n] = {"std": float(beta[i]), "raw": float(beta[i] / sd)}
        if n.startswith("t_"):
            out[n]["kept"] = float(beta[i] / sd / 0.04)
    return out


def coef_bootstrap(dev, params, scaler, lam_c):
    X, P = design(dev, params, scaler)
    y = dev["y"].to_numpy().astype(float)
    codes = pd.factorize(dev["game_id"] + "|" + dev["season"])[0]; G = codes.max() + 1
    rng = np.random.default_rng(nc.BOOT_SEED)
    cnt = rng.multinomial(G, np.full(G, 1.0 / G), size=COEF_BOOT_N)
    B, C, A = [], [], []
    for r in range(COEF_BOOT_N):
        w = cnt[r][codes].astype(float)
        B.append(fit_l2(X, y, w, 0, PEN)); C.append(fit_l2(X, y, w, lam_c, PEN))
        a = recal_fit(dev, P, w); A.append([v for s in nc.STATS for v in a[s]])
    return np.array(B), np.array(C), np.array(A)


def ci(a):
    return [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))]


def evaluate(df, probs, with_slope_ci=False):
    y = df["y"].to_numpy().astype(float)
    codes = pd.factorize(df["game_id"] + "|" + df["season"])[0]; G = int(codes.max()) + 1
    rng = np.random.default_rng(nc.BOOT_SEED)
    cnt = rng.multinomial(G, np.full(G, 1.0 / G), size=nc.BOOT_N).astype(float)
    scnt = rng.multinomial(G, np.full(G, 1.0 / G), size=300).astype(float) if with_slope_ci else None
    groups = {"pooled": np.ones(len(df), bool)}
    for s in nc.STATS:
        groups[nc.STAT_LABEL[s]] = (df["stat"] == s).to_numpy()
    out = {"n_rows": int(len(df)), "n_games": G, "groups": {}}
    for g, mk in groups.items():
        yb, cb = y[mk], codes[mk]
        L = {k: nc.brier_loss(p[mk], yb) for k, p in probs.items()}
        LL = {k: nc.logloss_loss(p[mk], yb) for k, p in probs.items()}
        R = {}
        for k, p in probs.items():
            a0, b0 = nc.fit_logit(nc.logit(p[mk]), yb)
            e = {"brier": float(L[k].mean()), "logloss": float(LL[k].mean()), "slope": b0, "intercept": a0,
                 "citl": float(nc.clipp(p[mk]).mean() - yb.mean())}
            for ref in ("a", "c"):
                if k != ref:
                    for nm, arr in (("brier", L), ("logloss", LL)):
                        d = arr[k] - arr[ref]
                        sg = np.bincount(cb, weights=d, minlength=G); ng = np.bincount(cb, minlength=G).astype(float)
                        b = (cnt @ sg) / (cnt @ ng)
                        e[f"d_{nm}_vs_{ref}"] = {"diff": float(d.mean()), "lo": ci(b)[0], "hi": ci(b)[1]}
            if with_slope_ci and g == "pooled":
                x = nc.logit(p[mk]); sl = [nc.fit_logit(x, yb, scnt[r][cb])[1] for r in range(300)]
                e["slope_ci"] = ci(sl)
            if g == "pooled":
                e["reliability"] = nc.reliability(p[mk], yb)
                z = nc.clipp(p[mk]) >= ZONE
                e["zone70"] = {"n": int(z.sum()), "share": float(z.mean()),
                               "mean_p": float(nc.clipp(p[mk])[z].mean()) if z.any() else None,
                               "hit": float(yb[z].mean()) if z.any() else None}
            R[k] = e
        out["groups"][g] = R
    return out


def verdict(h1, dev, h2, k):
    c1 = h1["groups"]["pooled"][k]["d_brier_vs_a"]["hi"] < 0
    c2 = dev["groups"]["pooled"][k]["d_brier_vs_a"]["diff"] < 0
    c3 = h2["groups"]["pooled"][k]["d_brier_vs_a"]["hi"] < 0
    sl = h1["groups"]["pooled"][k]["slope"]; c4 = 0.85 <= sl <= 1.15
    rel = h1["groups"]["pooled"][k]["reliability"]
    bad = [(b[0], b[1], b[2], b[3]) for b in rel if b[1] >= 500 and abs(b[2] - b[3]) > 0.05]
    c5 = len(bad) == 0
    return {"c1_H1_ci_below0": bool(c1), "c2_dev_neg": bool(c2), "c3_H2_ci_below0": bool(c3),
            "c4_slope_in_band": bool(c4), "c5_no_bad_bucket": bool(c5), "bad_buckets": bad,
            "verdict": "passes" if all([c1, c2, c3, c4, c5]) else "not shown"}


def shuffle_test(dev, params, scaler):
    rng = np.random.default_rng(nc.BOOT_SEED)
    d = dev.copy()
    for s in nc.STATS:
        mk = d.stat == s
        d.loc[mk, "y"] = rng.permutation(d.loc[mk, "y"].to_numpy())
    X, _ = design(d, params, scaler)
    y = d["y"].to_numpy().astype(float)
    b = fit_l2(X, y, np.ones(len(d)), 0, PEN)
    p = sigmoid(X @ b)
    const = np.empty(len(d))
    for s in nc.STATS:
        mk = (d.stat == s).to_numpy(); const[mk] = y[mk].mean()
    imp = float(nc.brier_loss(const, y).mean() - nc.brier_loss(p, y).mean())
    mx = float(np.max(np.abs(b[1:1 + len(FEATS)])))
    return {"max_abs_std_coef": mx, "insample_brier_gain_vs_stat_const": imp,
            "pass": bool(mx < 0.05 and imp < 0.0005)}


def cmd_run(a):
    rows = pd.read_csv(a.rows, dtype={"game_id": str})
    prim = rows[rows.primary]; s1 = rows[rows.s1]
    sl = lambda pop: (pop[(pop.season == "2025-26") & (pop.date < nc.DEV_END)],
                      pop[(pop.season == "2025-26") & (pop.date >= nc.H1_START)], pop[pop.season == "2024-25"])
    dev, h1, h2 = sl(prim)
    params = nc.tune(dev)
    scaler = fit_scaler(dev, params)
    lam, lam_scores, inner = choose_lambda(dev, params, scaler)
    models, _ = fit_models(dev, params, scaler, lam)
    res = {"params": params, "lambda_C": lam, "lambda_val_brier": {str(k): v for k, v in lam_scores.items()}, "inner": inner,
           "scaler": {"mu": scaler["mu"].to_dict(), "sd": scaler["sd"].to_dict()},
           "coef_full": {"A": {s: list(v) for s, v in models["A"].items()},
                         "B": dict(zip(NAMES, map(float, models["B"]))), "C": dict(zip(NAMES, map(float, models["C"])))},
           "coef_raw": {"B": raw_coefs(models["B"], scaler), "C": raw_coefs(models["C"], scaler)}}
    Bb, Cb, Ab = coef_bootstrap(dev, params, scaler, lam)
    res["coef_ci"] = {"B": {n: ci(Bb[:, i]) for i, n in enumerate(NAMES)}, "C": {n: ci(Cb[:, i]) for i, n in enumerate(NAMES)},
                      "A": {f"{s}_{k}": ci(Ab[:, 2 * j + q]) for j, s in enumerate(nc.STATS) for q, k in enumerate(("a", "b"))},
                      "B_raw_kept": {}, "C_raw_kept": {}}
    for i, n in enumerate(FEATS, start=1):
        if n.startswith("t_"):
            sd = float(scaler["sd"][n])
            res["coef_ci"]["B_raw_kept"][n] = ci(Bb[:, i] / sd / 0.04); res["coef_ci"]["C_raw_kept"][n] = ci(Cb[:, i] / sd / 0.04)
    res["shuffle"] = shuffle_test(dev, params, scaler)
    for pname, pop in (("primary", prim), ("S1", s1)):
        d_, h1_, h2_ = sl(pop)
        W = {}
        for w, df, sc in (("dev", d_, False), ("H1", h1_, True), ("H2", h2_, True)):
            W[w] = evaluate(df, predict_all(df, params, scaler, models), with_slope_ci=sc and pname == "primary")
        res[pname] = {"windows": W}
        if pname == "primary":
            res["verdicts"] = {k: verdict(W["H1"], W["dev"], W["H2"], k) for k in ("c", "A", "B", "C")}
    json.dump(res, open(os.path.join(a.out, "results4.json"), "w"), indent=1, default=float)
    print("saved results4.json; lambda_C", lam, {k: v["verdict"] for k, v in res["verdicts"].items()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run"); r.add_argument("--rows", required=True); r.add_argument("--out", required=True)
    args = ap.parse_args(); os.makedirs(args.out, exist_ok=True); cmd_run(args)
