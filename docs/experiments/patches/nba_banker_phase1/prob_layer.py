"""EXP-20261022-03 harness. Protocol frozen in the EXP doc (commit 18625c24) before this ran."""
import sys, os, warnings
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
warnings.filterwarnings("ignore")
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), *[".."] * 4))
sys.path.insert(0, os.path.join(REPO, ".agents/skills/nba/nba_wong_choi/scripts"))
import generate_nba_reports as live  # noqa: E402

c = pd.read_csv(sys.argv[1]).dropna(subset=["y"]).reset_index(drop=True)
c["ext"] = pd.to_datetime(c["extraction_time"])
late = (pd.to_datetime(c["date"]) + pd.Timedelta(hours=19) - (c["ext"] - pd.Timedelta(hours=14))).dt.total_seconds() < 0
c = c[~late].reset_index(drop=True)
days = sorted(c["date"].unique()); assert len(days) == 31
DEV, HOLD = days[:19], days[20:]; assert len(HOLD) == 11
c["dev"] = c["date"].isin(DEV); c["hold"] = c["date"].isin(HOLD)
print("rows", len(c), "dev", int(c.dev.sum()), "hold", int(c.hold.sum()))
print("quote after 19:00 ET on game day:", int(late.sum()), "(dropped)")

lg = lambda p: np.log(p / (1 - p))
sg = lambda z: 1 / (1 + np.exp(-z))
c["M"] = c["implied"]
# --- E: live-like engine (live function, missing context factors = 0 as in live when absent)
def eng(r):
    l10 = [float(x) for x in r.l10_list.split("|")]
    phase = "PLAYOFFS" if r.date >= "2026-04-18" else "MID_SEASON"
    p, _ = live.calc_adjusted_winprob(r.hit_l10 * 100, hit_l5=r.hit_l5 * 100, cov=r["cov"], avg=r.avg_l10,
                                      line_val=r.line, l10=l10, min_avg=r.min_avg, season_phase=phase)
    return max(1.0, min(98.0, p)) / 100
c["E"] = c.apply(eng, axis=1)
h10 = c.hit_l10.clip(.05, .95); l10c = lg(h10)
c["buf"] = ((c.avg_l10 - c.line) / c.avg_l10.where(c.avg_l10 > 0, 1)).clip(-1, 1)
STATS = ["PTS", "REB", "AST", "FG3M"]
S = pd.get_dummies(c["stat"]).reindex(columns=STATS, fill_value=0).astype(float)
Mx = lg(c["M"].clip(.02, .98))

def fit_predict(X, y_dev, mask_dev):
    m = LogisticRegression(penalty=None, max_iter=2000, fit_intercept=False).fit(X[mask_dev], y_dev)
    return sg(X @ m.coef_[0]), m.coef_[0]

yv = c["y"].values
Xb = np.hstack([S.values, S.values * l10c.values[:, None]])
Xc = np.hstack([S.values, Mx.values[:, None], l10c.values[:, None]])
Xd = np.hstack([Xc, c[["buf"]].values, c[["cov"]].values.clip(0, 3), (c["min_avg"] / 48).values[:, None], lg(c.hit_l5.clip(.05, .95)).values[:, None]])
dev = c.dev.values
c["B"], cb = fit_predict(Xb, yv[dev], dev)
c["C"], cc = fit_predict(Xc, yv[dev], dev)
c["D"], cd = fit_predict(Xd, yv[dev], dev)
print("C coefficients [a_PTS a_REB a_AST a_3PM beta_market gamma_L10]:", np.round(cc, 3))

# --- shuffle test: permute y within (date, stat) in dev, refit C, check holdout skill ~ 0
rng = np.random.default_rng(3)
ys = yv.copy()
for _, idx in c[c.dev].groupby(["date", "stat"]).groups.items():
    ys[idx] = rng.permutation(ys[idx])
ps, _ = fit_predict(Xc, ys[dev], dev)
hd = c.hold.values
slope_sh = LogisticRegression(penalty=None).fit(lg(np.clip(ps[hd], .01, .99)).reshape(-1, 1), yv[hd]).coef_[0][0]
base_br = float(np.mean((yv[dev].mean() - yv[hd]) ** 2))
br_sh = float(np.mean((ps[hd] - yv[hd]) ** 2))
print(f"shuffle test: holdout slope={slope_sh:+.3f} (uninformative: near-constant preds)  Brier={br_sh:.4f} vs base-rate Brier={base_br:.4f}")

