"""Does carrying more weight than your rivals predict a WORSE finish?"""
import sys, os
from pathlib import Path
R=Path('/Users/imac/Antigravity-repo')
sys.path.insert(0,str(R/'.agents/skills/hkjc_racing/hkjc_reflector/scripts'))
sys.path.insert(0,str(R/'.agents/scripts'))
sys.path.insert(0,str(R/'.agents/skills/shared_racing/scripts'))
import pandas as pd
from pit_backtest import load_all_rows
df=load_all_rows()
print('rows',len(df),'cols',[c for c in df.columns][:30])

df=df.copy()
df['ActualWt']=pd.to_numeric(df['ActualWt'],errors='coerce')
df['Rank']=pd.to_numeric(df['Rank'],errors='coerce')
d=df.dropna(subset=['ActualWt','Rank','Date','RaceNo','Venue'])
d=d[d['Rank']>0]
key=['Date','Venue','RaceNo']
g=d.groupby(key)
d=d.assign(n=g['Rank'].transform('size'),
           wt_rank=g['ActualWt'].rank(ascending=False,method='average'),
           wt_mean=g['ActualWt'].transform('mean'))
d=d[d['n']>=6]
d['wt_dev']=d['ActualWt']-d['wt_mean']
d['placed']=(d['Rank']<=3).astype(int)
d['won']=(d['Rank']==1).astype(int)
print('\nfield-size>=6 runners: %d  races: %d'%(len(d),d.groupby(key).ngroups))
print('\n--- 場內負磅偏離 vs 上名率（同場比較，唔跨場） ---')
bins=[-99,-8,-4,-1.5,1.5,4,8,99]
d['bucket']=pd.cut(d['wt_dev'],bins)
t=d.groupby('bucket',observed=True).agg(n=('placed','size'),place_rate=('placed','mean'),win_rate=('won','mean'),mean_rank=('Rank','mean'))
t['place_rate']=(100*t['place_rate']).round(1); t['win_rate']=(100*t['win_rate']).round(1); t['mean_rank']=t['mean_rank'].round(2)
print(t.to_string())
# within-race Spearman between weight and finish
import numpy as np
rho=[]
for _,grp in d.groupby(key):
    if len(grp)<6: continue
    a=grp['ActualWt'].rank(); b=grp['Rank'].rank()
    if a.std()==0: continue
    rho.append(np.corrcoef(a,b)[0,1])
rho=np.array(rho); rho=rho[~np.isnan(rho)]
se=rho.std(ddof=1)/np.sqrt(len(rho))
print('\n場內 Spearman ρ(負磅, 名次)  = %+.4f  [%+.4f, %+.4f]  n=%d 場'%(
    rho.mean(), rho.mean()-1.96*se, rho.mean()+1.96*se, len(rho)))
print('（ρ>0 = 負磅越重名次越差 → 現行「重磅扣分」啱；ρ<0 = 負磅越重跑得越好 → 扣分方向錯）')
