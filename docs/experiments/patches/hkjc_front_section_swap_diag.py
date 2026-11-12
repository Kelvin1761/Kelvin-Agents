# EXP-20261113-05/06 分析腳本（喺 repo root 行；參數見 EXP 記錄：labels_final.jsonl 所在 scratch 目錄／前置腳本路徑）
import json,sys,numpy as np
sys.path.insert(0,".agents/skills/shared_racing")
from eval_metrics import race_metrics
N=sys.argv[1]
a=[json.loads(l) for l in open(f"{N}/lab/labels_final.jsonl")]; b=[json.loads(l) for l in open(f"{N}/lab/lab_front_b5.jsonl")]
R=[]
for x,y in zip(a,b):
    if "error" in x or "error" in y or not x.get("horses"): continue
    pos={h["n"]:h["pos"] for h in x["horses"] if h["pos"]}
    if sum(p<=3 for p in pos.values())<3: continue
    hs=[]
    for h,g in zip(x["horses"],y["horses"]):
        d=g["f"]["speed_score"]-h["f"]["speed_score"]
        hs.append({"n":h["n"],"raw":h["raw"],"speed":h["f"]["speed_score"],"z":d/(0.5*9.4487) if abs(d)>1e-9 else None,"pos":h["pos"]})
    R.append({"x":x,"hs":hs,"pos":pos})
def score(r,b=0.5,fn=None):
    s=[]
    for h in r["hs"]:
        v=h["raw"]
        if h["z"] is not None:
            pts=b*9.4487*h["z"] if fn is None else fn(r,h)
            v+=0.1285*(min(100,max(0,h["speed"]+pts))-h["speed"])
        s.append((-v,h["n"]))
    return [n for _,n in sorted(s)]
def met(r,order):
    m=race_metrics(order,[k for k,p in r["pos"].items() if p<=3],actual_pos=r["pos"])
    return np.array([m["gold"],m["good_positional"],m["top3_capture_at5"],(m.get("top2_hits") or 0)>=1],float)
base=np.array([met(r,score(r,0)) for r in R]); arm=np.array([met(r,score(r,0.5)) for r in R])
print("離線重算 b=0.5（全 449 中有效場）：Δ Gold/Good/cap5/頭二 =",np.round((arm-base).mean(0)*100,2))
dist=np.array([r["x"]["distance"] or 0 for r in R]); ven=np.array([r["x"]["venue"] for r in R]); fld=np.array([r["x"]["field"] or 0 for r in R])
nfront=np.array([sum(1 for h in r["hs"] if h["z"] is not None and h["z"]>1) for r in R])
def show(lab,mask):
    d=(arm-base)[mask]*100
    print(f"  {lab:<16} n={mask.sum():>3}｜Gold {d[:,0].mean():+.2f}（失{(d[:,0]<0).sum()} 得{(d[:,0]>0).sum()}）｜Good {d[:,1].mean():+.2f}｜cap5 {d[:,2].mean():+.2f}｜頭二 {d[:,3].mean():+.2f}")
print("按路程"); [show(l,m) for l,m in (("≤1200",dist<=1200),("1400–1650",(dist>=1400)&(dist<=1650)),("≥1800",dist>=1800))]
print("按場地"); [show(l,ven==v) for l,v in (("沙田","沙田"),("跑馬地","跑馬地"))]
print("按出賽數"); [show(l,m) for l,m in (("≤10",fld<=10),("11–12",fld>=11),)]
print("按場內前段強馬數（z>1）"); [show(l,m) for l,m in (("0",nfront==0),("1",nfront==1),("2",nfront==2),("≥3",nfront>=3))]
# 換位分析：入／出頭四
inn=[];out=[]
for r in R:
    o0=score(r,0)[:4]; o1=score(r,0.5)[:4]
    H={h["n"]:h for h in r["hs"]}
    for n in set(o1)-set(o0): inn.append((H[n]["z"] or 0,H[n]["pos"] is not None and H[n]["pos"]<=3,o0.index(n) if n in o0 else score(r,0).index(n)+1))
    for n in set(o0)-set(o1): out.append((H[n]["z"] or 0,H[n]["pos"] is not None and H[n]["pos"]<=3))
inn=np.array(inn,float); out=np.array(out,float)
print(f"\n換入頭四 {len(inn)} 匹：入位率 {inn[:,1].mean()*100:.1f}%，前段 z 均值 {inn[:,0].mean():+.2f}，原本名次中位 {np.median(inn[:,2]):.0f}")
print(f"換出頭四 {len(out)} 匹：入位率 {out[:,1].mean()*100:.1f}%，前段 z 均值 {out[:,0].mean():+.2f}")
# 換出嘅馬：佢自己 front z 為負（被扣分）定係被人超越？
print(f"  換出馬 z<0（自己被扣）{(out[:,0]<0).mean()*100:.0f}%，入位率 {out[out[:,0]<0,1].mean()*100:.1f}% vs 被超越（z≥0）{out[out[:,0]>=0,1].mean()*100:.1f}%")
print(f"  換入馬 z>0（自己加分）{(inn[:,0]>0).mean()*100:.0f}%，入位率 {inn[inn[:,0]>0,1].mean()*100:.1f}% vs 因人哋扣分而上（z≤0）{inn[inn[:,0]<=0,1].mean()*100:.1f}%")
