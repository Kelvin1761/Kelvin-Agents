#!/usr/bin/env python3
"""EXP-20261021-08 — monotone recalibration of the live FINAL probability E (analysis only).
Protocol frozen in docs/experiments/EXP-20261021-08-nba-final-probability-recalibration.md.
  python3 nba_recal_e.py run --rows1 OUT5/rows.csv --rows2 OUT6/rows.csv --out OUT8
"""
import argparse, json, os, sys
import numpy as np
import pandas as pd
from scipy.stats import rankdata

sys.path.insert(0, os.path.dirname(__file__))
import nba_calib as nc
import nba_early as ne
import nba_pregame as npg
import nba_refit as nr

KMAP = {"PTS": 5, "REB": 40, "AST": 5, "FG3M": 8}
CITL_BAND = 0.03
ZONES = (0.70, 0.80)
E_GRID = [0.30, 0.50, 0.70, 0.80, 0.90, 0.95]
AUC_BOOT = 200


# ───────────────────────── maps ─────────────────────────
def fit_iso(x, y):
    """PAV on unique x (ties merged, weights = counts). Returns (ux, fitted) with fitted non-decreasing."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    ux, inv = np.unique(x, return_inverse=True)
    w = np.bincount(inv).astype(float); m = np.bincount(inv, weights=y) / w
    vals, wts, cnt = [], [], []
    for v, ww in zip(m, w):
        vals.append(v); wts.append(ww); cnt.append(1)
        while len(vals) > 1 and vals[-2] > vals[-1] + 1e-15:
            tw = wts[-2] + wts[-1]; tv = (vals[-2] * wts[-2] + vals[-1] * wts[-1]) / tw; tc = cnt[-2] + cnt[-1]
            vals[-2:], wts[-2:], cnt[-2:] = [tv], [tw], [tc]
    fitted = np.repeat(vals, cnt)
    return ux, fitted


def pred_iso(model, x):
    ux, fitted = model
    return np.clip(np.interp(np.asarray(x, float), ux, fitted), *nc.CLIP)


def fit_platt(e, y, w=None):
    return nc.fit_logit(nc.logit(e), np.asarray(y, float), w)


def pred_platt(coef, e):
    a, b = coef
    return nc.clipp(nr.sigmoid(a + b * nc.logit(e)))


def design_pooled(df):
    return np.column_stack([np.ones(len(df)), nc.logit(df["e"].to_numpy())] + [(df["stat"] == s).to_numpy().astype(float) for s in ("REB", "AST", "FG3M")])


def fit_all_maps(d):
    """Fit every map on frame d (dev only by construction of the caller)."""
    y = d["y"].to_numpy().astype(float); e = d["e"].to_numpy()
    M = {"K1": {}, "K2": {}}
    for s in nc.STATS:
        mk = (d.stat == s).to_numpy()
        M["K1"][s] = fit_iso(e[mk], y[mk]); M["K2"][s] = fit_platt(e[mk], y[mk])
    M["K1p"] = fit_iso(e, y)
    M["K2p"] = nr.fit_l2(design_pooled(d), y, np.ones(len(d)), 0, np.array([0, 0, 0, 0, 0]))
    return M


def apply_maps(df, M):
    e = df["e"].to_numpy(); out = {}
    for name, fn in (("K1", pred_iso), ("K2", pred_platt)):
        p = np.empty(len(df))
        for s in nc.STATS:
            mk = (df.stat == s).to_numpy(); p[mk] = fn(M[name][s], e[mk])
        out[name] = p
    out["K1p"] = pred_iso(M["K1p"], e); out["K2p"] = nc.clipp(nr.sigmoid(design_pooled(df) @ M["K2p"]))
    return out


# ───────────────────────── metrics ─────────────────────────
def auc(score, y):
    y = np.asarray(y).astype(bool); n1 = y.sum(); n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = rankdata(score)
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def auc_table(df, probs, arms=("a", "base", "c")):
    y = df["y"].to_numpy(); out = {"pooled": {k: auc(probs[k], y) for k in probs}}
    for s in nc.STATS:
        mk = (df.stat == s).to_numpy(); out[nc.STAT_LABEL[s]] = {k: auc(probs[k][mk], y[mk]) for k in probs}
    codes = pd.factorize(df["game_id"] + "|" + df["season"])[0]; G = int(codes.max()) + 1
    order = np.argsort(codes, kind="stable"); starts = np.searchsorted(codes[order], np.arange(G + 1))
    idx = [order[starts[g]:starts[g + 1]] for g in range(G)]
    rng = np.random.default_rng(nc.BOOT_SEED); boots = {k: [] for k in arms}; d_eb, d_le = [], []
    for _ in range(AUC_BOOT):
        sel = np.concatenate([idx[g] for g in rng.integers(0, G, size=G)]); yy = y[sel]
        v = {k: auc(probs[k][sel], yy) for k in arms}
        for k in arms:
            boots[k].append(v[k])
        d_eb.append(v["a"] - v["base"]); d_le.append(v["c"] - v["a"])
    out["pooled_ci"] = {k: nr.ci(boots[k]) for k in arms}
    out["E_minus_base"] = {"diff": out["pooled"]["a"] - out["pooled"]["base"], "ci": nr.ci(d_eb)}
    out["L_minus_E"] = {"diff": out["pooled"]["c"] - out["pooled"]["a"], "ci": nr.ci(d_le)}
    return out


def strata_metrics(df, probs, labels):
    out = {}
    y = df["y"].to_numpy().astype(float)
    for nm in pd.unique(labels):
        mk = labels == nm
        ent = {"n": int(mk.sum())}
        for k, p in probs.items():
            if k in ("a", "base", "c", "K1", "K2"):
                ent[k] = {"brier": float(nc.brier_loss(p[mk], y[mk]).mean()), "slope": nc.fit_logit(nc.logit(p[mk]), y[mk])[1],
                          "citl": float(nc.clipp(p[mk]).mean() - y[mk].mean()), "auc": auc(p[mk], y[mk])}
        out[str(nm)] = ent
    return out


def resid_tables(df, p, strat, bucket):
    codes = pd.factorize(df["game_id"] + "|" + df["season"])[0]; G = int(codes.max()) + 1
    cnt = np.random.default_rng(nc.BOOT_SEED).multinomial(G, np.full(G, 1.0 / G), size=nc.BOOT_N).astype(float)
    resid = df["y"].to_numpy() - p; out = {"S": {}, "B": {}}
    for fam, arr in (("S", strat), ("B", bucket)):
        for nm in pd.unique(arr):
            mk = arr == nm; r = np.where(mk, resid, 0.0)
            b = (cnt @ np.bincount(codes, weights=r, minlength=G)) / (cnt @ np.bincount(codes, weights=mk.astype(float), minlength=G))
            out[fam][str(nm)] = {"n": int(mk.sum()), "mean_resid": float(resid[mk].mean()), "ci": nr.ci(b)}
    return out


def veto(t):
    return [(f, n, v["mean_resid"], v["ci"]) for f in ("S", "B") for n, v in t[f].items()
            if abs(v["mean_resid"]) > CITL_BAND and (v["ci"][0] > 0 or v["ci"][1] < 0)]


def level_ok(t, keys):
    return all(k in t["S"] and abs(t["S"][k]["mean_resid"]) <= CITL_BAND and t["S"][k]["ci"][0] <= 0 <= t["S"][k]["ci"][1] for k in keys)


def zone_cross(p0, p1, y):
    out = {}
    for z in ZONES:
        hi0 = p0 >= z; hi1 = p1 >= z
        out[str(z)] = {"n_E": int(hi0.sum()), "n_K": int(hi1.sum()), "retained_of_E": float((hi0 & hi1).sum() / max(1, hi0.sum())),
                       "new_from_below": int((~hi0 & hi1).sum()),
                       "E_mean_p": float(p0[hi0].mean()) if hi0.any() else None, "E_hit": float(y[hi0].mean()) if hi0.any() else None,
                       "K_mean_p": float(p1[hi1].mean()) if hi1.any() else None, "K_hit": float(y[hi1].mean()) if hi1.any() else None}
    return out


# ───────────────────────── verdicts ─────────────────────────
def verdict_p1(W, T, k):
    P = lambda w: W[w]["groups"]["pooled"][k]
    c = {"c1_H1_ci_below0": P("H1")["d_brier_vs_a"]["hi"] < 0, "c2_dev_neg": P("dev")["d_brier_vs_a"]["diff"] < 0,
         "c3_H2_ci_below0": P("H2")["d_brier_vs_a"]["hi"] < 0,
         "c4_slope_H1": 0.85 <= P("H1")["slope"] <= 1.15, "c4_slope_H2": 0.85 <= P("H2")["slope"] <= 1.15}
    bad = [b for b in P("H1")["reliability"] if b[1] >= 500 and abs(b[2] - b[3]) > 0.05]
    c["c5_no_bad_bucket_H1"] = not bad
    vb = veto(T["dev"]); allc = all(c.values())
    return {**{x: bool(v) for x, v in c.items()}, "bad_buckets_H1": bad, "veto_buckets_dev": vb,
            "verdict": "VETOED" if (vb and allc) else ("passes" if allc and not vb else "not shown")}


def verdict_p2(W, T, k):
    P = lambda w: W[w]["groups"]["pooled"][k]
    c = {"c1_H2_ci_below0": P("H2")["d_brier_vs_a"]["hi"] < 0, "c2_dev_neg": P("dev")["d_brier_vs_a"]["diff"] < 0,
         "c3_H3_ci_below0": P("H3")["d_brier_vs_a"]["hi"] < 0,
         "c4_slope_H2": 0.85 <= P("H2")["slope"] <= 1.15, "c4_slope_H3": 0.85 <= P("H3")["slope"] <= 1.15}
    bad = [b for b in P("H2")["reliability"] if b[1] >= 500 and abs(b[2] - b[3]) > 0.05]
    c["c5_no_bad_bucket_H2"] = not bad
    c["c6_level_H2"] = level_ok(T["H2"], ["S0", "S1", "S2"]); c["c6_level_H3"] = level_ok(T["H3"], ["S0", "S1", "S2"])
    vb = veto(T["dev"]); allc = all(c.values())
    return {**{x: bool(v) for x, v in c.items()}, "bad_buckets_H2": bad, "veto_buckets_dev": vb,
            "verdict": "VETOED" if (vb and allc) else ("passes" if allc and not vb else "not shown")}


# ───────────────────────── run ─────────────────────────
def p1_labels(df):
    t = df["t_sip_n01"].to_numpy()
    return np.array(["G11+"] * len(df)), np.where(t == -3, "20-25", np.where(t == 0, ">=25", "<20"))


def p2_labels(df):
    return ne_labels(df)


def ne_labels(df):
    n = df["n_cur"].to_numpy(); pm = df["prior_min_mean"].to_numpy()
    return (np.where(n == 0, "S0", np.where(n <= 4, "S1", "S2")), np.where(pm < 25, "B1", np.where(pm < 30, "B2", "B3")))


def cmd_run(a):
    model, why = ne.fl.load_model(); assert model is not None, why
    fz = ne.frozen_coefs(model)
    r1 = pd.read_csv(a.rows1, dtype={"game_id": str}); r1 = r1[r1.pregame & (r1.virtual == 0)]
    r2 = pd.read_csv(a.rows2, dtype={"game_id": str})
    H1d = {"dev": r1[(r1.season == "2025-26") & (r1.date < nc.DEV_END)].reset_index(drop=True),
           "H1": r1[(r1.season == "2025-26") & (r1.date >= nc.H1_START)].reset_index(drop=True),
           "H2": r1[r1.season == "2024-25"].reset_index(drop=True)}
    H2d = {"dev": r2[(r2.season == "2025-26") & (r2.date < nc.DEV_END)].reset_index(drop=True),
           "H2": r2[r2.season == "2024-25"].reset_index(drop=True), "H3": r2[r2.season == "2023-24"].reset_index(drop=True)}
    res = {"n_rows": {"P1": {w: int(len(d)) for w, d in H1d.items()}, "P2": {w: int(len(d)) for w, d in H2d.items()}}}
    # ---- maps (dev of P1 only) ----
    params = nc.tune(H1d["dev"]); M = fit_all_maps(H1d["dev"])
    Me = fit_all_maps(H2d["dev"])                                       # exploratory early-dev maps
    res["platt_coef_P1dev"] = {s: list(M["K2"][s]) for s in nc.STATS}; res["K2p_coef"] = list(map(float, M["K2p"]))
    res["iso_values_P1dev"] = {s: {str(g): float(pred_iso(M["K1"][s], np.array([g]))[0]) for g in E_GRID} for s in nc.STATS}
    # ---- shuffle test (dev P1) ----
    rng = np.random.default_rng(nc.BOOT_SEED); d = H1d["dev"].copy(); ys = d["y"].to_numpy().astype(float).copy()
    for s in nc.STATS:
        mk = (d.stat == s).to_numpy(); ys[mk] = rng.permutation(ys[mk])
    sl = {s: float(nc.fit_logit(nc.logit(d["e"].to_numpy()[(d.stat == s).to_numpy()]), ys[(d.stat == s).to_numpy()])[1]) for s in nc.STATS}
    iso_gain = {}
    for s in nc.STATS:
        mk = (d.stat == s).to_numpy(); mdl = fit_iso(d["e"].to_numpy()[mk], ys[mk]); p = pred_iso(mdl, d["e"].to_numpy()[mk])
        iso_gain[s] = float(nc.brier_loss(np.full(mk.sum(), ys[mk].mean()), ys[mk]).mean() - nc.brier_loss(p, ys[mk]).mean())
    res["shuffle"] = {"platt_slopes": sl, "iso_insample_gain": iso_gain, "pass": bool(all(abs(v) < 0.10 for v in sl.values()) and all(v < 0.0005 for v in iso_gain.values()))}
    # ---- probabilities per window ----
    def probs_p1(df):
        P = nc.cand_probs(df, params)
        L = ne.recal(P["c"], df, fz)
        K = apply_maps(df, M)
        return {"a": df["e"].to_numpy(), "c": L, "base": df["a"].to_numpy(), **K}
    def probs_p2(df):
        pc = ne.count_p(df, ne.mu_blend(df, KMAP), model)
        L = ne.recal(pc, df, fz)
        K = apply_maps(df, M); Ke = apply_maps(df, Me)
        return {"a": df["e"].to_numpy(), "c": L, "base": df["a"].to_numpy(), **K, "K1e": Ke["K1"], "K2e": Ke["K2"]}
    PR1 = {w: probs_p1(d) for w, d in H1d.items()}; PR2 = {w: probs_p2(d) for w, d in H2d.items()}
    # ---- evaluate ----
    W1 = {w: npg.evaluate(H1d[w], PR1[w], slope_ci=(w in ("H1", "H2"))) for w in H1d}
    W2 = {w: npg.evaluate(H2d[w], PR2[w], slope_ci=(w in ("H2", "H3"))) for w in H2d}
    res["P1"] = {"windows": W1}; res["P2"] = {"windows": W2}
    T1 = {k: {w: resid_tables(H1d[w], PR1[w][k], *p1_labels(H1d[w])) for w in H1d} for k in ("a", "K1", "K2")}
    T2 = {k: {w: resid_tables(H2d[w], PR2[w][k], *ne_labels(H2d[w])) for w in H2d} for k in ("a", "K1", "K2", "K1e", "K2e")}
    res["P1"]["resid"] = T1; res["P2"]["resid"] = T2
    res["P1"]["verdicts"] = {k: verdict_p1(W1, T1[k], k) for k in ("K1", "K2")}
    res["P2"]["verdicts"] = {k: verdict_p2(W2, T2[k], k) for k in ("K1", "K2", "K1e", "K2e")}
    ov = {k: ("passes" if res["P1"]["verdicts"][k]["verdict"] == "passes" and res["P2"]["verdicts"][k]["verdict"] == "passes" else "not shown") for k in ("K1", "K2")}
    res["overall_full_coverage"] = ov
    # ---- rank / strata ----
    res["auc"] = {"P1": {w: auc_table(H1d[w], PR1[w]) for w in ("dev", "H1", "H2")}, "P2": {w: auc_table(H2d[w], PR2[w]) for w in ("dev", "H2", "H3")}}
    res["strata"] = {"P1": {w: strata_metrics(H1d[w], PR1[w], p1_labels(H1d[w])[0]) for w in H1d},
                     "P2": {w: strata_metrics(H2d[w], PR2[w], ne_labels(H2d[w])[0]) for w in H2d}}
    # ---- zones & crossing ----
    res["cross"] = {pop: {w: {k: zone_cross(PR[w]["a"], PR[w][k], D[w]["y"].to_numpy()) for k in ("K1", "K2")}
                          for w in D} for pop, PR, D in (("P1", PR1, H1d), ("P2", PR2, H2d))}
    # ---- stability (descriptive refits per window; not used for selection) ----
    stab = {}
    for pop, D in (("P1", H1d), ("P2", H2d)):
        for w, d in D.items():
            if len(d) < 500:
                continue
            mm = fit_all_maps(d)
            stab[f"{pop}:{w}"] = {"platt": {s: list(mm["K2"][s]) for s in nc.STATS},
                                  "iso": {s: {str(g): float(pred_iso(mm["K1"][s], np.array([g]))[0]) for g in E_GRID} for s in nc.STATS}}
    res["stability"] = stab
    json.dump(res, open(os.path.join(a.out, "results8.json"), "w"), indent=1, default=float)
    print("saved; shuffle", res["shuffle"]["pass"], "P1", {k: v["verdict"] for k, v in res["P1"]["verdicts"].items()},
          "P2", {k: v["verdict"] for k, v in res["P2"]["verdicts"].items()}, "overall", ov)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run"); r.add_argument("--rows1", required=True); r.add_argument("--rows2", required=True); r.add_argument("--out", required=True)
    args = ap.parse_args(); os.makedirs(args.out, exist_ok=True); cmd_run(args)
