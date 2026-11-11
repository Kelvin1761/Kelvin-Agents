import pickle,os,math,random,collections,json
D=os.path.dirname(os.path.abspath(__file__))
R=pickle.load(open(D+'/rate_corpus.pkl','rb'))
DEV_END='2026-02-08'
part=lambda r:'dev' if r['season']=='2025-26' and r['day']<=DEV_END else 'hold' if r['season']=='2025-26' else 'new'
SH=10.0
def shrink(n,v,lv): return ((n*v+SH*lv)/(n+SH))/lv if lv>0 else 1.0
def ctx(r):
    L=r['league']; nt,own,alw=r['own']; no,oown,oalw=r['oppt']
    c={}
    for k in ('PTS','REB','AST','FG3M','FG3A','FTA'): c['opp_'+k]=shrink(no,oalw[k],L[k])
    pace=(own['POSS']*nt+oown['POSS']*no)/(nt+no); c['pace']=shrink(nt+no,pace,L['POSS'])
    miss=lambda d:d['FGA']-d['FGM']; Lm=miss(L)
    c['own_miss']=shrink(nt+no,(miss(own)*nt+miss(oalw)*no)/(nt+no),Lm)    # our misses = our tendency & what opp allows
    c['opp_miss']=shrink(nt+no,(miss(oown)*no+miss(alw)*nt)/(nt+no),Lm)
    c['own_fgm']=shrink(nt+no,(own['FGM']*nt+oalw['FGM']*no)/(nt+no),L['FGM'])
    c['total']=(r['total']/(2*L['PTS'])) if r['total'] else None
    return c
for r in R: r['c']=ctx(r)
def pts_parts(r):
    a,t=r['rate'],r['tot']
    e2=(t['FGM']-t['FG3M']+.54*100)/(t['FGA']-t['FG3A']+100); e3=(t['FG3M']+.36*100)/(t['FG3A']+100); ef=(t['FTM']+.78*50)/(t['FTA']+50)
    return (a['FGA']-a['FG3A'])*e2*2, a['FG3A']*e3*3, a['FTA']*ef, e3
def mu(r,stat,v,p):
    m=r['y']['MIN']; a=r['rate']; c=r['c']
    pace=c['pace']**p.get('pace',0.0) if v.get('pace')=='team' else ((c['total'] or 1.0)**p.get('pace',0.0) if v.get('pace')=='total' else 1.0)
    if stat=='PTS':
        two,three,ft,_=pts_parts(r)
        if v.get('ft'): return m*((two+three)*c['opp_PTS']+ft*c['opp_FTA']**p['ft'])*pace
        return m*(two+three+ft)*c['opp_PTS']*pace
    if stat=='FG3M':
        if v.get('dec'):
            _,_,_,e3=pts_parts(r); return m*a['FG3A']*e3*c['opp_'+v['dec']]*pace
        return m*a['FG3M']*c['opp_FG3M']*pace
    if stat=='REB':
        if v.get('split'): return m*(a['OREB']*c['own_miss']**p['o']+a['DREB']*c['opp_miss']**p['d'])*c['opp_REB']**p.get('r',0.0)*pace
        return m*a['REB']*c['opp_REB']*pace
    if stat=='AST':
        return m*a['AST']*c['opp_AST']*(c['own_fgm']**p['f'] if v.get('fgm') else 1.0)*pace
def dev(y,m):
    m=max(m,1e-6); return 2*((y*math.log(y/m) if y>0 else 0.0)-(y-m))
def score(rows,stat,v,p): return [dev(r['y'][stat],mu(r,stat,v,p)) for r in rows]
def ci(rows,d):
    dd=collections.defaultdict(list)
    for x,r in zip(d,rows): dd[r['day']].append(x)
    ks=sorted(dd); rnd=random.Random(11); o=[]
    for _ in range(800):
        z=[x for k in (rnd.choice(ks) for _ in ks) for x in dd[k]]; o.append(sum(z)/len(z))
    o.sort(); return o[20],o[779]
P={k:[r for r in R if part(r)==k] for k in ('dev','hold','new')}
TP=[r for r in R if r['c']['total']]; PT={k:[r for r in TP if part(r)==k] for k in ('dev','hold','new')}
def grid(stat,v,keys,vals,rows):
    best=None
    import itertools
    for combo in itertools.product(vals,repeat=len(keys)):
        p=dict(zip(keys,combo)); s=sum(score(rows,stat,v,p))/len(rows)
        if best is None or s<best[0]: best=(s,p)
    return best[1]
ARMS={
 'FG3M':[('拆出手×收縮命中率（對手失三分入球）',{'dec':'FG3M'},{}),('拆出手×收縮命中率（對手失三分出手）',{'dec':'FG3A'},{}),('節奏（球隊回合）',{'pace':'team'},('pace',)),('拆出手（對手失出手）＋節奏',{'dec':'FG3A','pace':'team'},('pace',))],
 'REB':[('拆前場／後場×射失數',{'split':1},('o','d')),('拆前後場＋保留對手失籃板',{'split':1},('o','d','r')),('節奏（球隊回合）',{'pace':'team'},('pace',))],
 'AST':[('×隊友入球數',{'fgm':1},('f',)),('節奏（球隊回合）',{'pace':'team'},('pace',))],
 'PTS':[('罰球部分改用對手送罰球',{'ft':1},('ft',)),('節奏（球隊回合）',{'pace':'team'},('pace',))],
}
GRID=[0.0,0.25,0.5,0.75,1.0,1.25,1.5]
fitted={}
for stat,arms in ARMS.items():
    print(f'\n== {stat}（Poisson deviance，Δ 對現行；負 = 好）')
    for nm,v,keys in arms:
        p=grid(stat,v,keys,GRID,P['dev']) if keys else {}
        line=f'  {nm:34s} 參數 {p}'
        for k in ('dev','hold','new'):
            rows=P[k]; b=score(rows,stat,{},{}); c=score(rows,stat,v,p); d=[x-y for x,y in zip(c,b)]; lo,hi=ci(rows,d)
            line+=f' | {k} {sum(d)/len(d):+.4f} [{lo:+.4f},{hi:+.4f}]'
        print(line); fitted[stat+'|'+nm]=(v,p)
    # market total pace on the subset that has totals
    v={'pace':'total'}; p=grid(stat,v,('pace',),GRID,PT['dev']); line=f'  {"節奏（大細盤總分）":34s} 參數 {p}'
    for k in ('dev','hold','new'):
        rows=PT[k]; b=score(rows,stat,{},{}); c=score(rows,stat,v,p); d=[x-y for x,y in zip(c,b)]; lo,hi=ci(rows,d)
        line+=f' | {k} {sum(d)/len(d):+.4f} [{lo:+.4f},{hi:+.4f}]'
    print(line); fitted[stat+'|total']=(v,p)
print('\nbase mean deviance', {s:round(sum(score(P['hold'],s,{},{}))/len(P['hold']),4) for s in ('PTS','REB','AST','FG3M')}, 'n', {k:len(v) for k,v in P.items()})
pickle.dump(fitted,open(D+'/rate_fitted.pkl','wb'))
