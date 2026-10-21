#!/usr/bin/env python3
"""EXP-20261021-05 — fitted adjustment layer on a PRE-GAME-KNOWABLE population (analysis only).
Protocol frozen in docs/experiments/EXP-20261021-05-nba-pregame-population-refit.md.
  python3 nba_pregame.py build --raw RAW --out OUT5
  python3 nba_pregame.py check --old OUT3 --out OUT5
  python3 nba_pregame.py run   --out OUT5
"""
import argparse, json, os, sys
from datetime import date, timedelta
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import nba_calib as nc
import nba_refit as nr

ZONES = (0.70, 0.80)


# ───────────────────────── build ─────────────────────────
def load_all(raw_dir, season):
    d = json.load(open(os.path.join(raw_dir, nc.SEASONS[season])))["resultSets"][0]
    df = pd.DataFrame(d["rowSet"], columns=d["headers"])
    df["GAME_DATE"] = df["GAME_DATE"].astype(str).str[:10]
    df["is_home"] = df["MATCHUP"].str.contains("vs.", regex=False)
    return df.sort_values(["PLAYER_ID", "GAME_DATE", "GAME_ID"]).reset_index(drop=True)   # MIN==0 rows KEPT


def build_rows(df, season, gen):
    team_dates = df.groupby("TEAM_ABBREVIATION")["GAME_DATE"].apply(lambda s: sorted(set(s))).to_dict()
    team_dateset = {t: set(v) for t, v in team_dates.items()}
    info = {}
    for r in df.drop_duplicates(["TEAM_ABBREVIATION", "GAME_DATE"]).itertuples():
        info[(r.TEAM_ABBREVIATION, r.GAME_DATE)] = (str(r.GAME_ID), bool(r.is_home))
    rows = []
    for pid, g in df.groupby("PLAYER_ID", sort=False):
        dates = g["GAME_DATE"].tolist()
        mins = g["MIN"].to_numpy(float); home = g["is_home"].to_numpy(); team = g["TEAM_ABBREVIATION"].tolist()
        gids = g["GAME_ID"].astype(str).tolist()
        vals_all = {s: g[s].to_numpy(float) for s in nc.STATS}
        pts = vals_all["PTS"]
        played = np.where(mins > 0)[0]
        pdates = [dates[j] for j in played]

        def emit(D, tm, gid, is_home_i, min_g, actual, virtual, old_ok):
            kp = nc.prior_count(pdates, D)
            if kp < 10:
                return
            idx = played[:kp]
            assert all(dates[j] < D for j in idx)                       # runtime point-in-time assert
            min10 = mins[idx[kp - 10:kp]]; min_avg10 = float(min10.mean())
            pregame = bool(min_avg10 >= 20); old = bool(old_ok)
            if not (pregame or old):
                return
            prev = (date.fromisoformat(D) - timedelta(days=1)).isoformat()
            is_b2b = prev in team_dateset[tm]
            hm = home[idx]; pp = pts[idx]
            hp = float(pp[hm].mean()) if hm.sum() >= 3 else None
            rp = float(pp[~hm].mean()) if (~hm).sum() >= 3 else None
            for s in nc.STATS:
                v = vals_all[s][idx]
                l10 = [float(x) for x in v[kp - 10:kp][::-1]]
                avg, med, sd, cov = gen.compute_stats(l10)
                m = float(np.mean(l10))
                if m < 1.0:
                    continue
                mu = max(0.05, float(v.sum()) / float(mins[idx].sum()) * min_avg10)
                for n in nc.choose_lines(m):
                    hr10 = gen.hit_rate(l10, n)[0]; hr5 = gen.hit_rate(l10[:5], n)[0]
                    e, bd = gen.calc_adjusted_winprob(
                        base_rate=hr10, hit_l5=hr5, cov=cov, avg=avg, line_val=float(n), is_b2b=is_b2b,
                        is_home=bool(is_home_i), l10=l10, min_avg=min_avg10, home_ppg=hp, road_ppg=rp,
                        season_phase="MID_SEASON")
                    rows.append(dict(
                        season=season, date=D, game_id=gid, player_id=int(pid), stat=s, line=n, m=m, rel=n - m,
                        pregame=pregame, old=old, virtual=int(virtual), min_g=float(min_g),
                        y=int(actual[s] >= n), actual=float(actual[s]), a=hr10 / 100.0,
                        hit_sea=float((v >= n).mean()), mu=mu, e=e / 100.0, f=nc.live_mc_prob(avg, sd, n, s), k=kp,
                        t_trend=bd["trend"], t_cov=bd["cov"], t_buffer=bd["buffer"], t_sip_n04=bd["sip_n04_trend_protect"],
                        t_sip_n01=bd["sip_n01_bench_risk"], t_b2b=bd["b2b_fatigue"], t_home_away=bd["home_away"]))

        for i in range(len(g)):
            emit(dates[i], team[i], gids[i], home[i], mins[i], {s: vals_all[s][i] for s in nc.STATS}, False, mins[i] >= 15)
        # single-game absences of rotation players (virtual units, y=0): played in team's previous AND next game, same team
        pset = {dates[j]: team[j] for j in played}
        if len(played) >= 10:
            for tm in set(team):
                tg = team_dates[tm]
                for j in range(1, len(tg) - 1):
                    if tg[j] in set(dates):
                        continue
                    if pset.get(tg[j - 1]) == tm and pset.get(tg[j + 1]) == tm:
                        gid, ih = info[(tm, tg[j])]
                        emit(tg[j], tm, gid, ih, 0.0, {s: 0.0 for s in nc.STATS}, True, False)
    return rows


