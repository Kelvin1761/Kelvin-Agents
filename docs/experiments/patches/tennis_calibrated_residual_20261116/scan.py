"""Residual scan on top of the market-anchored calibration (EXP-20261116-08 arm C).

Pre-registered before looking: base p = per-family C fit on dev (<=2026-10-15),
market fair where a family has <50 dev rows. Residual r = y - p.
Segments (fixed list): family, odds band, favourite/underdog, tier, tour, surface,
hours before start. A segment is a candidate only if its DEV mean residual CI
(match bootstrap 2000, seed 20260826) excludes 0 AND bets with p*odds>1 inside
it have dev ROI > 0. Candidates are then reported on HOLDOUT once, untouched.
Exploratory: Bonferroni over the segment count is applied to the dev screen.
"""
import sys, sqlite3, json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "tennis-wong-choi/src"))
sys.path.insert(0, str(REPO / "docs/experiments/patches/tennis_family_calibration_20261116"))
from tennis_wc.pricing.families import family_for_market
from tennis_wc.pricing.props import tier_of
from tennis_wc.select.featured import FAMILIES
import study as C

DEV_END = "2026-10-15"
DB = sys.argv[1] if len(sys.argv) > 1 else f"{REPO}/tennis-wong-choi/tennis_wc.db"
conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
rows = []
for r in conn.execute("""
  SELECT p.match_id, p.match_date, p.market_key, p.decimal_odds o, p.model_prob_raw mp, p.market_prob_fair f,
         p.result_status s, p.priced_at, p.recorded_at, m.start_time_utc st, m.tour,
         (SELECT t.name FROM tournaments t WHERE t.id=m.tournament_id) tn,
         (SELECT tl.level FROM tournament_levels tl WHERE tl.tournament_id=m.tournament_id ORDER BY tl.id DESC LIMIT 1) lvl,
         (SELECT tl.surface FROM tournament_levels tl WHERE tl.tournament_id=m.tournament_id AND tl.surface IS NOT NULL ORDER BY tl.id DESC LIMIT 1) surf
  FROM prop_tracker p JOIN matches m ON m.id=p.match_id
  WHERE p.is_point_in_time=1 AND p.result_status IN ('WON','LOST') AND COALESCE(m.fixture_status,'')!='DISPUTED'
    AND p.model_prob_raw IS NOT NULL AND p.market_prob_fair IS NOT NULL AND p.decimal_odds>1"""):
    fam = family_for_market(r["market_key"] or "")
    if fam not in FAMILIES: continue
    def ts(x):
        try: return datetime.fromisoformat(str(x).replace("Z","+00:00"))
        except Exception: return None
    a, b = ts(r["priced_at"] or r["recorded_at"]), ts(r["st"])
    hrs = (b-a).total_seconds()/3600 if a and b and a.tzinfo and b.tzinfo else None
    o = r["o"]
    rows.append(dict(match=r["match_id"], date=r["match_date"], fam=fam, odds=o, model=r["mp"], fair=r["f"],
        y=1.0 if r["s"]=="WON" else 0.0,
        seg={"family": fam,
             "odds": "<1.5" if o<1.5 else "1.5-2" if o<2 else "2-3" if o<3 else ">=3",
             "side": "fav" if r["f"]>=0.5 else "dog",
             "tier": tier_of(r["tn"], r["lvl"]),
             "tour": r["tour"] or "UNKNOWN",
             "surface": (r["surf"] or "unknown").lower(),
             "lead": "unknown" if hrs is None else "<2h" if hrs<2 else "2-8h" if hrs<8 else "8-24h" if hrs<24 else ">=24h"}))
dev=[r for r in rows if r["date"]<=DEV_END]; hold=[r for r in rows if r["date"]>DEV_END]
fits={}
for fam in FAMILIES:
    d=[r for r in dev if r["fam"]==fam]
    if len(d)<50: continue
    y=np.array([r["y"] for r in d]); lf=C.logit([r["fair"] for r in d]); lm=C.logit([r["model"] for r in d])
    fits[fam]=C.fit_logistic(np.column_stack([lf,lm-lf]),y)
for r in rows:
    w=fits.get(r["fam"])
    if w is None: r["p"]=r["fair"]
    else:
        lf=C.logit([r["fair"]])[0]; lm=C.logit([r["model"]])[0]
        r["p"]=float(C.predict(w,np.array([[lf,lm-lf]]))[0])
def summ(rs, draws=2000):
    if not rs: return None
    m=[r["match"] for r in rs]; res=np.array([r["y"]-r["p"] for r in rs])
    pt,lo,hi=C.cluster_ci(m,res,draws=draws,ratio_den=np.ones(len(rs)))
    bet=np.array([r["p"]*r["odds"]>1 for r in rs]); pl=np.array([(r["odds"]-1) if r["y"] else -1.0 for r in rs])
    roi=(pl*bet).sum()/bet.sum() if bet.sum() else None
    blind=pl.mean()
    return dict(n=len(rs),matches=len(set(m)),resid=pt,lo=lo,hi=hi,bets=int(bet.sum()),roi=roi,blind=blind)
segs=defaultdict(list)
for i,r in enumerate(dev):
    for k,v in r["seg"].items(): segs[(k,v)].append(r)
K=len(segs); z_q=1-0.05/K/2
print(f"dev {len(dev)} rows, holdout {len(hold)}; {K} segments; Bonferroni level {0.05/K:.4f}")
cands=[]
print(f"{'segment':34s} {'n':>5s} {'resid':>7s} [95% CI]          bets  roi(p*o>1)  blind")
for key in sorted(segs):
    s=summ(segs[key])
    if s["n"]<100: continue
    flag=""
    # Bonferroni CI via wider bootstrap percentile
    m=[r["match"] for r in segs[key]]; res=np.array([r["y"]-r["p"] for r in segs[key]])
    rng=np.random.default_rng(20260826); by=defaultdict(list)
    for i,mm in enumerate(m): by[mm].append(i)
    ks=list(by); num=np.array([res[by[k]].sum() for k in ks]); den=np.array([len(by[k]) for k in ks])
    st = []
    for _ in range(2000):
        ss=rng.integers(0,len(ks),len(ks)); st.append(num[ss].sum()/den[ss].sum())
    blo,bhi=np.percentile(st,[100*(1-z_q),100*z_q])
    if (blo>0 or bhi<0): flag="BONF"
    if flag and s["roi"] is not None and s["roi"]>0: cands.append(key); flag+=" CAND"
    roi="—" if s["roi"] is None else f"{s['roi']*100:+.1f}%"
    print(f"{key[0]+'='+key[1]:34s} {s['n']:5d} {s['resid']:+.4f} [{s['lo']:+.4f},{s['hi']:+.4f}] {s['bets']:5d} {roi:>9s} {s['blind']*100:+.1f}% {flag}")
print("\nholdout check of dev candidates:", cands)
for key in cands:
    h=[r for r in hold if r["seg"][key[0]]==key[1]]; s=summ(h,4000)
    if s: print(f"  {key}: n={s['n']} resid {s['resid']:+.4f} [{s['lo']:+.4f},{s['hi']:+.4f}] bets {s['bets']} roi {s['roi'] and s['roi']*100:+.1f}% blind {s['blind']*100:+.1f}%")
print("\noverall holdout, bet when p*odds>1:", summ(hold,4000))
