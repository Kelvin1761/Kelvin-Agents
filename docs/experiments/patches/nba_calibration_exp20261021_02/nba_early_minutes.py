#!/usr/bin/env python3
"""EXP-20261021-07 — early-season minutes calibration (analysis only).
Protocol frozen in docs/experiments/EXP-20261021-07-nba-early-season-minutes-calibration.md.
  python3 nba_early_minutes.py run --rows OUT6/rows.csv --out OUT7
"""
import argparse, json, os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import nba_calib as nc
import nba_early as ne
import nba_pregame as npg
import nba_refit as nr

KMAP = {"PTS": 5, "REB": 40, "AST": 5, "FG3M": 8}      # EXP-06 dev-fitted, frozen (not re-tuned)
SHRINK_UNITS = 100                                       # M2 shrinkage toward M1, pre-registered
STRATA = ["S0", "S1", "S2"]; BUCKETS = ["B1", "B2", "B3"]
CITL_BAND = 0.03


def stratum_of(n):
    return np.where(n == 0, "S0", np.where(n <= 4, "S1", "S2"))


def bucket_of(pm):
    return np.where(pm < 25, "B1", np.where(pm < 30, "B2", "B3"))


def fit_f(dev):
    u = dev.drop_duplicates(["player_id", "game_id"]).copy()
    u["S"] = stratum_of(u["n_cur"].to_numpy()); u["B"] = bucket_of(u["prior_min_mean"].to_numpy())
    m1 = {s: float(g["min_g"].sum() / g["min10"].sum()) for s, g in u.groupby("S")}
    m2 = {}
    for (b, s), g in u.groupby(["B", "S"]):
        n = len(g); raw = float(g["min_g"].sum() / g["min10"].sum())
        m2[(b, s)] = (n * raw + SHRINK_UNITS * m1[s]) / (n + SHRINK_UNITS)
    for b in BUCKETS:
        for s in STRATA:
            m2.setdefault((b, s), m1[s])                  # empty cell -> M1
    return m1, m2


def f_vec(df, m1=None, m2=None):
    S = stratum_of(df["n_cur"].to_numpy()); B = bucket_of(df["prior_min_mean"].to_numpy())
    if m1 is None and m2 is None:
        return np.ones(len(df))
    if m2 is None:
        return np.array([m1[s] for s in S])
    return np.array([m2[(b, s)] for b, s in zip(B, S)])


def mu_blend_f(df, f):
    rp = df["prior_total"].to_numpy() / df["prior_min_total"].to_numpy()
    n = df["n_cur"].to_numpy(float); Mc = df["M_cur"].to_numpy(); Sc = df["S_cur"].to_numpy()
    rc = np.where(Mc > 0, Sc / np.where(Mc > 0, Mc, 1.0), rp)
    k = df["stat"].map(KMAP).to_numpy(float)
    rate = np.where(n + k > 0, (n * rc + k * rp) / np.where(n + k > 0, n + k, 1.0), rp)
    return np.maximum(0.05, rate * df["min10"].to_numpy() * f)


def probs_for(df, model, m1, m2, x1coef, x2coef):
    fz = ne.frozen_coefs(model)
    pc = lambda f: ne.count_p(df, mu_blend_f(df, f), model)
    p0, p1, p2 = pc(np.ones(len(df))), pc(f_vec(df, m1)), pc(f_vec(df, m1, m2))
    return {"a": df["a"].to_numpy(), "c": ne.recal(p0, df, fz), "M1f": ne.recal(p1, df, fz), "M1x": ne.recal(p1, df, x1coef),
            "M2f": ne.recal(p2, df, fz), "M2x": ne.recal(p2, df, x2coef), "E": df["e"].to_numpy()}, {"p1": p1, "p2": p2}


def fit_recal(df, pcount, y=None):
    y = df["y"].to_numpy().astype(float) if y is None else y
    return {s: nc.fit_logit(nc.logit(pcount[(df.stat == s).to_numpy()]), y[(df.stat == s).to_numpy()]) for s in nc.STATS}


