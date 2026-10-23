#!/usr/bin/env python3
"""EXP-20261021-06 — early-season (games 1-10) carryover for fit layer A (analysis only).
Protocol frozen in docs/experiments/EXP-20261021-06-nba-early-season-carryover.md.
  python3 nba_early.py build --raw RAW --out OUT6
  python3 nba_early.py run   --out OUT6
"""
import argparse, json, os, sys
from datetime import date, timedelta
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import nba_calib as nc
import nba_pregame as npg
import nba_refit as nr

sys.path.insert(0, nc.LIVE_DIR)
import nba_fit_layer as fl  # frozen artefact (read-only)

TARGETS = {"2025-26": "2024-25", "2024-25": "2023-24", "2023-24": "2022-23"}
FILES = {"2025-26": "leaguegamelog_P_2025-26.json", "2024-25": "leaguegamelog_P_2024-25.json",
         "2023-24": "leaguegamelog_P_2023-24.json", "2022-23": "leaguegamelog_P_2022-23.json"}
K_GRID = [0, 1, 2, 3, 5, 8, 12, 20, 40, 80]
MIN_PRIOR_GAMES, MIN_PRIOR_MEAN_MIN = 40, 20.0


def load(raw_dir, season):
    d = json.load(open(os.path.join(raw_dir, FILES[season])))["resultSets"][0]
    df = pd.DataFrame(d["rowSet"], columns=d["headers"])
    df["GAME_DATE"] = df["GAME_DATE"].astype(str).str[:10]
    df["is_home"] = df["MATCHUP"].str.contains("vs.", regex=False)
    return df.sort_values(["PLAYER_ID", "GAME_DATE", "GAME_ID"]).reset_index(drop=True)


def prior_table(dfP):
    out = {}
    for pid, g in dfP[dfP["MIN"] > 0].groupby("PLAYER_ID"):
        if len(g) >= MIN_PRIOR_GAMES and g["MIN"].mean() >= MIN_PRIOR_MEAN_MIN:
            out[pid] = {"dates": g["GAME_DATE"].tolist(), "mins": g["MIN"].to_numpy(float),
                        **{s: g[s].to_numpy(float) for s in nc.STATS}}
    return out


def build_rows(dfS, dfP, season, gen):
    prior = prior_table(dfP)
    team_dateset = dfS.groupby("TEAM_ABBREVIATION")["GAME_DATE"].apply(set).to_dict()
    rows = []
    for pid, g in dfS.groupby("PLAYER_ID", sort=False):
        if pid not in prior:
            continue
        P = prior[pid]
        dates = g["GAME_DATE"].tolist(); mins = g["MIN"].to_numpy(float); home = g["is_home"].to_numpy()
        team = g["TEAM_ABBREVIATION"].tolist(); gids = g["GAME_ID"].astype(str).tolist()
        vals = {s: g[s].to_numpy(float) for s in nc.STATS}
        played = np.where(mins > 0)[0]; pdates = [dates[j] for j in played]
        prior_min_total = float(P["mins"].sum()); prior_min_mean = float(P["mins"].mean())
        for i in range(len(g)):
            D = dates[i]
            kc = nc.prior_count(pdates, D)                 # same-season played games strictly before D
            if kc >= 10:
                continue
            idx = played[:kc]
            assert all(dates[j] < D for j in idx) and max(P["dates"]) < D       # point-in-time
            seq_min = np.concatenate([P["mins"], mins[idx]])
            min10 = float(seq_min[-10:].mean())
            prev = (date.fromisoformat(D) - timedelta(days=1)).isoformat()
            is_b2b = prev in team_dateset[team[i]]
            hm = home[idx]; pp = vals["PTS"][idx]
            hp = float(pp[hm].mean()) if hm.sum() >= 3 else None
            rp = float(pp[~hm].mean()) if (~hm).sum() >= 3 else None
            for s in nc.STATS:
                seq = np.concatenate([P[s], vals[s][idx]])
                l10 = [float(x) for x in seq[-10:][::-1]]            # newest first, spans seasons like live
                avg, med, sd, cov = gen.compute_stats(l10); m = float(np.mean(l10))
                if m < 1.0:
                    continue
                prior_total = float(P[s].sum())
                S_cur = float(vals[s][idx].sum()); M_cur = float(mins[idx].sum())
                for n in nc.choose_lines(m):
                    hr10 = gen.hit_rate(l10, n)[0]; hr5 = gen.hit_rate(l10[:5], n)[0]
                    e, _ = gen.calc_adjusted_winprob(base_rate=hr10, hit_l5=hr5, cov=cov, avg=avg, line_val=float(n),
                                                     is_b2b=is_b2b, is_home=bool(home[i]), l10=l10, min_avg=min10,
                                                     home_ppg=hp, road_ppg=rp, season_phase="MID_SEASON")
                    rows.append(dict(season=season, date=D, game_id=gids[i], player_id=int(pid), stat=s, line=n, m=m,
                                     y=int(vals[s][i] >= n), actual=float(vals[s][i]), min_g=float(mins[i]), a=hr10 / 100.0,
                                     e=e / 100.0, n_cur=kc, S_cur=S_cur, M_cur=M_cur, prior_total=prior_total,
                                     prior_min_total=prior_min_total, min10=min10, prior_min_mean=prior_min_mean))
    return rows


