#!/usr/bin/env python3
"""EXP-20261021-03 — ablation of the reproducible live adjustment terms (analysis only).
Protocol frozen in docs/experiments/EXP-20261021-03-nba-adjustment-ablation.md.

  python3 nba_calib.py build --raw RAW --out OUT3        # rows with t_* columns (EXP-02 builder, additive cols)
  python3 nba_ablation.py check   --old OUT_OLD --out OUT3   # determinism vs EXP-02 rows.csv
  python3 nba_ablation.py analyse --out OUT3
"""
import argparse, itertools, json, os, sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import nba_calib as nc

TERMS = ["trend", "cov", "buffer", "sip_n04", "sip_n01", "b2b", "home_away"]
PAIRS = {"P_trend_buffer": ("trend", "buffer"), "P_trend_sip04": ("trend", "sip_n04"),
         "P_buffer_sip04": ("buffer", "sip_n04"), "P_cov_buffer": ("cov", "buffer")}
ARMS = {"ALL": TERMS, "C0": []}
ARMS.update({f"ADD_{t}": [t] for t in TERMS})
ARMS.update({f"LOO_{t}": [x for x in TERMS if x != t] for t in TERMS})
ARMS.update({k: list(v) for k, v in PAIRS.items()})
assert len(ARMS) == 1 + 1 + 7 + 7 + 4


def arm_prob(df, terms):
    """Live combination rule: s=sum(terms); s>=-20; p=clamp(base+s,5,98); rounded to 0.1 like live."""
    base = df["a"].to_numpy() * 100.0
    s = np.zeros(len(df))
    for t in terms:
        s = s + df["t_" + t].to_numpy(float)
    s = np.maximum(s, -20.0)
    return np.round(np.clip(base + s, 5.0, 98.0), 1) / 100.0


def all_arm_probs(df):
    P = {"a": df["a"].to_numpy()}
    for k, terms in ARMS.items():
        P[k] = arm_prob(df, terms)
    return P


def cmd_check(a):
    old = pd.read_csv(os.path.join(a.old, "rows.csv"), dtype={"game_id": str})
    new = pd.read_csv(os.path.join(a.out, "rows.csv"), dtype={"game_id": str})
    assert len(old) == len(new), (len(old), len(new))
    for c in old.columns:
        if old[c].dtype.kind in "fi":
            assert np.allclose(old[c].to_numpy(), new[c].to_numpy(), equal_nan=True), c
        else:
            assert (old[c].astype(str).to_numpy() == new[c].astype(str).to_numpy()).all(), c
    # live-formula identity: ALL arm must equal live return value (column e) row by row
    d = new
    p = arm_prob(d, TERMS)
    assert np.allclose(p, d["e"].to_numpy(), atol=1e-9), float(np.abs(p - d["e"]).max())
    # other (unreproducible) terms must be zero in this setting
    assert (d["t_other"] == 0).all(), d["t_other"].abs().max()
    print("CHECK OK: rows identical to EXP-02 on old columns; ALL arm == live e on", len(d), "rows; t_other==0")


def boot_ci(dv, codes, G, counts):
    sg = np.bincount(codes, weights=dv, minlength=G)
    ng = np.bincount(codes, minlength=G).astype(float)
    b = (counts @ sg) / (counts @ ng)
    return {"diff": float(dv.mean()), "lo": float(np.percentile(b, 2.5)), "hi": float(np.percentile(b, 97.5)),
            "p": float(max(2 * min((b <= 0).mean(), (b >= 0).mean()), 1.0 / (nc.BOOT_N + 1)))}


