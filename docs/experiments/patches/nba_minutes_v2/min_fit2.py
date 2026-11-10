import pickle,os,random,collections,json
import numpy as np
R=pickle.load(open(os.path.dirname(os.path.abspath(__file__))+'/min_corpus2.pkl','rb'))
R=[r for r in R if r['m_hl']>=15 and r['spread'] is not None]
DEV_END='2026-02-08'
dev=[r for r in R if r['season']=='2025-26' and r['day']<=DEV_END]; hold=[r for r in R if r['season']=='2025-26' and r['day']>DEV_END]; new=[r for r in R if r['season']=='2026-27']
print('dev',len(dev),'holdout',len(hold),'今季',len(new))
def feats(r,g):
    hi=1.0 if r['m_hl']>=28 else 0.0; lo=1.0 if r['m_hl']<22 else 0.0; sp=min(r['spread'],16.0)
    f=[1.0,r['m_hl']]
    if 'shrink' in g: f+=[r['m_season']-r['m_hl'],r['m_last']-r['m_hl'],r['m_l10']-r['m_hl'],max(r['m_hl']-32,0.0)]
    if 'rest' in g: f+=[1.0 if r['rest']==1 else 0.0,(1.0 if r['rest']==1 else 0.0)*hi,1.0 if r['gap_last']>7 else 0.0,1.0 if r['missed_prev'] else 0.0]
    if 'spread' in g: f+=[sp*hi,sp*lo,sp,max(sp-8,0.0)*hi,(1.0 if r['is_fav'] else 0.0)*sp*hi]
    if 'total' in g: f+=[(float(r['total'] or 225)-225)/10.0]
    if 'role' in g: f+=[1.0 if r['started_prev'] else 0.0,r['start_share'],(1.0 if r['started_prev'] else 0.0)-r['start_share']]
    if 'pool_prev' in g: f+=[r['pool_prev'],r['pool_prev']*lo]
    if 'pool_today' in g: f+=[r['pool_today'],r['pool_today']*lo,r['pool_today']-r['pool_prev']]      # UPPER BOUND: same-day absences
    if 'starts_today' in g: f+=[1.0 if r['starts_today'] else 0.0,(1.0 if r['starts_today'] else 0.0)-r['start_share']]   # UPPER BOUND: lineup known ~30 min pre-tip
    return f
def fit(rows,g):
    X=np.array([feats(r,g) for r in rows]); y=np.array([r['y'] for r in rows]); return np.linalg.lstsq(X,y,rcond=None)[0]
def pred(rows,g,b): return np.array([feats(r,g) for r in rows])@b
def dmae(rows,p,ref=None):
    y=np.array([r['y'] for r in rows]); base=np.array([r['m_hl'] for r in rows]) if ref is None else ref
    d=np.abs(y-p)-np.abs(y-base); days=collections.defaultdict(list)
    for v,r in zip(d,rows): days[r['day']].append(v)
    ks=sorted(days); rnd=random.Random(5); bs=[]
    for _ in range(1000):
        x=[v for k in (rnd.choice(ks) for _ in ks) for v in days[k]]; bs.append(sum(x)/len(x))
    bs.sort(); return float(np.abs(y-base).mean()),float(np.abs(y-p).mean()),float(d.mean()),bs[25],bs[974]
BASE=('shrink','rest')
ARMS=[BASE+('spread','role','pool_prev'),('shrink',),BASE,BASE+('spread',),BASE+('total',),BASE+('role',),BASE+('pool_prev',),BASE+('spread','total','role','pool_prev'),
      BASE+('spread','total','role','pool_prev','pool_today'),BASE+('spread','total','role','pool_prev','pool_today','starts_today')]
ddays=sorted({r['day'] for r in dev}); cuts=[ddays[int(len(ddays)*q)] for q in (.4,.55,.7,.85)]+['9999']
print('\n== dev 時間 fold ΔMAE 對 baseline（負 = 好）')
for arm in ARMS:
    res=[]
    for i in range(4):
        tr=[r for r in dev if r['day']<cuts[i]]; va=[r for r in dev if cuts[i]<=r['day']<cuts[i+1]]
        res.append(dmae(va,pred(va,arm,fit(tr,arm)))[2])
    print(f"  {'+'.join(arm):62s} {' '.join(f'{v:+.3f}' for v in res)}  全負 {all(v<0 for v in res)}")
print('\n== dev 擬合 → holdout（上季尾段）／今季')
coef={}
for arm in ARMS:
    b=fit(dev,arm); coef['+'.join(arm)]=b.tolist(); line=f"  {'+'.join(arm):62s}"
    for nm,rows in (('holdout',hold),('今季',new)):
        base,m,d,lo,hi=dmae(rows,pred(rows,arm,b)); line+=f" | {nm} {base:.3f}→{m:.3f} Δ{d:+.3f} [{lo:+.3f},{hi:+.3f}]"
    print(line)
json.dump(coef,open(os.path.dirname(os.path.abspath(__file__))+'/min_coef2.json','w'),indent=1)
full=BASE+('spread','total','role','pool_prev'); b=fit(dev,full); p=pred(hold,full,b)
print('\n== 尾部（holdout，as-of 全模型）：預測比 baseline 低/高 最多嘅 10%')
y=np.array([r['y'] for r in hold]); base=np.array([r['m_hl'] for r in hold]); diff=p-base
for nm,mask in (('模型話會打少（最低 10%）',diff<=np.quantile(diff,.1)),('中間 80%',(diff>np.quantile(diff,.1))&(diff<np.quantile(diff,.9))),('模型話會打多（最高 10%）',diff>=np.quantile(diff,.9))):
    print(f"  {nm:22s} n={int(mask.sum()):5d} 模型調整 {diff[mask].mean():+.2f} 實際−baseline {(y-base)[mask].mean():+.2f} 分鐘；打少過 75% 佔 {100*((y/base)[mask]<.75).mean():.0f}%；打多過 125% 佔 {100*((y/base)[mask]>1.25).mean():.0f}%")
names={'spread':['讓分×主力','讓分×輪換','讓分','max(讓分−8,0)×主力','熱門×讓分×主力'],'role':['上場正選','近5場正選比例','角色變化'],'pool_prev':['上場缺陣時間池','×輪換'],'rest':['b2b','b2b×主力','休>7日','缺席上一場'],'total':['(總分−225)/10']}
k=2+4
for g in ('rest','spread','total','role','pool_prev'):
    print(' ',g,{n:round(float(v),3) for n,v in zip(names[g],b[k:k+len(names[g])])}); k+=len(names[g])