def cmd_build(a):
    gen = nc.load_live(); allr = []
    raw = {s: load(a.raw, s) for s in FILES}
    for S, Pn in TARGETS.items():
        allr += build_rows(raw[S], raw[Pn], S, gen); print(S, len(allr), flush=True)
    os.makedirs(a.out, exist_ok=True)
    pd.DataFrame(allr).to_csv(os.path.join(a.out, "rows.csv"), index=False); print("saved", len(allr))


# ───────────────────────── models ─────────────────────────
def count_p(df, mu, model):
    out = np.empty(len(df))
    stats = df["stat"].to_numpy(); lines = df["line"].to_numpy()
    cache = {}
    for i in range(len(df)):
        key = (stats[i], int(lines[i]), round(float(mu[i]), 10))
        v = cache.get(key)
        if v is None:
            v = fl._sf(int(lines[i]), float(mu[i]), float(model["count_model"][stats[i]]["alpha"])); cache[key] = v
        out[i] = v
    return out


def mu_prior(df):
    return np.maximum(0.05, df["prior_total"].to_numpy() / df["prior_min_total"].to_numpy() * df["min10"].to_numpy())


def mu_blend(df, kmap):
    rp = df["prior_total"].to_numpy() / df["prior_min_total"].to_numpy()
    n = df["n_cur"].to_numpy(float); Mc = df["M_cur"].to_numpy(); Sc = df["S_cur"].to_numpy()
    rc = np.where(Mc > 0, Sc / np.where(Mc > 0, Mc, 1.0), rp)
    k = df["stat"].map(kmap).to_numpy(float)
    rate = np.where(n + k > 0, (n * rc + k * rp) / np.where(n + k > 0, n + k, 1.0), rp)
    return np.maximum(0.05, rate * df["min10"].to_numpy())


def recal(p, df, coefs):
    out = np.empty(len(df))
    for s in nc.STATS:
        mk = (df["stat"] == s).to_numpy(); a_, b_ = coefs[s]
        out[mk] = nr.sigmoid(a_ + b_ * nc.logit(p[mk]))
    return nc.clipp(out)


def frozen_coefs(model):
    return {s: (model["recalibration"][s]["a"], model["recalibration"][s]["b"]) for s in nc.STATS}


def tune_k(dev, model):
    kmap = {}
    for s in nc.STATS:
        d = dev[dev.stat == s]; best = None
        for k in K_GRID:
            p = count_p(d, mu_blend(d, {s: k}), model)
            br = float(nc.brier_loss(p, d["y"].to_numpy()).mean())
            if best is None or br <= best[0] + 1e-12:      # ascending k; ties -> larger k
                best = (br if best is None else min(br, best[0]), k)
        kmap[s] = best[1]
    return kmap