def eval_window(df, pooled_only=False):
    P = all_arm_probs(df)
    y = df["y"].to_numpy().astype(float)
    codes = pd.factorize(df["game_id"] + "|" + df["season"])[0]
    G = int(codes.max()) + 1
    rng = np.random.default_rng(nc.BOOT_SEED)
    counts = rng.multinomial(G, np.full(G, 1.0 / G), size=nc.BOOT_N).astype(float)
    groups = {"pooled": np.ones(len(df), bool)}
    if not pooled_only:
        for s in nc.STATS:
            groups[nc.STAT_LABEL[s]] = (df["stat"] == s).to_numpy()
    out = {"n_rows": int(len(df)), "n_games": G, "groups": {}}
    for g, mk in groups.items():
        yb, cb = y[mk], codes[mk]
        L = {k: nc.brier_loss(p[mk], yb) for k, p in P.items()}
        LL = {k: nc.logloss_loss(p[mk], yb) for k, p in P.items()}
        R = {"arms": {}, "vs_C0": {}, "LOO_vs_ALL": {}, "interaction": {}}
        for k, p in P.items():
            a0, b0 = nc.fit_logit(nc.logit(p[mk]), yb)
            ent = {"brier": float(L[k].mean()), "logloss": float(LL[k].mean()), "slope": b0, "intercept": a0,
                   "citl": float(nc.clipp(p[mk]).mean() - yb.mean())}
            if k != "a":
                ent["d_brier"] = boot_ci(L[k] - L["a"], cb, G, counts)
                ent["d_logloss"] = boot_ci(LL[k] - LL["a"], cb, G, counts)
            R["arms"][k] = ent
        for k in ["ALL"] + [f"ADD_{t}" for t in TERMS] + list(PAIRS):
            R["vs_C0"][k] = boot_ci(L[k] - L["C0"], cb, G, counts)
        for t in TERMS:
            R["LOO_vs_ALL"][t] = boot_ci(L[f"LOO_{t}"] - L["ALL"], cb, G, counts)
        # interaction: joint minus sum of singles
        R["interaction"]["ALL_minus_sum_singles"] = boot_ci(
            L["ALL"] - sum(L[f"ADD_{t}"] for t in TERMS) + (len(TERMS) - 1) * L["a"], cb, G, counts)
        for k, (x, z) in PAIRS.items():
            R["interaction"][k] = boot_ci(L[k] - L[f"ADD_{x}"] - L[f"ADD_{z}"] + L["a"], cb, G, counts)
        R["sum_single_dbrier"] = float(sum(R["arms"][f"ADD_{t}"]["d_brier"]["diff"] for t in TERMS))
        out["groups"][g] = R
    return out


def diagnostics(df):
    s_raw = sum(df["t_" + t].to_numpy(float) for t in TERMS)
    base = df["a"].to_numpy() * 100
    tot = np.maximum(s_raw, -20)
    d = {"n": int(len(df)), "cap_binds": float((s_raw < -20).mean()),
         "clamp_low": float((base + tot < 5).mean()), "clamp_high": float((base + tot > 98).mean()),
         "base_0_or_100": float(((base <= 0) | (base >= 100)).mean()),
         "sum_adj_mean": float(s_raw.mean()), "sum_adj_sd": float(s_raw.std()),
         "terms": {t: {"nonzero": float((df["t_" + t] != 0).mean()), "mean": float(df["t_" + t].mean()),
                       "pos": float((df["t_" + t] > 0).mean()), "neg": float((df["t_" + t] < 0).mean())} for t in TERMS}}
    return d


def cmd_analyse(a):
    rows = pd.read_csv(os.path.join(a.out, "rows.csv"), dtype={"game_id": str})
    res = {}
    for pname, pop, pooled_only in (("primary", rows[rows.primary], False), ("S1", rows[rows.s1], True)):
        dev = pop[(pop.season == "2025-26") & (pop.date < nc.DEV_END)]
        h1 = pop[(pop.season == "2025-26") & (pop.date >= nc.H1_START)]
        h2 = pop[pop.season == "2024-25"]
        res[pname] = {"windows": {w: eval_window(df, pooled_only) for w, df in (("dev", dev), ("H1", h1), ("H2", h2))},
                      "diagnostics": {w: diagnostics(df) for w, df in (("dev", dev), ("H1", h1), ("H2", h2))}}
    json.dump(res, open(os.path.join(a.out, "results3.json"), "w"), indent=1)
    print("saved results3.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("check"); c.add_argument("--old", required=True); c.add_argument("--out", required=True)
    n = sp.add_parser("analyse"); n.add_argument("--out", required=True)
    args = ap.parse_args()
    {"check": cmd_check, "analyse": cmd_analyse}[args.cmd](args)
