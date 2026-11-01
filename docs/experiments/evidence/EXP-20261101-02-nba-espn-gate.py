"""EXP-20261101-02 regression gate: nba.com ruler vs ESPN ruler, same rows.

usage: python3 EXP-20261101-02-nba-espn-gate.py <repo> <rebuild out dir> <verified_dataset_v2/dataset.csv>

Primary (live model, pre-registered): C layer p_final = calibrated_prob(stat,
price, hit_rate_l10) on every paired labelled row; ESPN minus nba.com Brier,
US-date cluster bootstrap 2000x, seed 20261101.
Secondary (shadow only): the fixed v2 RF protocol (train_model) on
  A  v2 dataset, 27 features incl. defender_pm (the 2026-10-23 reproduction),
  B  nba.com ruler, 26 features (defender_pm removed),
  C  ESPN ruler, 26 features;
paired terminal Brier B-A (defender removal) and C-B (source switch).
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

repo, out, v2_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(repo / ".agents/scripts/nba_ml"))
sys.path.insert(0, str(repo / ".agents/skills/nba/nba_wong_choi/scripts"))
import nba_prob_layer
import train_nba_xgboost as T
from nba_ml_features import FEATURE_COLS, check_single_source

KEY = ["game_group", "player_key", "stat_category", "line_value"]
nb = pd.read_csv(out / "dataset_nbacom.csv")
es = pd.read_csv(out / "dataset_espn.csv")
assert check_single_source(nb.stat_source) == {"nbacom": 1.0}
assert check_single_source(es.stat_source) == {"espn": 1.0}
nb, es = nb.sort_values(KEY).reset_index(drop=True), es.sort_values(KEY).reset_index(drop=True)
assert (nb[KEY].values == es[KEY].values).all() and (nb.hit.values == es.hit.values).all()
y = nb.hit.astype(int).to_numpy()
days = nb.game_date.to_numpy()
unique = sorted(set(days))
index = [np.flatnonzero(days == d) for d in unique]
rng = np.random.default_rng(20261101)
draws = [np.concatenate([index[i] for i in rng.integers(0, len(index), len(index))]) for _ in range(2000)]


def paired(loss_a, loss_b, rows=None):
    """mean(b - a) and its date-cluster 95% interval over ``rows`` (all if None)."""
    d = np.asarray(loss_b) - np.asarray(loss_a)
    if rows is None:
        boots = [d[i].mean() for i in draws]
        return float(d.mean()), [float(x) for x in np.percentile(boots, [2.5, 97.5])]
    sub_days = days[rows]
    sub_unique = sorted(set(sub_days))
    sub_index = [np.flatnonzero(sub_days == u) for u in sub_unique]
    r = np.random.default_rng(20261101)
    boots = [d[np.concatenate([sub_index[i] for i in r.integers(0, len(sub_index), len(sub_index))])].mean()
             for _ in range(2000)]
    return float(d.mean()), [float(x) for x in np.percentile(boots, [2.5, 97.5])]


def c_layer(frame):
    return np.asarray([nba_prob_layer.calibrated_prob(s, p, h) / 100
                       for s, p, h in zip(frame.stat_category, frame.market_price, frame.hit_rate_l10)], float)


def brier(p):
    return (p - y) ** 2


def logloss(p):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


p_nb, p_es = c_layer(nb), c_layer(es)
delta, ci = paired(brier(p_nb), brier(p_es))
ll_delta, ll_ci = paired(logloss(p_nb), logloss(p_es))
primary = {
    "rows": int(len(y)), "events": int(nb.game_group.nunique()), "dates": len(unique),
    "brier_nbacom": float(brier(p_nb).mean()), "brier_espn": float(brier(p_es).mean()),
    "delta_brier_espn_minus_nbacom": delta, "ci95": ci,
    "delta_logloss": ll_delta, "logloss_ci95": ll_ci,
    "hit_rate_l10_identical": float((nb.hit_rate_l10.values == es.hit_rate_l10.values).mean()),
    "p_changed_rows": int((np.abs(p_nb - p_es) > 1e-9).sum()),
    "p_mean_abs_move_pp": float(100 * np.abs(p_nb - p_es).mean()),
    "p_max_abs_move_pp": float(100 * np.abs(p_nb - p_es).max()),
    "crossings_at_50_60_70_80": [int(((p_nb >= t) != (p_es >= t)).sum()) for t in (.5, .6, .7, .8)],
}
upper, lower = ci[1], ci[0]
primary["verdict"] = ("KEEP" if upper <= 0.002 else "REJECT" if lower > 0 else "NEEDS MORE TESTING")

# Secondary: RF arms on the fixed v2 temporal protocol.
v2 = pd.read_csv(v2_path)
v2 = v2[v2.hit.notna()].copy()
v2["line_value"] = v2.line_value.astype(float)
v2 = v2.merge(nb[KEY], on=KEY).sort_values(KEY).reset_index(drop=True)
assert (v2[KEY].values == nb[KEY].values).all()
v2_cols = [*FEATURE_COLS[:FEATURE_COLS.index("opp_pace") + 1], "defender_pm", *FEATURE_COLS[FEATURE_COLS.index("opp_pace") + 1:]]
assert len(v2_cols) == 27
context = nb[["game_date", "game_group", "stat_category", "market_price"]].copy()
context["dataset_sha256"] = "EXP-20261101-02 paired rows"
arms = {}
for name, frame, cols in (("A_v2_27_with_defender", v2, v2_cols), ("B_nbacom_26", nb, FEATURE_COLS),
                          ("C_espn_26", es, FEATURE_COLS)):
    X = frame[cols].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    model, metrics, X_test, y_test, pred, prob = T.train_model(X, pd.Series(y), context)
    arms[name] = {"terminal_brier": metrics["brier_score"], "terminal_auc": metrics["roc_auc"],
                  "test_size": metrics["test_size"], "terminal_dates": metrics["terminal_diagnostic_dates"],
                  "folds_brier": [f["brier_score"] for f in metrics["folds"]],
                  "_prob": prob, "_rows": X_test.index.to_numpy()}
rows = arms["B_nbacom_26"]["_rows"]
assert all((a["_rows"] == rows).all() for a in arms.values())
yt = y[rows]
loss = {k: (a["_prob"] - yt) ** 2 for k, a in arms.items()}


def paired_terminal(a, b):
    d = loss[b] - loss[a]
    sub = days[rows]
    su = sorted(set(sub))
    si = [np.flatnonzero(sub == u) for u in su]
    r = np.random.default_rng(20261101)
    boots = [d[np.concatenate([si[i] for i in r.integers(0, len(si), len(si))])].mean() for _ in range(2000)]
    return {"delta": float(d.mean()), "ci95": [float(x) for x in np.percentile(boots, [2.5, 97.5])],
            "date_clusters": len(su)}


secondary = {k: {kk: vv for kk, vv in a.items() if not kk.startswith("_")} for k, a in arms.items()}
secondary["B_minus_A_defender_removal"] = paired_terminal("A_v2_27_with_defender", "B_nbacom_26")
secondary["C_minus_B_source_switch"] = paired_terminal("B_nbacom_26", "C_espn_26")
c_terminal_nb, c_terminal_es = brier(p_nb)[rows], brier(p_es)[rows]
secondary["current_C_terminal_brier"] = {"nbacom": float(c_terminal_nb.mean()), "espn": float(c_terminal_es.mean())}
result = {"primary_C_layer": primary, "secondary_RF_shadow": secondary,
          "probability_model_id": nba_prob_layer.probability_model_id()}
(out / "gate_result.json").write_text(json.dumps(result, indent=1))
print(json.dumps(result, indent=1))
