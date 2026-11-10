import pickle,os,json,collections,statistics as st
X=pickle.load(open(os.path.dirname(os.path.abspath(__file__))+'/dec.pkl','rb'))
A=os.path.expanduser("~/WongChoiData/Wong Choi NBA Analysis")
pm={}
for x in X: pm.setdefault((x['d'],x['g'],x['pl']),x)
M=list(pm.values()); sp={}
for x in M:
    k=(x['d'],x['g'])
    if k not in sp:
        sp[k]=None
        try:
            j=json.load(open(f"{A}/{x['d']} NBA Analysis/Sportsbet_Odds_{x['g']}.json")); sp[k]=abs(float(str(j['game_lines']['spread_away']).replace('+','')))
        except Exception as e: pass
    x['spread']=sp[k]; x['ratio']=x['mins']/x['mhat']; x['dev']=x['mins']-x['mhat']
print('有讓分',sum(x['spread'] is not None for x in M),'/',len(M))
def row(nm,R):
    if len(R)<20: print(f'  {nm:26s} n={len(R)}'); return
    print(f"  {nm:26s} n={len(R):4d} 平均偏差 {st.mean(x['dev'] for x in R):+5.2f} 分鐘  <75% 佔 {100*st.mean(x['ratio']<.75 for x in R):3.0f}%  >125% 佔 {100*st.mean(x['ratio']>1.25 for x in R):3.0f}%  MAE {st.mean(abs(x['dev']) for x in R):.2f}")
print('== 按讓分（主力：預測 ≥28 分鐘）')
for lo,hi in ((0,4),(4,8),(8,12),(12,99)):
    row(f'讓分 {lo}–{hi}',[x for x in M if x['spread'] is not None and lo<=x['spread']<hi and x['mhat']>=28])
print('== 按讓分（輪換：預測 <22 分鐘）')
for lo,hi in ((0,4),(4,8),(8,12),(12,99)):
    row(f'讓分 {lo}–{hi}',[x for x in M if x['spread'] is not None and lo<=x['spread']<hi and x['mhat']<22])
print('== 按預測時間')
for lo,hi in ((0,18),(18,24),(24,30),(30,34),(34,60)):
    row(f'預測 {lo}–{hi} 分鐘',[x for x in M if lo<=x['mhat']<hi])
print('== 近況波動（近 5 場時間最大−最小）')
for lo,hi in ((0,6),(6,12),(12,99)):
    row(f'波幅 {lo}–{hi}',[x for x in M if len(x['hist'])>=5 and lo<=max(x['hist'][:5])-min(x['hist'][:5])<hi])
print('== 今季場數')
for lo,hi in ((0,4),(4,8),(8,99)):
    row(f'今季 {lo}–{hi} 場',[x for x in M if lo<=x['ncur']<hi])