def cmd_build(a):
    gen = nc.load_live(); allr = []
    for season in nc.SEASONS:
        allr += build_rows(load_all(a.raw, season), season, gen); print(season, len(allr), flush=True)
    os.makedirs(a.out, exist_ok=True)
    pd.DataFrame(allr).to_csv(os.path.join(a.out, "rows.csv"), index=False); print("saved", len(allr))


def cmd_check(a):
    old = pd.read_csv(os.path.join(a.old, "rows.csv"), dtype={"game_id": str})
    new = pd.read_csv(os.path.join(a.out, "rows.csv"), dtype={"game_id": str})
    keys = ["season", "game_id", "player_id", "stat", "line"]
    o = old[old.s1].sort_values(keys).reset_index(drop=True)
    n = new[(new.pregame) & (new.virtual == 0) & (new.min_g > 0)].sort_values(keys).reset_index(drop=True)
    assert len(o) == len(n), (len(o), len(n))
    for c in ["y", "a", "mu", "e", "f", "t_sip_n01", "t_cov", "k"]:
        assert np.allclose(o[c].to_numpy(float), n[c].to_numpy(float)), c
    o2 = old[old.primary].sort_values(keys).reset_index(drop=True)
    n2 = new[(new.old) & (new.virtual == 0)].sort_values(keys).reset_index(drop=True)
    assert len(o2) == len(n2), (len(o2), len(n2))
    assert np.allclose(o2["y"].to_numpy(float), n2["y"].to_numpy(float))
    print("CHECK OK: new MIN>0 pregame rows == EXP-03 S1 rows (%d); old-primary rows == EXP-03 primary (%d)" % (len(o), len(o2)))


