import sqlite3, sys, re
from collections import defaultdict
import numpy as np
sys.path.insert(0, "tennis-wong-choi/src")
from tennis_wc.pricing.families import family_for_market
c = sqlite3.connect(f"file:{sys.argv[1] if len(sys.argv) > 1 else 'tennis-wong-choi/tennis_wc.db'}?mode=ro", uri=True)
rows = c.execute("""SELECT p.match_id, p.market_key, p.selection, p.side, p.decimal_odds, p.market_prob_fair, p.model_prob_raw, p.result_status, p.match_date
 FROM prop_tracker p JOIN matches m ON m.id=p.match_id WHERE p.is_point_in_time=1 AND p.result_status IN ('WON','LOST')
 AND COALESCE(m.fixture_status,'')!='DISPUTED' AND p.decimal_odds>1""").fetchall()
def sidecls(fam, sel, side):
    s = (sel or "").lower()
    if s.startswith("under") or side == "under": return "under"
    if s.startswith("over") or re.match(r"^\d+\+$", s): return "over"
    return "fav" if False else "pick"
g = defaultdict(list)
for mid, mk, sel, side, o, f, mp, st, d in rows:
    fam = family_for_market(mk)
    g[(fam, sidecls(fam, sel, side))].append((mid, o, f, mp, 1.0 if st == "WON" else 0.0))
def lg(p): p = np.clip(p, 1e-4, 1-1e-4); return np.log(p/(1-p))
print(f"{'family':32s} {'side':6s} {'n':>6s} {'matches':>7s} {'odds':>5s} {'hit':>6s} {'fair':>6s} {'blindROI':>9s} {'mktSlope':>8s} {'LLmkt':>6s} {'LLmodel':>7s}")
rng = np.random.default_rng(20260826)
for k in sorted(g, key=lambda k: -len(g[k])):
    v = g[k]
    if len(v) < 150: continue
    mid = np.array([x[0] for x in v]); o = np.array([x[1] for x in v]); y = np.array([x[4] for x in v])
    f = np.array([np.nan if x[2] is None else x[2] for x in v]); mp = np.array([np.nan if x[3] is None else x[3] for x in v])
    pl = np.where(y == 1, o - 1, -1.0)
    # cluster bootstrap ROI CI
    by = defaultdict(list)
    for i, m in enumerate(mid): by[m].append(i)
    keys = list(by); num = np.array([pl[by[m]].sum() for m in keys]); den = np.array([len(by[m]) for m in keys])
    st = []
    for _ in range(1000):
        s = rng.integers(0, len(keys), len(keys)); st.append(num[s].sum()/den[s].sum())
    lo, hi = np.percentile(st, [2.5, 97.5])
    ok = ~np.isnan(f)
    slope = llm = llmod = np.nan
    if ok.sum() > 100:
        X = np.column_stack([np.ones(ok.sum()), lg(f[ok])]); w = np.zeros(2)
        for _ in range(50):
            p = 1/(1+np.exp(-X@w)); w -= np.linalg.solve((X.T*(p*(1-p)))@X + 1e-6*np.eye(2), X.T@(p-y[ok]))
        slope = w[1]
        pf = np.clip(f[ok], 1e-4, 1-1e-4); llm = -np.mean(y[ok]*np.log(pf)+(1-y[ok])*np.log(1-pf))
        okm = ok & ~np.isnan(mp)
        if okm.sum() > 100:
            pm = np.clip(mp[okm], 1e-4, 1-1e-4); llmod = -np.mean(y[okm]*np.log(pm)+(1-y[okm])*np.log(1-pm))
    print(f"{k[0]:32s} {k[1]:6s} {len(v):6d} {len(keys):7d} {np.mean(o):5.2f} {y.mean():6.3f} {np.nanmean(f):6.3f} {pl.mean()*100:+6.1f}% [{lo*100:+.1f},{hi*100:+.1f}] {slope:8.2f} {llm:6.3f} {llmod:7.3f}")
