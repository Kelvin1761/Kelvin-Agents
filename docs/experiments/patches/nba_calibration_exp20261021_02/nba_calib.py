#!/usr/bin/env python3
"""EXP-20261021-02 — NBA prop-probability calibration harness (analysis only).

Protocol is frozen in docs/experiments/EXP-20261021-02-nba-probability-calibration.md.
Do NOT edit metric / window / line selection after seeing results.

Usage:
  python3 nba_calib.py build   --raw RAW_DIR --out OUT_DIR   # features per (unit, stat, line)
  python3 nba_calib.py analyse --out OUT_DIR                 # tune on dev, score dev/H1/H2, bootstrap
"""
import argparse, importlib.util, json, math, os, random, sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), *[".."] * 4))
LIVE_DIR = os.path.join(REPO, ".agents", "skills", "nba", "nba_wong_choi", "scripts")
STATS = ["PTS", "REB", "AST", "FG3M"]
STAT_LABEL = {"PTS": "PTS", "REB": "REB", "AST": "AST", "FG3M": "3PM"}
CLIP = (0.01, 0.99)
DEV_END = "2026-01-01"       # dev: date < this
H1_START = "2026-02-01"      # holdout H1: date >= this (2025-26)
SEASONS = {"2025-26": "leaguegamelog_P_2025-26.json", "2024-25": "leaguegamelog_P_2024-25.json"}
BOOT_N, SLOPE_BOOT_N, BOOT_SEED = 2000, 300, 20261021


# ───────────────────────── point-in-time core (unit-tested) ─────────────────────────
def prior_count(dates, d):
    """Number of rows in sorted ISO-date list `dates` with date STRICTLY earlier than `d`."""
    return int(np.searchsorted(np.asarray(dates, dtype="U10"), str(d)[:10], side="left"))


def choose_lines(m):
    """3 integers N>=1 nearest to mean m (tie -> smaller N). Depends on m only."""
    lo = max(1, int(math.floor(m)) - 2)
    cands = list(range(lo, int(math.ceil(m)) + 3))
    cands = sorted((n for n in cands if n >= 1), key=lambda n: (abs(n - m), n))[:3]
    return sorted(cands)


# ───────────────────────── live code import (read-only) ─────────────────────────
def load_live():
    spec = importlib.util.spec_from_file_location("live_gen", os.path.join(LIVE_DIR, "generate_nba_reports.py"))
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    return gen


def betabinom_prob(mean, sd, line):
    """Analytic version of monte_carlo_nba._sample_beta_binomial hit prob (made >= line)."""
    from scipy.stats import betabinom
    if sd <= 0:
        sd = mean * 0.15
    att = max(3, round(mean / 0.36))
    rate = min(0.95, max(0.05, mean / att))
    var_rate = max(0.001, (sd / max(1, att)) ** 2)
    ratio = max(1.0, rate * (1 - rate) / var_rate - 1)
    alpha = max(0.5, rate * ratio)
    beta = max(0.5, (1 - rate) * ratio)
    return float(betabinom.sf(line - 1, att, alpha, beta))


def live_mc_prob(avg, sd, line, stat):
    """Analytic live MC (no shrinkage, MID_SEASON): P(v >= line-0.5)."""
    from scipy.stats import norm
    if stat == "FG3M":
        return betabinom_prob(avg, sd, line)
    if sd <= 0:
        sd = avg * 0.15
    return float(norm.sf((line - 0.5 - avg) / sd))


# ───────────────────────── build ─────────────────────────
def load_season(raw_dir, season):
    d = json.load(open(os.path.join(raw_dir, SEASONS[season])))["resultSets"][0]
    df = pd.DataFrame(d["rowSet"], columns=d["headers"])
    df = df[df["MIN"] > 0].copy()
    df["GAME_DATE"] = df["GAME_DATE"].astype(str).str[:10]
    df["is_home"] = df["MATCHUP"].str.contains("vs.", regex=False)
    return df.sort_values(["PLAYER_ID", "GAME_DATE", "GAME_ID"]).reset_index(drop=True)


