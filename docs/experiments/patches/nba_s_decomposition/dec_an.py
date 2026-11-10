import pickle,os,math,random,collections,statistics as st
X=pickle.load(open(os.path.dirname(os.path.abspath(__file__))+'/dec.pkl','rb'))
def ll(p,y): p=min(max(p,1e-4),1-1e-4); return -(math.log(p) if y else math.log(1-p))
def boot(pairs,days,n=1000):
    dd=collections.defaultdict(list)
    for v,d in zip(pairs,days): dd[d].append(v)
    ks=sorted(dd); rnd=random.Random(3); out=[]
    for _ in range(n):
        x=[v for k in (rnd.choice(ks) for _ in ks) for v in dd[k]]; out.append(sum(x)/len(x))
    out.sort(); return out[25],out[974]
print('legs',len(X),'days',len({x['d'] for x in X}))
print('\n== 逐腿 log-loss（越低越好）；Δ = 對市場(1/價)')
print(f"{'':14s}{'n':>6s} {'市場':>7s} {'發佈MS':>7s} {'S':>7s} {'S+真實時間':>10s} | S−市場 [95%CI]            | S真實時間−市場")
for stat in ('ALL','PTS','REB','AST','FG3M'):
    R=[x for x in X if stat=='ALL' or x['stat']==stat]; days=[x['d'] for x in R]
    m=[ll(1/x['price'],x['y']) for x in R]; s=[ll(x['pS'],x['y']) for x in R]; o=[ll(x['pO'],x['y']) for x in R]; f=[ll(x['p_final'],x['y']) for x in R if x['p_final'] is not None]
    lo,hi=boot([a-b for a,b in zip(s,m)],days); lo2,hi2=boot([a-b for a,b in zip(o,m)],days)
    print(f"{stat:14s}{len(R):6d} {st.mean(m):7.4f} {st.mean(f):7.4f} {st.mean(s):7.4f} {st.mean(o):10.4f} | {st.mean(s)-st.mean(m):+.4f} [{lo:+.4f},{hi:+.4f}] | {st.mean(o)-st.mean(m):+.4f} [{lo2:+.4f},{hi2:+.4f}]")
# player-game level mean errors
pg={}
for x in X: pg.setdefault((x['d'],x['g'],x['pl'],x['stat']),x)
P=list(pg.values()); print('\n== 球員-場次層面',len(P))
for stat in ('PTS','REB','AST','FG3M'):
    R=[x for x in P if x['stat']==stat]
    e=[x['actual']-x['mu'] for x in R]; eo=[x['actual']-x['mu']*x['mins']/x['mhat'] for x in R]; em=[x['mu']*(x['mins']/x['mhat']-1) for x in R]
    var=st.pvariance(e); print(f"{stat:5s} n={len(R):4d} 平均實際 {st.mean(x['actual'] for x in R):5.2f} 預測 {st.mean(x['mu'] for x in R):5.2f} | MAE {st.mean(map(abs,e)):.2f} → 知道真實時間後 {st.mean(map(abs,eo)):.2f} | 誤差方差：時間部分 {st.pvariance(em)/var*100:4.0f}% 、其餘（效率＋運氣）{st.pvariance(eo)/var*100:4.0f}%")
print('\n== 上場時間預測本身（球員-場次，去重）')
pm={}
for x in X: pm.setdefault((x['d'],x['g'],x['pl']),x)
M=list(pm.values())
def mae(f):
    v=[abs(x['mins']-f(x)) for x in M if f(x) is not None]; return st.mean(v),len(v)
for nm,f in (('S（半衰期 3 場加權）',lambda x:x['mhat']),('上一場',lambda x:x['hist'][0] if x['hist'] else None),('近 3 場平均',lambda x:st.mean(x['hist'][:3]) if len(x['hist'])>=3 else None),('近 10 場平均',lambda x:st.mean(x['hist']) if len(x['hist'])>=5 else None),('近 5 場中位數',lambda x:st.median(x['hist'][:5]) if len(x['hist'])>=5 else None)):
    a,n=mae(f); print(f'  {nm:18s} MAE {a:.2f} 分鐘 (n={n})')
r=[x['mins']/x['mhat'] for x in M]; print('  實際/預測 比例：中位 %.2f；<0.75 佔 %.0f%%；>1.25 佔 %.0f%%；平均偏差 %+.2f 分鐘'%(st.median(r),100*st.mean(v<.75 for v in r),100*st.mean(v>1.25 for v in r),st.mean(x['mins']-x['mhat'] for x in M)))
print('\n== 按時間偏差分組：S 同市場邊個輸得多（log-loss 差 S−市場）')
for lo,hi,nm in ((0,.75,'實際時間 <75% 預測'),(.75,.9,'75–90%'),(.9,1.1,'90–110%'),(1.1,1.25,'110–125%'),(1.25,9,'>125%')):
    R=[x for x in X if lo<=x['mins']/x['mhat']<hi]
    if R: print(f"  {nm:16s} n={len(R):5d} 市場 {st.mean(ll(1/x['price'],x['y']) for x in R):.4f}  S {st.mean(ll(x['pS'],x['y']) for x in R):.4f}  命中 {100*st.mean(x['y'] for x in R):.0f}%  1/價 {100*st.mean(1/x['price'] for x in R):.0f}%  S {100*st.mean(x['pS'] for x in R):.0f}%")
