#!/usr/bin/env python3
"""Freeze candidate (A) of EXP-20261021-05 into a coefficient file + parity fixture.
Reads the dev-fitted values from results5.json (NO refit). Usage:
  python3 make_fit_layer_artifact.py --scratch SCRATCH_DIR --repo REPO_ROOT
"""
import argparse, hashlib, json, os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import nba_calib as nc
import nba_refit as nr

HARNESS_COMMIT = "4b14b8e6d6c0c7be2098ab749b98ef22e6e26899"   # harness that produced results5.json
NBA = ".agents/skills/nba/nba_wong_choi"


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--scratch", required=True); ap.add_argument("--repo", required=True)
    a = ap.parse_args()
    res = json.load(open(os.path.join(a.scratch, "out5", "results5.json")))
    raw = {s: os.path.join(a.scratch, "raw", f) for s, f in nc.SEASONS.items()}
    model = {
        "model_id": "nba_fit_layer_A_v1",
        "created_at": "2026-10-21",
        "description": "Poisson/NB count model (mu = season stat-per-minute x prior-10 mean MIN) + per-stat logistic recalibration. "
                       "Offline candidate (A) of EXP-20261021-05, frozen exactly as dev-fitted. SHADOW use only.",
        "source_experiment": "EXP-20261021-05",
        "source_record": "docs/experiments/EXP-20261021-05-nba-pregame-population-refit.md",
        "harness_commit": HARNESS_COMMIT,
        "population": "pre-game knowable: >=10 prior games same season (strictly earlier date), prior-10 mean MIN >= 20",
        "dev_window": {"season": "2025-26", "date_lt": nc.DEV_END},
        "data_sha256": {s: sha(p) for s, p in raw.items()},
        "results_json_sha256": sha(os.path.join(a.scratch, "out5", "results5.json")),
        "fit_command": ["python3 -W ignore docs/experiments/patches/nba_calibration_exp20261021_02/nba_pregame.py build --raw <raw> --out <out5>",
                        "python3 -W ignore docs/experiments/patches/nba_calibration_exp20261021_02/nba_pregame.py run --out <out5>",
                        "python3 docs/experiments/patches/nba_calibration_exp20261021_02/make_fit_layer_artifact.py --scratch <scratch> --repo <repo>"],
        "mu_definition": "max(0.05, season_stat_total / season_minutes_total * prior10_mean_min); season totals over games with MIN>0 strictly before the game date",
        "count_model": {"PTS": {"family": "negbin", "alpha": res["params"]["alpha"]["PTS"]},
                        "REB": {"family": "poisson", "alpha": 0.0}, "AST": {"family": "poisson", "alpha": 0.0},
                        "FG3M": {"family": "poisson", "alpha": 0.0}},
        "negbin_parameterisation": "Var = mu + alpha*mu^2; r = 1/alpha; p = 1/(1+alpha*mu); P(X>=N) = 1 - sum_{k<N} pmf(k)",
        "recalibration": {s: {"a": res["coef_full"]["A"][s][0], "b": res["coef_full"]["A"][s][1]} for s in nc.STATS},
        "recalibration_formula": "p = sigmoid(a_s + b_s * logit(clip(p_count, 0.01, 0.99))); final p clipped to [0.01, 0.99]",
        "clip": [0.01, 0.99],
        "line_domain": "integer milestone N>=1, outcome = stat >= N",
        "notes": ["Not refit on H1/H2 or on newer data.", "Offline calibration only: no profit claim; lines near the player's mean.",
                  "Lines far from the prior-10 mean are outside the validated population."],
    }
    out = os.path.join(a.repo, NBA, "resources", "nba_fit_layer_A_v1.json")
    open(out, "w").write(json.dumps(model, indent=2, sort_keys=True) + "\n")
    print("model", out, sha(out))

    # parity fixture: recompute runtime inputs from raw logs, harness (A) probability via harness code path
    rows = pd.read_csv(os.path.join(a.scratch, "out5", "rows.csv"), dtype={"game_id": str})
    pool = rows[rows.pregame & (rows.virtual == 0)]
    smp = pool.sample(400, random_state=20261021).sort_values(["season", "date", "player_id", "stat", "line"]).reset_index(drop=True)
    logs = {}
    for s in nc.SEASONS:
        d = json.load(open(raw[s]))["resultSets"][0]
        df = pd.DataFrame(d["rowSet"], columns=d["headers"]); df["GAME_DATE"] = df["GAME_DATE"].astype(str).str[:10]
        logs[s] = df[df["MIN"] > 0]
    inputs = []
    for r in smp.itertuples():
        g = logs[r.season]; g = g[(g.PLAYER_ID == r.player_id) & (g.GAME_DATE < r.date)].sort_values(["GAME_DATE", "GAME_ID"])
        tot, mins = float(g[r.stat].sum()), float(g["MIN"].sum()); m10 = float(g["MIN"].to_numpy(float)[-10:].mean())
        assert np.isclose(max(0.05, tot / mins * m10), r.mu, rtol=0, atol=1e-12), (r, tot, mins, m10)
        inputs.append((tot, mins, m10))
    smp["season_stat_total"] = [x[0] for x in inputs]; smp["season_minutes_total"] = [x[1] for x in inputs]; smp["prior10_mean_min"] = [x[2] for x in inputs]
    params = {"w": res["params"]["w"], "alpha": res["params"]["alpha"]}
    P = nc.cand_probs(smp, params)
    coef = {s: tuple(v) for s, v in res["coef_full"]["A"].items()}
    pA = nr.recal_pred(smp, P, coef)
    fx = [dict(stat=r.stat, line=int(r.line), season_stat_total=r.season_stat_total, season_minutes_total=r.season_minutes_total,
               prior10_mean_min=r.prior10_mean_min, harness_p_count=float(P["c"][i]), harness_A=float(nc.clipp(pA[i])))
          for i, r in enumerate(smp.itertuples())]
    fxp = os.path.join(a.repo, NBA, "tests", "fixtures", "nba_fit_layer_A_parity.json")
    os.makedirs(os.path.dirname(fxp), exist_ok=True)
    json.dump({"source": "EXP-20261021-05 rows.csv sample (seed 20261021, n=400); inputs recomputed from raw logs, "
                         "harness_A = nba_refit.recal_pred on nba_calib.cand_probs (clipped to [0.01,0.99])",
               "rows_csv_sha256": sha(os.path.join(a.scratch, "out5", "rows.csv")), "units": fx}, open(fxp, "w"), indent=0)
    print("fixture", fxp, len(fx), sha(fxp))


if __name__ == "__main__":
    main()