def build_rows(df, season, gen):
    team_dates = df.groupby("TEAM_ABBREVIATION")["GAME_DATE"].apply(set).to_dict()
    rows = []
    for pid, g in df.groupby("PLAYER_ID", sort=False):
        dates = g["GAME_DATE"].tolist()
        mins = g["MIN"].to_numpy(float)
        home = g["is_home"].to_numpy()
        team = g["TEAM_ABBREVIATION"].tolist()
        pts = g["PTS"].to_numpy(float)
        vals_all = {s: g[s].to_numpy(float) for s in STATS}
        for i in range(len(g)):
            k = prior_count(dates, dates[i])           # strictly earlier dates only
            if k < 10:
                continue
            assert all(d < dates[i] for d in dates[:k])  # runtime point-in-time assert
            min10 = mins[k - 10:k]
            min_avg10 = float(min10.mean())
            primary = bool(mins[i] >= 15)
            s1 = bool(min_avg10 >= 20)
            if not (primary or s1):
                continue
            prev = (date.fromisoformat(dates[i]) - timedelta(days=1)).isoformat()
            is_b2b = prev in team_dates[team[i]]
            hm = home[:k]
            hp = float(pts[:k][hm].mean()) if hm.sum() >= 3 else None
            rp = float(pts[:k][~hm].mean()) if (~hm).sum() >= 3 else None
            for s in STATS:
                v = vals_all[s][:k]
                l10 = [float(x) for x in v[k - 10:k][::-1]]           # newest first (as live)
                avg, med, sd, cov = gen.compute_stats(l10)
                m = float(np.mean(l10))
                if m < 1.0:
                    continue
                sea_sum, sea_min = float(v.sum()), float(mins[:k].sum())
                mu = max(0.05, sea_sum / sea_min * min_avg10)
                for n in choose_lines(m):
                    hr10 = gen.hit_rate(l10, n)[0]
                    hr5 = gen.hit_rate(l10[:5], n)[0]
                    e, bd = gen.calc_adjusted_winprob(
                        base_rate=hr10, hit_l5=hr5, cov=cov, avg=avg, line_val=float(n),
                        is_b2b=is_b2b, is_home=bool(home[i]), l10=l10, min_avg=min_avg10,
                        home_ppg=hp, road_ppg=rp, season_phase="MID_SEASON")
                    rows.append(dict(
                        season=season, date=dates[i], game_id=str(g["GAME_ID"].iloc[i]),
                        player_id=int(pid), stat=s, line=n, m=m, rel=n - m, rel_pct=(n - m) / m,
                        primary=primary, s1=s1, y=int(vals_all[s][i] >= n), actual=float(vals_all[s][i]),
                        a=hr10 / 100.0, hit_sea=float((v >= n).mean()), mu=mu,
                        e=e / 100.0, f=live_mc_prob(avg, sd, n, s), k=k,
                        # EXP-20261021-03 (additive columns): live per-term breakdown, pp
                        t_trend=bd["trend"], t_cov=bd["cov"], t_buffer=bd["buffer"],
                        t_sip_n04=bd["sip_n04_trend_protect"], t_sip_n01=bd["sip_n01_bench_risk"],
                        t_b2b=bd["b2b_fatigue"], t_home_away=bd["home_away"],
                        t_other=sum(bd[x] for x in ("pace", "minutes_floor", "opp_defense", "usg_shift",
                                                    "matchup_pace", "playoff_guard"))))
    return rows


def cmd_build(a):
    gen = load_live()
    allrows = []
    for season in SEASONS:
        df = load_season(a.raw, season)
        allrows += build_rows(df, season, gen)
        print(season, "rows so far", len(allrows), flush=True)
    out = pd.DataFrame(allrows)
    os.makedirs(a.out, exist_ok=True)
    out.to_csv(os.path.join(a.out, "rows.csv"), index=False)
    print("saved", len(out))


def cmd_validate_mc(a):
    """Check the analytic live-MC replica against the real (sampled) live function."""
    sys.path.insert(0, LIVE_DIR)
    import monte_carlo_nba as mc
    worst = 0.0
    for stat, avg, sd, line in [("PTS", 18.3, 6.1, 17), ("PTS", 9.4, 4.0, 10), ("REB", 6.2, 2.5, 6), ("AST", 4.1, 2.0, 4),
                                ("AST", 7.9, 3.1, 8), ("FG3M", 2.4, 1.3, 2), ("FG3M", 3.6, 1.6, 4), ("FG3M", 1.2, 1.0, 1)]:
        cat = "3PM" if stat == "FG3M" else stat
        live = mc.monte_carlo_player_prop(avg=avg, sd=sd, line=line, n=100000, category=cat, seed=11)["mc_prob"] / 100
        mine = live_mc_prob(avg, sd, line, stat)
        worst = max(worst, abs(live - mine))
        print(f"{stat} avg={avg} sd={sd} N={line}: live_MC={live:.4f} analytic={mine:.4f}")
    print("max abs diff", round(worst, 4))