# ───────────────────────── evaluate ─────────────────────────
def evaluate(df, probs, slope_ci=False):
    y = df["y"].to_numpy().astype(float)
    codes = pd.factorize(df["game_id"] + "|" + df["season"])[0]; G = int(codes.max()) + 1
    rng = np.random.default_rng(nc.BOOT_SEED)
    cnt = rng.multinomial(G, np.full(G, 1.0 / G), size=nc.BOOT_N).astype(float)
    scnt = rng.multinomial(G, np.full(G, 1.0 / G), size=300).astype(float) if slope_ci else None
    groups = {"pooled": np.ones(len(df), bool)}
    for s in nc.STATS:
        groups[nc.STAT_LABEL[s]] = (df["stat"] == s).to_numpy()
    out = {"n_rows": int(len(df)), "n_games": G, "groups": {}}
    for g, mk in groups.items():
        yb, cb = y[mk], codes[mk]
        L = {k: nc.brier_loss(p[mk], yb) for k, p in probs.items()}; LL = {k: nc.logloss_loss(p[mk], yb) for k, p in probs.items()}
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
                        e[f"d_{nm}_vs_{ref}"] = {"diff": float(d.mean()), "lo": nr.ci(b)[0], "hi": nr.ci(b)[1]}
            if g == "pooled":
                if slope_ci:
                    x = nc.logit(p[mk]); e["slope_ci"] = nr.ci([nc.fit_logit(x, yb, scnt[r][cb])[1] for r in range(300)])
                e["reliability"] = nc.reliability(p[mk], yb)
                pc = nc.clipp(p[mk]); e["zones"] = {}
                for zt in ZONES:
                    z = pc >= zt
                    e["zones"][str(zt)] = {"n": int(z.sum()), "share": float(z.mean()),
                                           "mean_p": float(pc[z].mean()) if z.any() else None,
                                           "hit": float(yb[z].mean()) if z.any() else None}
            R[k] = e
        out["groups"][g] = R
    return out


def predict(df, params, scaler, models):
    P = nr.predict_all(df, params, scaler, models); P["E"] = df["e"].to_numpy(); return P


def verdict(h1, dev, h2, k):
    P = lambda W: W["groups"]["pooled"][k]
    c = {"c1": P(h1)["d_brier_vs_a"]["hi"] < 0, "c2": P(dev)["d_brier_vs_a"]["diff"] < 0, "c3": P(h2)["d_brier_vs_a"]["hi"] < 0,
         "c4": 0.85 <= P(h1)["slope"] <= 1.15}
    bad = [(b[0], b[1], b[2], b[3]) for b in P(h1)["reliability"] if b[1] >= 500 and abs(b[2] - b[3]) > 0.05]
    c["c5"] = not bad
    c["c6"] = (P(h2)["d_brier_vs_c"]["hi"] < 0) if k in ("A", "B", "C") else None
    need = [c[x] for x in ("c1", "c2", "c3", "c4", "c5")] + ([c["c6"]] if k in ("A", "B", "C") else [])
    return {**{x: (None if v is None else bool(v)) for x, v in c.items()}, "bad_buckets": bad,
            "verdict": ("passes" if all(need) else "not shown") if k in ("A", "B", "C") else
                       ("n/a (comparison arm); conditions " + ("all hold" if all(need) else "do not all hold"))}


def bias_check(dev, params):
    P = nc.cand_probs(dev, params); resid = dev["y"].to_numpy() - P["c"]
    codes = pd.factorize(dev["game_id"] + "|" + dev["season"])[0]; G = int(codes.max()) + 1
    cnt = np.random.default_rng(nc.BOOT_SEED).multinomial(G, np.full(G, 1.0 / G), size=nc.BOOT_N).astype(float)
    out = {}
    for name, mk in (("<20", dev["t_sip_n01"] == -5), ("20-25", dev["t_sip_n01"] == -3), (">=25", dev["t_sip_n01"] == 0)):
        mk = mk.to_numpy()
        if mk.sum() == 0:
            out[name] = {"n": 0}; continue
        r = np.where(mk, resid, 0.0); sg = np.bincount(codes, weights=r, minlength=G); ng = np.bincount(codes, weights=mk.astype(float), minlength=G)
        b = (cnt @ sg) / (cnt @ ng)
        out[name] = {"n": int(mk.sum()), "mean_resid": float(resid[mk].mean()), "ci": nr.ci(b)}
    out["biased"] = bool(any(v.get("n", 0) > 0 and abs(v["mean_resid"]) > 0.03 and (v["ci"][0] > 0 or v["ci"][1] < 0)
                             for v in out.values() if isinstance(v, dict) and "ci" in v))
    return out


