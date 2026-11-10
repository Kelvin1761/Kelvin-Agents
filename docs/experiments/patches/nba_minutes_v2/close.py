import pickle,os,statistics as st,random,collections
D=os.path.dirname(os.path.abspath(__file__))
X=pickle.load(open(D+'/cal.pkl','rb'))
E=[x for x in X if 1.2<=x['price']<=1.6 and (x['h10'] or 0)>=.8 and (x['h5'] or 0)>=.8 and x['l10'] and len(x['l10'])>=5]
print('B2 式合資格腿（價 1.2–1.6、L10/L5≥80%、有 L10 數值）',len(E),'日',len({x['d'] for x in E}))
def boot(rows):
    dd=collections.defaultdict(list)
    for x in rows: dd[x['d']].append(x['price']*x['y']-1)
    ks=sorted(dd); rnd=random.Random(2); o=[]
    for _ in range(1000):
        z=[v for k in (rnd.choice(ks) for _ in ks) for v in dd[k]]; o.append(sum(z)/len(z))
    o.sort(); return o[25],o[974]
def row(nm,R):
    if len(R)<30: print(f'  {nm:34s} n={len(R)}'); return
    lo,hi=boot(R); print(f"  {nm:34s} n={len(R):4d} 中 {100*st.mean(x['y'] for x in R):5.1f}%  1/價 {100*st.mean(1/x['price'] for x in R):5.1f}%  模型 {100*st.mean(x['p'] for x in R):5.1f}%  單腿ROI {100*st.mean(x['price']*x['y']-1 for x in R):+6.1f}% [{100*lo:+.0f},{100*hi:+.0f}]")
for x in E:
    l=x['l10']; a=st.mean(l); x['u']=a-x['line']; x['sd']=st.pstdev(l) or .5; x['z']=x['u']/x['sd']
    x['min_gap']=min(l)-x['line']; x['near']=sum(1 for v in l if v-x['line'] in (0,1))/len(l)   # 近 10 場有幾多場只係啱啱過線（=線 或 線+1）
    x['second']=sorted(l)[1]-x['line']
row('全部',E)
print('-- 平均高過線幾多個單位'); [row(f'  {lo}–{hi}',[x for x in E if lo<=x['u']<hi]) for lo,hi in ((0,1.5),(1.5,3),(3,6),(6,99))]
print('-- 平均高過線幾多個標準差'); [row(f'  z {lo}–{hi}',[x for x in E if lo<=x['z']<hi]) for lo,hi in ((0,.8),(.8,1.2),(1.2,1.8),(1.8,99))]
print('-- 近 10 場「啱啱過線」（=線 或 線+1）嘅比例'); [row(f'  {int(lo*100)}–{int(hi*100)}%',[x for x in E if lo<=x['near']<hi]) for lo,hi in ((0,.2),(.2,.4),(.4,.6),(.6,1.01))]
print('-- 近 10 場第二低嗰場 − 線'); [row(f'  {lo}–{hi}',[x for x in E if lo<=x['second']<hi]) for lo,hi in ((-99,0),(0,1),(1,2),(2,4),(4,99))]
print('-- 線嘅大細'); [row(f'  線 {lo}–{hi}',[x for x in E if lo<=x['line']<hi]) for lo,hi in ((1,3),(3,5),(5,8),(8,15),(15,99))]
print('-- L10 命中'); [row(f'  {nm}',[x for x in E if f(x)]) for nm,f in (('80%',lambda x:x['h10']<.85),('90%',lambda x:.85<=x['h10']<.95),('100%',lambda x:x['h10']>=.95))]
print('-- 候選篩：啱啱過線比例 <40%');
half=sorted({x['d'] for x in E}); mid=half[len(half)//2]
for nm,f in (('通過（唔貼線）',lambda x:x['near']<.4),('唔通過（貼線）',lambda x:x['near']>=.4)):
    row(nm+' 前半',[x for x in E if f(x) and x['d']<mid]); row(nm+' 後半',[x for x in E if f(x) and x['d']>=mid])