# ───────────────────────── metrics ─────────────────────────
def clipp(p):
    return np.clip(np.asarray(p, float), *CLIP)


def brier_loss(p, y):
    return (clipp(p) - y) ** 2


def logloss_loss(p, y):
    p = clipp(p)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def logit(p):
    p = clipp(p)
    return np.log(p / (1 - p))


def fit_logit(x, y, w=None, iters=40):
    """y ~ sigmoid(a + b x), weighted Newton. Returns (a, b) or (nan, nan)."""
    if w is None:
        w = np.ones_like(x)
    if np.ptp(x[w > 0]) < 1e-9:
        return float("nan"), float("nan")
    beta = np.array([0.0, 1.0])
    X = np.column_stack([np.ones_like(x), x])
    for _ in range(iters):
        z = X @ beta
        p = 1 / (1 + np.exp(-z))
        g = X.T @ (w * (y - p))
        H = (X * (w * p * (1 - p))[:, None]).T @ X + 1e-9 * np.eye(2)
        step = np.linalg.solve(H, g)
        beta += step
        if np.max(np.abs(step)) < 1e-8:
            break
    return float(beta[0]), float(beta[1])


def reliability(p, y):
    p = clipp(p)
    b = np.minimum((p * 10).astype(int), 9)
    out = []
    for i in range(10):
        mk = b == i
        out.append((i, int(mk.sum()), float(p[mk].mean()) if mk.any() else None, float(y[mk].mean()) if mk.any() else None))
    return out


def cand_probs(df, params):
    """Return dict cand -> probability array for df rows."""
    from scipy.stats import nbinom, poisson
    out = {"a": df["a"].to_numpy(), "d": df["hit_sea"].to_numpy(), "e": df["e"].to_numpy(), "f": df["f"].to_numpy()}
    b = np.empty(len(df)); c = np.empty(len(df))
    for s in STATS:
        mk = (df["stat"] == s).to_numpy()
        w = params["w"][s]
        b[mk] = w * df["a"].to_numpy()[mk] + (1 - w) * df["hit_sea"].to_numpy()[mk]
        mu = df["mu"].to_numpy()[mk]; n = df["line"].to_numpy()[mk]
        al = params["alpha"][s]
        if al > 0:
            r = 1.0 / al
            c[mk] = nbinom.sf(n - 1, r, 1.0 / (1.0 + al * mu))
        else:
            c[mk] = poisson.sf(n - 1, mu)
    out["b"], out["c"] = b, c
    return out


def tune(dev):
    from scipy.optimize import minimize_scalar
    from scipy.stats import nbinom, poisson
    w = {}
    for s in STATS:
        d = dev[dev.stat == s]
        best = None
        for wi in np.arange(0, 1.0001, 0.05):
            p = wi * d["a"].to_numpy() + (1 - wi) * d["hit_sea"].to_numpy()
            br = float(brier_loss(p, d["y"].to_numpy()).mean())
            if best is None or br < best[0] - 1e-12:
                best = (br, round(float(wi), 2))
        w[s] = best[1]
    alpha = {s: 0.0 for s in STATS}
    d = dev[dev.stat == "PTS"].drop_duplicates(["player_id", "game_id"])
    y = d["actual"].to_numpy(); mu = d["mu"].to_numpy()

    def nll(la):
        al = math.exp(la); r = 1 / al
        return -float(nbinom.logpmf(y, r, 1 / (1 + al * mu)).sum())
    res = minimize_scalar(nll, bounds=(math.log(1e-4), math.log(5)), method="bounded")
    alpha["PTS"] = math.exp(res.x)
    return {"w": w, "alpha": alpha}


def paired_boot(diff, game_codes, G, rng_counts):
    """ratio-of-sums bootstrap of mean(diff) resampling games."""
    sg = np.bincount(game_codes, weights=diff, minlength=G)
    ng = np.bincount(game_codes, minlength=G).astype(float)
    return (rng_counts @ sg) / (rng_counts @ ng)


