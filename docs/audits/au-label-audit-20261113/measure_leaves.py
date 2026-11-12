import json, sys, random, statistics as st
from collections import Counter
races=json.load(open(sys.argv[1]))
LEAVES="form_score trial_score sectional_score pace_map_score jockey_score trainer_score jockey_horse_fit_score class_score rating_score weight_score distance_score track_score formline_score consistency_score performance_quality_score health_score confidence_score pace_figure_score preparation_score form_quality_score trial_speed_score".split()
OVER="wet_form_feature proven_class_feature full_time_speed_feature draw_feature".split()
TOT=["final_rank_score","pure_7d_score"]
def f(x):
    try: return float(x)
    except: return None
def rank(v):
    o=sorted(range(len(v)),key=lambda i:v[i]); r=[0]*len(v); i=0
    while i<len(o):
        j=i
        while j+1<len(o) and v[o[j+1]]==v[o[i]]: j+=1
        for k in range(i,j+1): r[o[k]]=(i+j)/2
        i=j+1
    return r
def spear(a,b):
    if len(set(a))<2 or len(set(b))<2: return None
    ra,rb=rank(a),rank(b); ma,mb=st.mean(ra),st.mean(rb)
    num=sum((x-ma)*(y-mb) for x,y in zip(ra,rb)); den=(sum((x-ma)**2 for x in ra)*sum((y-mb)**2 for y in rb))**.5
    return num/den
def auc_race(vals,pos,neutral,excl):
    win=0; n=0
    P=[(v,p) for v,p in zip(vals,pos) if v is not None and not (excl and neutral is not None and abs(v-neutral)<1e-9)]
    pl=[v for v,p in P if p<=3]; un=[v for v,p in P if p>3]
    for a in pl:
        for b in un:
            n+=1; win+= 1 if a>b else (.5 if a==b else 0)
    return win,n
def boot(per,B=1000):
    random.seed(7); idx=list(range(len(per))); out=[]
    for _ in range(B):
        s=[per[random.choice(idx)] for _ in idx]; w=sum(x[0] for x in s); n=sum(x[1] for x in s)
        if n: out.append(w/n)
    out.sort(); return out[int(.025*len(out))],out[int(.975*len(out))]
rows=[]
for key in LEAVES+OVER+TOT:
    neutral=60.0 if key in LEAVES else 0.0
    allv=[]; const=0; nrace=0; distinct=[]; sds=[]; per_ex=[]; per_in=[]; rho=[]
    for r in races:
        v=[f(x.get(key)) for x in r["rows"]]; pos=[x["pos"] for x in r["rows"]]
        if all(x is None for x in v): continue
        nrace+=1; vv=[x for x in v if x is not None]; allv+=vv
        if len(set(round(x,4) for x in vv))==1: const+=1
        distinct.append(len(set(round(x,4) for x in vv))); sds.append(st.pstdev(vv))
        per_ex.append(auc_race(v,pos,neutral,True)); per_in.append(auc_race(v,pos,neutral,False))
        tot=[f(x["final_rank_score"]) for x in r["rows"]]
        if key not in TOT:
            s=spear([x if x is not None else neutral for x in v],tot)
            if s is not None: rho.append(s)
    if not allv: rows.append((key,0)); continue
    neu=sum(1 for x in allv if abs(x-neutral)<1e-9)/len(allv)
    def agg(per):
        w=sum(x[0] for x in per); n=sum(x[1] for x in per); return (w/n if n else None), n
    ae,ne=agg(per_ex); ai,ni=agg(per_in)
    cie=boot(per_ex) if ne else (None,None)
    rows.append(dict(key=key,races=nrace,neutral=round(neu,3),const_race=round(const/nrace,3),distinct_med=st.median(distinct),sd_med=round(st.median(sds),2),
        auc_ex=round(ae,4) if ae else None,ci=[round(c,4) if c else None for c in cie],pairs_ex=ne,auc_in=round(ai,4) if ai else None,rho_total=round(st.median(rho),3) if rho else None,
        top=Counter(round(x,2) for x in allv).most_common(3)))
for r in rows: print(json.dumps(r,ensure_ascii=False))