def resid_tables(df, p, mask=None):
    """mean(y - p) with cluster-bootstrap CI by stratum S0..S2 and prior-minutes bucket B1..B3."""
    d = df if mask is None else df[mask]; pp = p if mask is None else p[mask]
    codes = pd.factorize(d["game_id"] + "|" + d["season"])[0]; G = int(codes.max()) + 1
    cnt = np.random.default_rng(nc.BOOT_SEED).multinomial(G, np.full(G, 1.0 / G), size=nc.BOOT_N).astype(float)
    resid = d["y"].to_numpy() - pp
    S = stratum_of(d["n_cur"].to_numpy()); B = bucket_of(d["prior_min_mean"].to_numpy())
    out = {"S": {}, "B": {}}
    for fam, arr, names in (("S", S, STRATA), ("B", B, BUCKETS)):
        for nm in names:
            mk = arr == nm
            if mk.sum() == 0:
                continue
            r = np.where(mk, resid, 0.0)
            b = (cnt @ np.bincount(codes, weights=r, minlength=G)) / (cnt @ np.bincount(codes, weights=mk.astype(float), minlength=G))
            out[fam][nm] = {"n": int(mk.sum()), "mean_resid": float(resid[mk].mean()), "ci": nr.ci(b)}
    return out


def minutes_quality(df, m1, m2):
    u = df.drop_duplicates(["player_id", "game_id"]).copy()
    u["S"] = stratum_of(u["n_cur"].to_numpy()); u["B"] = bucket_of(u["prior_min_mean"].to_numpy())
    preds = {"f1": u["min10"].to_numpy(), "M1": u["min10"].to_numpy() * f_vec(u, m1), "M2": u["min10"].to_numpy() * f_vec(u, m1, m2)}
    out = {}
    for fam in ("S", "B"):
        for nm, g in u.groupby(fam):
            ix = u.index.get_indexer(g.index); act = g["min_g"].to_numpy()
            ent = {"n": int(len(g)), "mean_ratio": float(act.mean() / g["min10"].mean())}
            for k, pv in preds.items():
                e = act - pv[ix]; ent[k] = {"bias": float(e.mean()), "mae": float(np.abs(e).mean()), "rmse": float(np.sqrt((e ** 2).mean()))}
            out[f"{fam}:{nm}"] = ent
    return out


def veto(tables):
    bad = [(fam, nm, v["mean_resid"], v["ci"]) for fam in ("S", "B") for nm, v in tables[fam].items()
           if abs(v["mean_resid"]) > CITL_BAND and (v["ci"][0] > 0 or v["ci"][1] < 0)]
    return bad


def level_ok(tbl, keys):
    # citl = mean(p - y) = -mean_resid; require |citl| <= band and CI includes 0
    return all(k in tbl["S"] and abs(tbl["S"][k]["mean_resid"]) <= CITL_BAND and tbl["S"][k]["ci"][0] <= 0 <= tbl["S"][k]["ci"][1] for k in keys)


def verdict(W, tbl, k, subset=False):
    P = lambda w: W[w]["groups"]["pooled"][k]
    c = {"c1_H2_ci_below0": P("H2")["d_brier_vs_a"]["hi"] < 0, "c2_dev_neg": P("dev")["d_brier_vs_a"]["diff"] < 0,
         "c3_H3_ci_below0": P("H3")["d_brier_vs_a"]["hi"] < 0,
         "c4_slope_H2": 0.85 <= P("H2")["slope"] <= 1.15, "c4_slope_H3": 0.85 <= P("H3")["slope"] <= 1.15}
    bad = [b for b in P("H2")["reliability"] if b[1] >= 500 and abs(b[2] - b[3]) > 0.05]
    c["c5_no_bad_bucket_H2"] = not bad
    if not subset:
        c["c6_H2_beats_M0"] = P("H2")["d_brier_vs_c"]["hi"] < 0
    keys = ["S2"] if subset else ["S0", "S1"]
    c["c7_level_H2"] = level_ok(tbl["H2"], keys); c["c7_level_H3"] = level_ok(tbl["H3"], keys)
    vbad = veto(tbl["dev"])
    return {**{x: bool(v) for x, v in c.items()}, "bad_buckets_H2": bad, "veto_buckets_dev": vbad, "veto": bool(vbad),
            "conditions_all": bool(all(c.values())),
            "verdict": ("VETOED" if vbad and all(c.values()) else "passes" if all(c.values()) else "not shown")}