def evaluate(df, params, label, do_boot=True, ref="a", slope_ci=False):
    P = cand_probs(df, params)
    y = df["y"].to_numpy().astype(float)
    games = pd.factorize(df["game_id"] + "|" + df["season"])[0]
    G = int(games.max()) + 1
    res = {"n_rows": int(len(df)), "n_games": G, "cands": {}}
    rng = np.random.default_rng(BOOT_SEED)
    counts = rng.multinomial(G, np.full(G, 1.0 / G), size=BOOT_N).astype(float) if do_boot else None
    scount = rng.multinomial(G, np.full(G, 1.0 / G), size=SLOPE_BOOT_N).astype(float) if slope_ci else None
    groups = {"pooled": np.ones(len(df), bool)}
    for s in STATS:
        groups[STAT_LABEL[s]] = (df["stat"] == s).to_numpy()
    for gname, mk in groups.items():
        res["cands"][gname] = {}
        yb = y[mk]
        refb, refl = brier_loss(P[ref][mk], yb), logloss_loss(P[ref][mk], yb)
        for c, p in P.items():
            pm = p[mk]
            bl, ll = brier_loss(pm, yb), logloss_loss(pm, yb)
            a0, b0 = fit_logit(logit(pm), yb)
            ent = {"brier": float(bl.mean()), "logloss": float(ll.mean()),
                   "intercept": a0, "slope": b0, "citl": float(clipp(pm).mean() - yb.mean()),
                   "base_rate": float(yb.mean()), "reliability": reliability(pm, yb)}
            if do_boot and c != ref:
                gc = games[mk]
                for nm, dv in (("d_brier", bl - refb), ("d_logloss", ll - refl)):
                    bd = paired_boot(dv, gc, G, counts)
                    ent[nm] = {"diff": float(dv.mean()), "lo": float(np.percentile(bd, 2.5)), "hi": float(np.percentile(bd, 97.5)),
                               "p_two_sided": float(max(2 * min((bd <= 0).mean(), (bd >= 0).mean()), 1.0 / (BOOT_N + 1)))}
            if slope_ci and gname in ("pooled",) + tuple(STAT_LABEL.values()):
                x = logit(pm); gc = games[mk]; sl = []
                for r in range(SLOPE_BOOT_N):
                    wrow = scount[r][gc]
                    sl.append(fit_logit(x, yb, wrow)[1])
                ent["slope_ci"] = [float(np.nanpercentile(sl, 2.5)), float(np.nanpercentile(sl, 97.5))]
            res["cands"][gname][c] = ent
    return res


def shuffle_test(dev, params):
    rng = np.random.default_rng(BOOT_SEED)
    out = {}
    d = dev.copy()
    for s in STATS:
        mk = d.stat == s
        d.loc[mk, "y"] = rng.permutation(d.loc[mk, "y"].to_numpy())
    P = cand_probs(d, params)
    y = d["y"].to_numpy().astype(float)
    for c, p in P.items():
        out[c] = fit_logit(logit(p), y)[1]
    return out


def cmd_analyse(a):
    rows = pd.read_csv(os.path.join(a.out, "rows.csv"), dtype={"game_id": str})
    is25 = rows.season == "2025-26"
    pops = {
        "primary": rows[rows.primary],
        "S1": rows[rows.s1],
    }
    result = {"settings": dict(CLIP=CLIP, DEV_END=DEV_END, H1_START=H1_START, BOOT_N=BOOT_N, SEED=BOOT_SEED)}
    for pname, pop in pops.items():
        dev = pop[(pop.season == "2025-26") & (pop.date < DEV_END)]
        h1 = pop[(pop.season == "2025-26") & (pop.date >= H1_START)]
        h2 = pop[pop.season == "2024-25"]
        params = tune(dev)                      # tuned on dev ONLY
        R = {"params": params, "windows": {}}
        R["shuffle_dev_slopes"] = shuffle_test(dev, params)
        R["windows"]["dev"] = evaluate(dev, params, "dev")
        R["windows"]["H1"] = evaluate(h1, params, "H1", slope_ci=True)     # touched once
        R["windows"]["H2"] = evaluate(h2, params, "H2", slope_ci=True)
        R["line_rel"] = {w: {"rel_mean": float(df.rel.mean()), "rel_sd": float(df.rel.std()),
                              "rel_pct_mean": float(df.rel_pct.mean()),
                              "by_stat_base_rate": {s: float(df[df.stat == s].y.mean()) for s in STATS}}
                         for w, df in (("dev", dev), ("H1", h1), ("H2", h2))}
        result[pname] = R
    json.dump(result, open(os.path.join(a.out, "results.json"), "w"), indent=1)
    print("saved results.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build"); b.add_argument("--raw", required=True); b.add_argument("--out", required=True)
    sp.add_parser("validate-mc")
    n = sp.add_parser("analyse"); n.add_argument("--out", required=True)
    args = ap.parse_args()
    {"build": cmd_build, "analyse": cmd_analyse, "validate-mc": cmd_validate_mc}[args.cmd](args)