def all_probs(df, model, kmap, x1coef):
    pc0 = count_p(df, mu_prior(df), model); pc1 = count_p(df, mu_blend(df, kmap), model)
    fz = frozen_coefs(model)
    A0 = np.array([fl.fit_prob_A(r.stat, int(r.line), r.prior_total, r.prior_min_total, r.min10, model=model)[0] for r in df.itertuples()])
    A0_ref = recal(pc0, df, fz)
    assert np.abs(A0 - A0_ref).max() < 1e-9, np.abs(A0 - A0_ref).max()      # artefact call == harness formula
    return {"a": df["a"].to_numpy(), "c": pc0, "c1": pc1, "A0": A0, "A1": recal(pc1, df, fz), "X1": recal(pc1, df, x1coef), "E": df["e"].to_numpy()}


def fit_x1(dev, model, kmap, y=None):
    pc1 = count_p(dev, mu_blend(dev, kmap), model); y = dev["y"].to_numpy().astype(float) if y is None else y
    return {s: nc.fit_logit(nc.logit(pc1[(dev.stat == s).to_numpy()]), y[(dev.stat == s).to_numpy()]) for s in nc.STATS}


def verdict(W, k):
    P = lambda w: W[w]["groups"]["pooled"][k]
    c = {"c1_H2_ci_below0": P("H2")["d_brier_vs_a"]["hi"] < 0, "c2_dev_neg": P("dev")["d_brier_vs_a"]["diff"] < 0,
         "c3_H3_ci_below0": P("H3")["d_brier_vs_a"]["hi"] < 0,
         "c4_slope_H2": 0.85 <= P("H2")["slope"] <= 1.15, "c4_slope_H3": 0.85 <= P("H3")["slope"] <= 1.15}
    bad = [b for b in P("H2")["reliability"] if b[1] >= 500 and abs(b[2] - b[3]) > 0.05]
    c["c5_no_bad_bucket_H2"] = not bad
    c["c6_H2_beats_c0"] = P("H2")["d_brier_vs_c"]["hi"] < 0
    return {**{x: bool(v) for x, v in c.items()}, "bad_buckets_H2": bad, "verdict": "passes" if all(c.values()) else "not shown"}


def bias_check(dev, pc0, pc1):
    codes = pd.factorize(dev["game_id"] + "|" + dev["season"])[0]; G = int(codes.max()) + 1
    cnt = np.random.default_rng(nc.BOOT_SEED).multinomial(G, np.full(G, 1.0 / G), size=nc.BOOT_N).astype(float)
    out = {"by_prior_min": {}, "by_n_cur": {}}
    def one(mk, resid):
        r = np.where(mk, resid, 0.0); sg = np.bincount(codes, weights=r, minlength=G); ng = np.bincount(codes, weights=mk.astype(float), minlength=G)
        b = (cnt @ sg) / (cnt @ ng); return {"n": int(mk.sum()), "mean": float(resid[mk].mean()), "ci": nr.ci(b)}
    pm = dev["prior_min_mean"].to_numpy(); nn = dev["n_cur"].to_numpy()
    for name, mk in (("20-25", (pm >= 20) & (pm < 25)), ("25-30", (pm >= 25) & (pm < 30)), (">=30", pm >= 30)):
        if mk.sum():
            out["by_prior_min"][name] = {"c0": one(mk, dev["y"].to_numpy() - pc0), "c1": one(mk, dev["y"].to_numpy() - pc1)}
    for name, mk in (("0", nn == 0), ("1-4", (nn >= 1) & (nn <= 4)), ("5-9", (nn >= 5) & (nn <= 9))):
        if mk.sum():
            out["by_n_cur"][name] = {"c0": one(mk, dev["y"].to_numpy() - pc0), "c1": one(mk, dev["y"].to_numpy() - pc1)}
    out["biased"] = bool(any(abs(v[a]["mean"]) > 0.03 and (v[a]["ci"][0] > 0 or v[a]["ci"][1] < 0)
                             for v in out["by_prior_min"].values() for a in ("c0", "c1")))
    return out