def cmd_run(a):
    rows = pd.read_csv(a.rows, dtype={"game_id": str})
    model, why = ne.fl.load_model(); assert model is not None, why
    r6 = os.path.join(os.path.dirname(a.rows), "results6.json")
    if os.path.exists(r6):
        assert json.load(open(r6))["kmap"] == KMAP
    H = {"dev": rows[(rows.season == "2025-26") & (rows.date < nc.DEV_END)].reset_index(drop=True),
         "H2": rows[rows.season == "2024-25"].reset_index(drop=True), "H3": rows[rows.season == "2023-24"].reset_index(drop=True)}
    dev = H["dev"]
    m1, m2 = fit_f(dev)
    assert np.allclose(mu_blend_f(dev, np.ones(len(dev))), ne.mu_blend(dev, KMAP))
    # parity of frozen artefact call vs harness formula (c0 type mu with minutes factor)
    d0 = dev.head(2000); f0 = f_vec(d0, m1)
    mu0 = np.maximum(0.05, d0["prior_total"].to_numpy() / d0["prior_min_total"].to_numpy() * d0["min10"].to_numpy() * f0)
    ref = ne.recal(ne.count_p(d0, mu0, model), d0, ne.frozen_coefs(model))
    art = np.array([ne.fl.fit_prob_A(r.stat, int(r.line), r.prior_total, r.prior_min_total, r.min10 * f, model=model)[0] for r, f in zip(d0.itertuples(), f0)])
    assert np.abs(ref - art).max() < 1e-9
    # exploratory recalibrations: refit on dev only
    pc1_dev = ne.count_p(dev, mu_blend_f(dev, f_vec(dev, m1)), model); pc2_dev = ne.count_p(dev, mu_blend_f(dev, f_vec(dev, m1, m2)), model)
    x1, x2 = fit_recal(dev, pc1_dev), fit_recal(dev, pc2_dev)
    res = {"m1": m1, "m2": {f"{b}|{s}": v for (b, s), v in m2.items()}, "x1_coef": {s: list(v) for s, v in x1.items()},
           "x2_coef": {s: list(v) for s, v in x2.items()}, "kmap": KMAP, "shrink_units": SHRINK_UNITS,
           "n_rows": {w: int(len(d)) for w, d in H.items()}, "n_units": {w: int(d.drop_duplicates(["player_id", "game_id"]).shape[0]) for w, d in H.items()}}
    # shuffle test
    rng = np.random.default_rng(nc.BOOT_SEED); ys = dev["y"].to_numpy().astype(float).copy()
    for s in nc.STATS:
        mk = (dev.stat == s).to_numpy(); ys[mk] = rng.permutation(ys[mk])
    sh = fit_recal(dev, pc1_dev, y=ys); res["shuffle"] = {"slopes": {s: float(v[1]) for s, v in sh.items()}, "pass": bool(all(abs(v[1]) < 0.10 for v in sh.values()))}
    P = {w: probs_for(d, model, m1, m2, x1, x2)[0] for w, d in H.items()}
    res["minutes_quality"] = {w: minutes_quality(H[w], m1, m2) for w in H}
    W = {w: npg.evaluate(H[w], P[w], slope_ci=(w in ("H2", "H3"))) for w in H}
    res["windows"] = W
    # residual tables per candidate and window (final probabilities)
    T = {k: {w: resid_tables(H[w], P[w][k]) for w in H} for k in ("a", "c", "M1f", "M1x", "M2f", "M2x", "E")}
    res["resid_tables"] = T
    res["verdicts"] = {k: verdict(W, T[k], k) for k in ("M1f", "M1x", "M2f", "M2x")}
    # M3: policy n_cur >= 5, evaluated on the retained subset
    sub = {w: (H[w]["n_cur"] >= 5).to_numpy() for w in H}
    Hs = {w: H[w][sub[w]].reset_index(drop=True) for w in H}; Ps = {w: {k: P[w][k][sub[w]] for k in ("a", "c", "E")} for w in H}
    res["M3"] = {"coverage_units": {w: float(Hs[w].drop_duplicates(["player_id", "game_id"]).shape[0] / H[w].drop_duplicates(["player_id", "game_id"]).shape[0]) for w in H},
                 "coverage_rows": {w: float(len(Hs[w]) / len(H[w])) for w in H}}
    Ws = {w: npg.evaluate(Hs[w], Ps[w], slope_ci=(w in ("H2", "H3"))) for w in H}
    res["M3"]["windows"] = Ws
    Ts = {w: resid_tables(Hs[w], Ps[w]["c"]) for w in H}
    res["M3"]["resid_tables"] = Ts
    res["verdicts"]["M3"] = verdict(Ws, Ts, "c", subset=True)
    json.dump(res, open(os.path.join(a.out, "results7.json"), "w"), indent=1, default=float)
    print("saved; f1", {k: round(v, 3) for k, v in m1.items()}, "shuffle", res["shuffle"]["pass"], {k: v["verdict"] for k, v in res["verdicts"].items()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run"); r.add_argument("--rows", required=True); r.add_argument("--out", required=True)
    args = ap.parse_args(); os.makedirs(args.out, exist_ok=True); cmd_run(args)
