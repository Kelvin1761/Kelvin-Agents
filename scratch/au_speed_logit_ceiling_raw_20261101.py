import json,sys,math,random
import numpy as np
sys.path.insert(0,'/Users/imac/Antigravity-repo/.agents/skills/au_racing/au_wong_choi_auto/scripts')
from au_racing_engine.scoring import MATRIX_WEIGHTS
from au_walkforward_refit import exact_score
X="/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/EXP-20261101-33/arms"
def load(arm):
    return {(r["meeting"],r["race"]):r for r in json.load(open(f"{X}/{arm}.json"))["races"]
            if r["date"]>="2026-08-05" and sum(x["pos"]<=3 for x in r["rows"])>=3 and any(x["pos"]==1 for x in r["rows"])}
B,G=load("base"),load("G")
keys=sorted(B,key=lambda k:(B[k]["date"],k))
def z_old(v):
    v=np.array(v,float); s=v.std(); return (v-v.mean())/s if s>0 else v*0
def z(v):
    v=np.array(v,float); return v-v.mean()
def feats(r):
    rows=r["rows"]
    rest=[exact_score({**x,"features":{**x["features"],"pace_figure_score":60.0}},MATRIX_WEIGHTS) for x in rows]
    pf=[x["features"]["pace_figure_score"] for x in rows]
    return z(rest), z(pf), np.array([x["pos"]<=3 for x in rows],float), np.array([x["ability"] for x in rows])
data={}
for name,src in (("base",B),("G",G)):
    data[name]=[(B[k]["date"],)+feats(src[k]) for k in keys]
# current implied ratio: d ability / d pf (per raw point) vs d ability / d rest; estimate empirically
def fit(rows):
    Xm=np.vstack([np.column_stack([a,b]) for _,a,b,_,_ in rows]); y=np.concatenate([c for *_,c,_ in rows])
    w=np.zeros(3); Xb=np.column_stack([np.ones(len(y)),Xm])
    for _ in range(25):
        p=1/(1+np.exp(-Xb@w)); W=p*(1-p)+1e-9
        w=w+np.linalg.solve(Xb.T@(W[:,None]*Xb)+1e-6*np.eye(3), Xb.T@(y-p))
    return w
dates=sorted({d for d,*_ in data["base"]}); n=len(dates); blocks=[dates[i*n//6:(i+1)*n//6] for i in range(6)]
res={}
for name in ("base","G"):
    rows=data[name]; per_day={}; coefs=[]
    for bi in range(1,6):
        train=[r for r in rows if r[0]<blocks[bi][0]]; test=[r for r in rows if r[0] in set(blocks[bi])]
        w=fit(train); coefs.append(w.round(3).tolist())
        for d,a,b,y,_ in test:
            s=w[0]+w[1]*a+w[2]*b; p=1/(1+np.exp(-s)); ll=float(np.sum(y*np.log(p)+(1-y)*np.log(1-p)))
            hit=tot=0
            for i in range(len(y)):
                for j in range(len(y)):
                    if y[i]==1 and y[j]==0: tot+=1; hit+=1 if s[i]>s[j] else .5 if s[i]==s[j] else 0
            v=per_day.setdefault(d,[0.,0.,0.,0]); v[0]+=ll; v[1]+=hit; v[2]+=tot; v[3]+=len(y)
    res[name]=(per_day,coefs)
pb,cb=res["base"]; pg,cg=res["G"]; days=sorted(pb)
def stat(ds,i):
    if i=="ll": return (sum(pg[d][0] for d in ds)-sum(pb[d][0] for d in ds))/sum(pb[d][3] for d in ds)
    return sum(pg[d][1] for d in ds)/sum(pg[d][2] for d in ds)-sum(pb[d][1] for d in ds)/sum(pb[d][2] for d in ds)
rng=random.Random(7)
for m in ("ll","auc"):
    boots=sorted(stat([days[rng.randrange(len(days))] for _ in days],m) for _ in range(2000))
    print(m,"G - base: %+.5f CI [%+.5f, %+.5f]"%(stat(days,m),boots[50],boots[1949]))
print("OOS days",len(days))
print("coef base (rest, speed) per block:",[c[1:] for c in cb])
print("coef G    (rest, speed) per block:",[c[1:] for c in cg])
# implied current production weight ratio: regress ability on rest_z & pf_z within races
Xm=np.vstack([np.column_stack([a,b]) for _,a,b,_,_ in data["base"]]); yab=np.concatenate([z(ab) for *_,ab in data["base"]])
print("production implied (rest, speed) ratio:", np.linalg.lstsq(Xm,yab,rcond=None)[0].round(3))

# production ordering vs walk-forward logit ordering (base features), within-race AUC, paired by day
per=dict()
rows=data["base"]
for bi in range(1,6):
    train=[r for r in rows if r[0]<blocks[bi][0]]; test=[r for r in rows if r[0] in set(blocks[bi])]
    w=fit(train)
    for d,a,b,y,ab in test:
        s=w[1]*a+w[2]*b
        for name,sc in (("prod",ab),("logit",s)):
            hit=tot=0
            for i in range(len(y)):
                for j in range(len(y)):
                    if y[i]==1 and y[j]==0: tot+=1; hit+=1 if sc[i]>sc[j] else .5 if sc[i]==sc[j] else 0
            v=per.setdefault((name,d),[0,0]); v[0]+=hit; v[1]+=tot
def st2(ds): return sum(per[("logit",d)][0] for d in ds)/sum(per[("logit",d)][1] for d in ds)-sum(per[("prod",d)][0] for d in ds)/sum(per[("prod",d)][1] for d in ds)
boots=sorted(st2([days[rng.randrange(len(days))] for _ in days]) for _ in range(2000))
print("within-race AUC walk-forward reweighted(rest+speed) - production: %+.5f CI [%+.5f, %+.5f]"%(st2(days),boots[50],boots[1949]))