def strata(df, P):
    out = {}
    for name, mk in (("0", df.n_cur == 0), ("1-4", (df.n_cur >= 1) & (df.n_cur <= 4)), ("5-9", (df.n_cur >= 5) & (df.n_cur <= 9))):
        mk = mk.to_numpy(); y = df["y"].to_numpy().astype(float)[mk]
        out[name] = {"n": int(mk.sum()), **{k: {"brier": float(nc.brier_loss(p[mk], y).mean()), "slope": nc.fit_logit(nc.logit(p[mk]), y)[1]}
                                            for k, p in P.items() if k in ("a", "c", "c1", "A0", "A1", "X1")}}
    return out


def cmd_run(a):
    rows = pd.read_csv(os.path.join(a.out, "rows.csv"), dtype={"game_id": str})
    model, why = fl.load_model(); assert model is not None, why
    dev = rows[(rows.season == "2025-26") & (rows.date < nc.DEV_END)].reset_index(drop=True)
    H = {"dev": dev, "H1": rows[(rows.season == "2025-26") & (rows.date >= nc.H1_START)].reset_index(drop=True),
         "H2": rows[rows.season == "2024-25"].reset_index(drop=True), "H3": rows[rows.season == "2023-24"].reset_index(drop=True)}
    kmap = tune_k(dev, model); x1 = fit_x1(dev, model, kmap)
    res = {"kmap": kmap, "x1_coef": {s: list(v) for s, v in x1.items()}, "frozen_coef": {s: list(v) for s, v in frozen_coefs(model).items()},
           "n_rows": {w: int(len(d)) for w, d in H.items()},
           "n_units": {w: int(d.drop_duplicates(["player_id", "game_id"]).shape[0]) for w, d in H.items()},
           "n_players": {w: int(d.player_id.nunique()) for w, d in H.items()}}
    # shuffle test (dev): permute y within stat, refit X1 slopes
    rng = np.random.default_rng(nc.BOOT_SEED); ys = dev["y"].to_numpy().astype(float).copy()
    for s in nc.STATS:
        mk = (dev.stat == s).to_numpy(); ys[mk] = rng.permutation(ys[mk])
    sh = fit_x1(dev, model, kmap, y=ys); res["shuffle"] = {"slopes": {s: float(v[1]) for s, v in sh.items()}, "pass": bool(all(abs(v[1]) < 0.10 for v in sh.values()))}
    P = {w: all_probs(d, model, kmap, x1) for w, d in H.items()}
    pc0d = count_p(dev, mu_prior(dev), model); pc1d = count_p(dev, mu_blend(dev, kmap), model)
    res["bias_check"] = bias_check(dev, pc0d, pc1d)
    W = {w: npg.evaluate(H[w], P[w], slope_ci=(w in ("H2", "H3"))) for w in H}
    res["windows"] = W; res["strata"] = {w: strata(H[w], P[w]) for w in H}
    res["verdicts"] = {k: verdict(W, k) for k in ("c1", "A0", "A1", "X1")}
    json.dump(res, open(os.path.join(a.out, "results6.json"), "w"), indent=1, default=float)
    print("saved; k", kmap, "bias", res["bias_check"]["biased"], "shuffle", res["shuffle"]["pass"], {k: v["verdict"] for k, v in res["verdicts"].items()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build"); b.add_argument("--raw", required=True); b.add_argument("--out", required=True)
    r = sp.add_parser("run"); r.add_argument("--out", required=True)
    args = ap.parse_args(); {"build": cmd_build, "run": cmd_run}[args.cmd](args)