H = c[c.hold].copy(); hy = H["y"].values
_real_skill = base_br - float(np.mean((c["C"].values[hd] - yv[hd]) ** 2)); _sh_skill = base_br - br_sh
print(f"shuffle skill {_sh_skill:+.5f} vs real C skill {_real_skill:+.5f}  ratio={_sh_skill/_real_skill:.3f} (need < 0.10)")
assert _sh_skill < 0.10 * _real_skill, "LEAK: shuffled-y model keeps holdout skill"
def brier(p): return np.mean((np.asarray(p) - hy) ** 2)
def logloss(p): p = np.clip(p, 1e-4, 1 - 1e-4); return -np.mean(hy * np.log(p) + (1 - hy) * np.log(1 - p))
def slope(p):
    m = LogisticRegression(penalty=None).fit(lg(np.clip(np.asarray(p), .01, .99)).reshape(-1, 1), hy)
    return m.coef_[0][0], m.intercept_[0]
hdays = np.array(HOLD)
idx_by = {d: np.where(H["date"].values == d)[0] for d in hdays}
rs = np.random.default_rng(11)
boots = [np.concatenate([idx_by[d] for d in rs.choice(hdays, len(hdays))]) for _ in range(2000)]

print("\n== holdout overall")
print(f"{'arm':4s} {'Brier':>7s} {'logloss':>8s} {'slope':>6s} {'icpt':>6s}")
for a in ["M", "E", "B", "C", "D"]:
    b, i = slope(H[a]); print(f"{a:4s} {brier(H[a]):7.4f} {logloss(H[a].values):8.4f} {b:6.3f} {i:+6.3f}")
print(f"base-rate Brier {base_br:.4f}")

def dbr(a, ref):
    d = [np.mean((H[a].values[ix] - hy[ix]) ** 2) - np.mean((H[ref].values[ix] - hy[ix]) ** 2) for ix in boots]
    return brier(H[a]) - brier(H[ref]), np.percentile(d, [2.5, 97.5])
def zone(a):
    m = H[a].values >= .8
    g = [ (H[a].values[ix][H[a].values[ix] >= .8].mean() - hy[ix][H[a].values[ix] >= .8].mean()) for ix in boots if (H[a].values[ix] >= .8).sum() > 30]
    return int(m.sum()), H[a].values[m].mean() if m.any() else float("nan"), hy[m].mean() if m.any() else float("nan"), np.percentile(g, [2.5, 97.5]) if g else (np.nan, np.nan)

print("\n== banker zone (p >= 0.8): n, mean p, actual, gap CI")
for a in ["M", "E", "B", "C", "D"]:
    n, mp, ya, ci = zone(a)
    print(f"{a:4s} n={n:5d} mean_p={mp:.3f} actual={ya:.3f} gap={mp-ya:+.3f} CI[{ci[0]:+.3f},{ci[1]:+.3f}]")

print("\n== deltas and verdicts")
for a in ["B", "C", "D"]:
    dE, cE = dbr(a, "E"); dM, cM = dbr(a, "M"); sl = slope(H[a])[0]
    n, mp, ya, ci = zone(a)
    ok = (cE[1] < 0, 0.85 <= sl <= 1.15, ci[0] <= 0 <= ci[1], cM[1] <= 0.001)
    verdict = "passes" if all(ok) else "fails"
    extra = " improves-on-market" if cM[1] < 0 else ""
    print(f"{a}: dBrier vs E {dE:+.4f} CI[{cE[0]:+.4f},{cE[1]:+.4f}] | vs M {dM:+.4f} CI[{cM[0]:+.4f},{cM[1]:+.4f}] | slope {sl:.3f} | zone gap CI [{ci[0]:+.3f},{ci[1]:+.3f}] "
          f"| checks(vsE<0, slope, zone∋0, vsM<=.001)={ok} -> {verdict}{extra}")

print("\n== per stat (holdout): Brier M / E / C and slope E / C")
for s in STATS:
    m = (H["stat"] == s).values
    hh = hy[m]
    f = lambda a: np.mean((H[a].values[m] - hh) ** 2)
    def sl2(a): return LogisticRegression(penalty=None).fit(lg(np.clip(H[a].values[m], .01, .99)).reshape(-1, 1), hh).coef_[0][0]
    print(f"{s:5s} n={int(m.sum()):5d} M={f('M'):.4f} E={f('E'):.4f} C={f('C'):.4f} D={f('D'):.4f} | slope E={sl2('E'):.2f} C={sl2('C'):.2f}")
