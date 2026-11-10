import pickle,os,json,math,random,collections,sys,statistics as st,re
from datetime import date,timedelta
import numpy as np
D=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','..','..','.agents','skills','nba'))
from nba_engine import model
sr=model.config()['season_rate']
src=open(D+'/min_fit2.py').read(); ns={}
exec(src[src.index('def feats'):src.index('def fit')],ns); feats=ns['feats']
coef=json.load(open(D+'/min_coef2.json'))
C=pickle.load(open(D+'/min_corpus2.pkl','rb')); idx={(r['day'],r['pid']):r for r in C if r['season']=='2026-27' and r['spread'] is not None}
X=pickle.load(open(D+'/dec2.pkl','rb'))
def kfor(stat,mu):
    scale,power=sr['dispersion'][stat]; return sr['dispersion_k'][stat]*scale*(max(mu,.3)/sr['dispersion_ref'][stat])**power
def ll(p,y): p=min(max(p,1e-4),1-1e-4); return -(math.log(p) if y else math.log(1-p))
ARMS=['shrink+rest+spread+role+pool_prev','shrink+rest','shrink+rest+spread+total+role+pool_prev','shrink+rest+spread+total+role+pool_prev+pool_today','shrink+rest+spread+total+role+pool_prev+pool_today+starts_today']
rows=[]
for x in X:
    us=(date.fromisoformat(x['d'])-timedelta(days=1)).isoformat()
    r=idx.get((us,x['pid']))
    if r is None or r['m_hl']<15: continue
    e=dict(x); r=dict(r)
    try:
        j=json.load(open(os.path.expanduser(f"~/WongChoiData/Wong Choi NBA Analysis/{x['d']} NBA Analysis/Sportsbet_Odds_{x['g']}.json")))
        sa=float(str(j['game_lines']['spread_away']).replace('+','')); away=x['g'].split('_')[0]
        r['spread_espn']=r['spread']; r['spread']=abs(sa); r['is_fav']=(sa<0)==(r['team']==away) if sa!=0 else False
    except Exception: continue
    e['r']=r
    for a in ARMS:
        g=tuple(a.split('+')); m2=float(np.array(feats(r,g))@np.array(coef[a])); ratio=min(max(m2/r['m_hl'],0.5),1.6)
        mu=x['mu']*ratio; e[a]=model.nb_tail(x['line'],mu,kfor(x['stat'],mu))
    rows.append(e)
print('legs joined',len(rows),'/',len(X),'days',len({e['d'] for e in rows}))
def boot(v,days,n=1000):
    dd=collections.defaultdict(list)
    for a,d in zip(v,days): dd[d].append(a)
    ks=sorted(dd); rnd=random.Random(7); o=[]
    for _ in range(n):
        z=[a for k in (rnd.choice(ks) for _ in ks) for a in dd[k]]; o.append(sum(z)/len(z))
    o.sort(); return o[25],o[974]
for stat in ('ALL','PTS','REB','AST','FG3M'):
    R=[e for e in rows if stat=='ALL' or e['stat']==stat]; days=[e['d'] for e in R]
    s=[ll(e['pS'],e['y']) for e in R]; m=[ll(1/e['price'],e['y']) for e in R]
    print(f"\n{stat} n={len(R)}  市場 {st.mean(m):.4f}  S現行 {st.mean(s):.4f}")
    for a,nm in zip(ARMS,('候選（21:00 讓分，冇總分）','基本（收縮＋休息）','as-of 全模型','＋當日傷缺（上限）','＋當日正選（上限）')):
        v=[ll(e[a],e['y']) for e in R]; d=[p-q for p,q in zip(v,s)]; lo,hi=boot(d,days)
        print(f"   {nm:16s} {st.mean(v):.4f}  Δ對S {st.mean(d):+.4f} [{lo:+.4f},{hi:+.4f}]  Δ對市場 {st.mean(v)-st.mean(m):+.4f}")

d=[abs(e['r']['spread']-e['r']['spread_espn']) for e in rows]; print('\n21:00 Sportsbet 讓分 對 ESPN 收市讓分：平均相差 %.2f 分，>2 分佔 %.0f%%'%(st.mean(d),100*st.mean(v>2 for v in d)))
