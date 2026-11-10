import sqlite3, sys, math, random, collections
import numpy as np
sys.path.insert(0,"/Users/imac/Antigravity-repo/tennis-wong-choi/src")
from tennis_wc.pricing.families import family_for_market
c=sqlite3.connect("file:/Users/imac/Antigravity-repo/tennis-wong-choi/tennis_wc.db?mode=ro",uri=True)
c.row_factory=sqlite3.Row
lv={}
for r in c.execute("select tournament_id, level from tournament_levels order by (level='UNKNOWN'), id"):
    lv.setdefault(r[0], r[1])
def normlv(l):
    l=(l or 'UNKNOWN').upper().replace(' ','_')
    if l in('1000','WTA_1000','ATP_1000','GRAND_SLAM','ATP_500','WTA_500','ATP_250','WTA_250','ATP_FINALS','WTA_FINALS'): return 'TOUR'
    if l in('125','CHALLENGER'): return 'CHALL'
    return l
rows=[]
for r in c.execute("""select p.id,p.match_id,p.match_date,p.market_key,p.feed_market_name,p.line,p.side,p.decimal_odds o,p.model_prob_raw mr,p.model_prob mp,
 p.market_prob_fair mk,p.blended_prob bl,p.edge,p.ev,p.is_value v,p.result_status rs,m.tour,m.tournament_id,l.clv_vs_close clv,l.close_pre_start_odds co
 from prop_tracker p join matches m on m.id=p.match_id left join prop_price_log l on l.prop_id=p.id
 where p.is_point_in_time=1 and p.result_status in ('WON','LOST') and m.fixture_status!='DISPUTED'"""):
    d=dict(r); d['fam']=family_for_market(d['market_key'], d['feed_market_name'] or ''); d['y']=1 if d['rs']=='WON' else 0
    d['pl']=d['o']-1 if d['y'] else -1.0; d['lv']=normlv(lv.get(d['tournament_id'])); d['mon']=d['match_date'][:7]
    rows.append(d)
print("PIT settled rows",len(rows),"matches",len({r['match_id'] for r in rows}), min(r['match_date'] for r in rows), max(r['match_date'] for r in rows))
def boot(rs, f, n=2000, seed=20260826):
    by=collections.defaultdict(list)
    for r in rs: by[r['match_id']].append(r)
    keys=list(by); rng=random.Random(seed); out=[]
    for _ in range(n):
        s=[]
        for k in rng.choices(keys,k=len(keys)): s+=by[k]
        out.append(f(s))
    out.sort(); return out[int(.025*n)], out[int(.975*n)-1]
roi=lambda s: sum(r['pl'] for r in s)/len(s) if s else 0
def line(name, s, nb=1000):
    if len(s)<30: print(f"  {name:34s} n={len(s):5d} (thin) roi={roi(s):+.3f}"); return
    lo,hi=boot(s,roi,nb); print(f"  {name:34s} n={len(s):5d} m={len({r['match_id'] for r in s}):4d} win={np.mean([r['y'] for r in s]):.3f} avgO={np.mean([r['o'] for r in s]):.2f} ROI={roi(s):+.3f} [{lo:+.3f},{hi:+.3f}]")
fams=sorted({r['fam'] for r in rows})
print("\n== 1. ALL priced PIT rows per family: blind ROI, Brier model vs market, overround")
for f in fams:
    s=[r for r in rows if r['fam']==f and r['mk'] and r['mr'] is not None]
    if len(s)<50: continue
    bm=np.mean([(r['mr']-r['y'])**2 for r in s]); bk=np.mean([(r['mk']-r['y'])**2 for r in s]); ov=np.mean([(1/r['o'])/r['mk'] for r in s])
    print(f"  {f:32s} n={len(s):5d} blindROI={roi(s):+.3f} Brier model={bm:.4f} mkt={bk:.4f} overround={ov:.3f} val={sum(r['v'] for r in s)}")
print("\n== 2. model-free: blind ROI by odds bucket (all priced rows, live families)")
LIVE=['player_game_handicap','first_set_winner','player_win_a_set','player_first_set_game_handicap','player_set_handicap','player_total_games']
bk=[(1,1.3),(1.3,1.6),(1.6,1.9),(1.9,2.3),(2.3,3),(3,5),(5,99)]
for f in LIVE:
    print(f)
    for a,b in bk: line(f"odds {a}-{b}", [r for r in rows if r['fam']==f and a<=r['o']<b], 500)
print("\n== 3. VALUE bets")
V=[r for r in rows if r['v']]
line("all value", V)
for f in fams: line(f, [r for r in V if r['fam']==f])
print(" by month");
for m in sorted({r['mon'] for r in V}): line(m,[r for r in V if r['mon']==m])
print(" by level");
for l in sorted({r['lv'] for r in V}): line(l,[r for r in V if r['lv']==l])
print(" by tour");
for l in sorted({r['tour'] for r in V}): line(l,[r for r in V if r['tour']==l])
print(" by edge")
for a,b in [(0,.06),(.06,.1),(.1,.15),(.15,.2),(.2,.3),(.3,1)]: line(f"edge {a}-{b}",[r for r in V if a<=(r['edge'] or 0)<b])
print(" by odds")
for a,b in bk: line(f"odds {a}-{b}",[r for r in V if a<=r['o']<b])
print(" live families only, since 10-28"); line("live fam >=10-28",[r for r in V if r['fam'] in LIVE and r['match_date']>='2026-10-28'])
print("\n== 4. CLV on value bets (close vs taken)")
C=[r for r in V if r['clv'] is not None]
print("  n with close",len(C),"mean clv",np.mean([r['clv'] for r in C]),"share moved",np.mean([abs(r['clv'])>1e-9 for r in C]))
line("clv>0",[r for r in C if r['clv']>1e-9]); line("clv=0",[r for r in C if abs(r['clv'])<=1e-9]); line("clv<0",[r for r in C if r['clv']<-1e-9])
A=[r for r in rows if r['clv'] is not None]
print("  all priced rows: n",len(A)); line("clv>0",[r for r in A if r['clv']>1e-9]); line("clv=0",[r for r in A if abs(r['clv'])<=1e-9]); line("clv<0",[r for r in A if r['clv']<-1e-9])
print("\n== 5. Does model add info beyond market? logit regression y ~ a + b*logit(mkt) + g*(logit(model)-logit(mkt))")
def lg(p): p=min(max(p,1e-4),1-1e-4); return math.log(p/(1-p))
def fit(s):
    X=np.array([[1,lg(r['mk']),lg(r['mr'])-lg(r['mk'])] for r in s]); y=np.array([r['y'] for r in s]); w=np.zeros(3)
    for _ in range(30):
        p=1/(1+np.exp(-X@w)); H=X.T@(X*(p*(1-p))[:,None])+1e-6*np.eye(3); w=w+np.linalg.solve(H,X.T@(y-p))
    return w
for f in LIVE+['ALL_LIVE']:
    s=[r for r in rows if (r['fam']==f or (f=='ALL_LIVE' and r['fam'] in LIVE)) and r['mk'] and r['mr'] is not None]
    if len(s)<200: continue
    w=fit(s); lo,hi=boot(s,lambda t: fit(t)[2],300)
    print(f"  {f:32s} n={len(s):5d} b_mkt={w[1]:.3f} g_model={w[2]:+.3f} [{lo:+.3f},{hi:+.3f}]")