def dnp_stats(rows):
    out = {}
    for w, mk in (("dev", (rows.season == "2025-26") & (rows.date < nc.DEV_END)),
                  ("H1", (rows.season == "2025-26") & (rows.date >= nc.H1_START)), ("H2", rows.season == "2024-25")):
        d = rows[mk & rows.pregame]
        u = d.drop_duplicates(["player_id", "game_id"])
        real, virt = u[u.virtual == 0], u[u.virtual == 1]
        out[w] = {"real_units": int(len(real)), "absent_units": int(len(virt)),
                  "absent_rate": float(len(virt) / max(1, len(real) + len(virt))),
                  "real_min0_units": int((real.min_g == 0).sum()), "real_min_lt15_share": float((real.min_g < 15).mean()),
                  "real_min_lt10_share": float((real.min_g < 10).mean())}
    return out


def cmd_run(a):
    rows = pd.read_csv(os.path.join(a.out, "rows.csv"), dtype={"game_id": str})
    sl = lambda pop: (pop[(pop.season == "2025-26") & (pop.date < nc.DEV_END)], pop[(pop.season == "2025-26") & (pop.date >= nc.H1_START)], pop[pop.season == "2024-25"])
    prim = rows[rows.pregame & (rows.virtual == 0)]
    dev, h1, h2 = sl(prim)
    params = nc.tune(dev); scaler = nr.fit_scaler(dev, params)
    lam, lam_scores, inner = nr.choose_lambda(dev, params, scaler)
    models, _ = nr.fit_models(dev, params, scaler, lam)
    res = {"params": params, "lambda_C": lam, "lambda_val_brier": {str(k): v for k, v in lam_scores.items()}, "inner": inner,
           "coef_full": {"A": {s: list(v) for s, v in models["A"].items()}, "B": dict(zip(nr.NAMES, map(float, models["B"]))),
                         "C": dict(zip(nr.NAMES, map(float, models["C"])))},
           "coef_raw": {"B": nr.raw_coefs(models["B"], scaler), "C": nr.raw_coefs(models["C"], scaler)}}
    Bb, Cb, Ab = nr.coef_bootstrap(dev, params, scaler, lam)
    res["coef_ci"] = {"B": {n: nr.ci(Bb[:, i]) for i, n in enumerate(nr.NAMES)}, "C": {n: nr.ci(Cb[:, i]) for i, n in enumerate(nr.NAMES)},
                      "A": {f"{s}_{k}": nr.ci(Ab[:, 2 * j + q]) for j, s in enumerate(nc.STATS) for q, k in enumerate(("a", "b"))}, "B_kept": {}}
    for i, n in enumerate(nr.FEATS, start=1):
        if n.startswith("t_"):
            res["coef_ci"]["B_kept"][n] = nr.ci(Bb[:, i] / float(scaler["sd"][n]) / 0.04)
    res["shuffle"] = nr.shuffle_test(dev, params, scaler)
    res["bias_check"] = bias_check(dev, params)
    res["dnp"] = dnp_stats(rows)
    W = {}
    for w, df, sc in (("dev", dev, False), ("H1", h1, True), ("H2", h2, True)):
        W[w] = evaluate(df, predict(df, params, scaler, models), slope_ci=sc)
    res["primary"] = {"windows": W}
    res["verdicts"] = {k: verdict(W["H1"], W["dev"], W["H2"], k) for k in ("c", "E", "A", "B", "C")}
    for name, pop in (("old_MINg15", rows[rows.old & (rows.virtual == 0)]), ("S_dnp_worst_case", rows[rows.pregame])):
        d_, h1_, h2_ = sl(pop)
        res[name] = {"windows": {w: evaluate(df, predict(df, params, scaler, models)) for w, df in (("dev", d_), ("H1", h1_), ("H2", h2_))}}
    json.dump(res, open(os.path.join(a.out, "results5.json"), "w"), indent=1, default=float)
    print("saved; lambda", lam, "bias", res["bias_check"]["biased"], {k: v["verdict"] for k, v in res["verdicts"].items()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build"); b.add_argument("--raw", required=True); b.add_argument("--out", required=True)
    c = sp.add_parser("check"); c.add_argument("--old", required=True); c.add_argument("--out", required=True)
    r = sp.add_parser("run"); r.add_argument("--out", required=True)
    args = ap.parse_args(); {"build": cmd_build, "check": cmd_check, "run": cmd_run}[args.cmd](args)
