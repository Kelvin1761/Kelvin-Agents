import pickle,os,math,random,collections,sys,json
D=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','..','..','.agents','skills','nba'))
src=open(D+'/rate_fit.py').read(); ns={}
ns["__file__"]=D+"/rate_fit.py"; exec(src[:src.index("ARMS={")],ns)
R,P,score,ci,part=ns['R'],ns['P'],ns['score'],ns['ci'],ns['part']
def mu3(r,K,pm):
    t=r['tot']; e3=(t['FG3M']+pm*K)/(t['FG3A']+K); return r['y']['MIN']*r['rate']['FG3A']*e3*r['c']['opp_FG3A']
def dv(y,m): m=max(m,1e-6); return 2*((y*math.log(y/m) if y>0 else 0.0)-(y-m))
print('== 三分命中率收縮強度（Δ 對現行）')
best=None
for K in (50,100,200,400,800,1600):
    line=f'  K={K:5d}'
    for k in ('dev','hold','new'):
        rows=P[k]; b=score(rows,'FG3M',{},{}); c=[dv(r['y']['FG3M'],mu3(r,K,.36)) for r in rows]; d=[x-y for x,y in zip(c,b)]
        if k=='dev' and (best is None or sum(d)<best[0]): best=(sum(d),K)
        lo,hi=ci(rows,d); line+=f' | {k} {sum(d)/len(d):+.4f} [{lo:+.4f},{hi:+.4f}]'
    print(line)
K=best[1]; print('dev 揀 K =',K)
# calibration check: predicted vs actual 3PM by predicted bucket (holdout)
rows=P['hold']
for lo,hi in ((0,1),(1,2),(2,3),(3,9)):
    g=[r for r in rows if lo<=mu3(r,K,.36)<hi]
    if g: print(f'  holdout 預測 {lo}–{hi}: n={len(g)} 預測 {sum(mu3(r,K,.36) for r in g)/len(g):.2f}  現行 {sum(ns["mu"](r,"FG3M",{},{}) for r in g)/len(g):.2f}  實際 {sum(r["y"]["FG3M"] for r in g)/len(g):.2f}')
# leg-level: ratio new/base applied to engine S mean (this season)
import importlib
from nba_engine import model
sr=model.config()['season_rate']
X=pickle.load(open(D+'/../nba_minutes_v2/dec2.pkl','rb'))
from datetime import date,timedelta
idx={(r['day'],r['pid']):r for r in R if r['season']=='2026-27'}
def kfor(mu):
    sc,pw=sr['dispersion']['FG3M']; return sr['dispersion_k']['FG3M']*sc*(max(mu,.3)/sr['dispersion_ref']['FG3M'])**pw
def ll(p,y): p=min(max(p,1e-4),1-1e-4); return -(math.log(p) if y else math.log(1-p))
rows=[]
for x in X:
    if x['stat']!='FG3M': continue
    r=idx.get(((date.fromisoformat(x['d'])-timedelta(days=1)).isoformat(),x['pid']))
    if not r: continue
    base=ns['mu'](r,'FG3M',{},{}); new=mu3(r,K,.36)
    if base<=0: continue
    m2=x['mu']*new/base; p2=model.nb_tail(x['line'],m2,kfor(m2))
    rows.append((x['d'],ll(x['pS'],x['y']),ll(p2,x['y']),ll(1/x['price'],x['y'])))
dd=collections.defaultdict(list)
for d,a,b,m in rows: dd[d].append(b-a)
ks=sorted(dd); rnd=random.Random(4); o=[]
for _ in range(1000):
    z=[v for k in (rnd.choice(ks) for _ in ks) for v in dd[k]]; o.append(sum(z)/len(z))
o.sort(); n=len(rows)
print(f'\n今季三分腿 n={n} 日={len(ks)}: 市場 {sum(r[3] for r in rows)/n:.4f}  S現行 {sum(r[1] for r in rows)/n:.4f}  S新三分 {sum(r[2] for r in rows)/n:.4f}  Δ {sum(r[2]-r[1] for r in rows)/n:+.4f} [{o[25]:+.4f},{o[974]:+.4f}]')
json.dump({'K':K,'prior':0.36},open(D+'/rate_3pm.json','w'))
