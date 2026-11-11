import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd
from hkjc_trainer_class_screen import prep, load, fit, edges, OOS_START
from hkjc_class_move_people_screen import add_move, boot975
m=add_move(prep(load(sys.argv[1])))
m=m.sort_values(["HorseID","Date","RaceNo"])
g=m.groupby("HorseID")
fs=g.Rank.transform(lambda s: s.astype(float))
m["fs"]=fs
m["prev_rank"]=g.fs.shift(1); m["prev_place"]=g.Place.shift(1)
m["prev_win"]=(m.prev_rank==1).astype(float)
m["last3"]=g.Place.transform(lambda s: s.shift(1).rolling(3,min_periods=1).mean())
m=m.sort_values(["Date","RaceNo"])
d=m[(m.Date>=OOS_START)&(m.MV!="冇前仗")].copy()
d["prev_rank"]=d.prev_rank.fillna(14); d["last3"]=d.last3.fillna(0.25)
d["up"]=(d.MV=="升班").astype(float); d["down"]=(d.MV=="降班").astype(float)
print("升班 之中上仗贏咗嘅比例 %.1f%%，同班 %.1f%%"%(d[d.up==1].prev_win.mean()*100, d[(d.up==0)&(d.down==0)].prev_win.mean()*100))
d=d.reset_index(drop=True)
for b,a,l in [([],["up","down"],"升降班 單獨"),
              (["prev_rank","prev_win","last3"],["up","down"],"升降班 加喺上仗名次＋近3仗之上")]:
    b2=b or ["last3"];
    if not b:
        from sklearn.metrics import roc_auc_score
        print(l, "AUC", round(roc_auc_score(d.Place, d.up-d.down),4)); continue
    mean,lo,hi=boot975(d,fit(d,b2),fit(d,b2+a)); print(f"{l} Δ {mean:+.4f} [{lo:+.4f},{hi:+.4f}]")
print(pd.crosstab(d.MV, d.prev_rank.clip(upper=5), normalize="index").round(3))
