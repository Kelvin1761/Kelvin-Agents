import json, sys, statistics as st
from collections import Counter, defaultdict
rows=[json.loads(l) for l in open(sys.argv[1])]
rows=[r for r in rows if "horses" in r]
W={"stability":(0.08847,{"form_score":0.5/0.9,"consistency_score":0.4/0.9}),"trainer_signal":(0.2362,{"jockey_score":.55,"trainer_score":.45}),
 "sectional":(0.1285,{"speed_score":1}),"race_shape":(0.2737,{"race_shape_context_score":1}),"horse_health":(0.0404,{"risk_score":.611,"weight_score":.389}),
 "trackwork":(0.00983,{"trackwork_trend_score":1}),"distance_fit":(0.02,{"distance_fit":1}),"form_line":(0.0801,{"formline_strength_score":1}),"class_advantage":(0.1428,{"class_score":.75,"weight_score":.25})}
def auc(pairs):  # within race: P(score placed > score unplaced)
    num=den=0
    for xs in pairs:
        P=[s for s,p in xs if p]; U=[s for s,p in xs if not p]
        for a in P:
            for b in U:
                den+=1; num+= 1 if a>b else .5 if a==b else 0
    return num/den if den else float('nan')
def stats(get):
    vals=[];within=[];races=[];n60=0;distinct=[];
    for r in rows:
        xs=[]
        for h in r["horses"]:
            if h.get("debut"): continue
            v=get(h)
            if v is None or h.get("pos") in (None,0): continue
            xs.append((v,h["pos"]<=3)); vals.append(v); n60+= abs(v-60)<1e-9
        if len(xs)>=4:
            races.append(xs); m=st.mean(v for v,_ in xs); within+= [v-m for v,_ in xs]; distinct.append(len({round(v,2) for v,_ in xs}))
    mode,mc=Counter(round(v,2) for v in vals).most_common(1)[0]
    return dict(n=len(vals),sd=st.pstdev(vals),wsd=st.pstdev(within),mn=min(vals),mx=max(vals),p60=n60/len(vals),mode=mode,modesh=mc/len(vals),distinct=st.median(distinct),auc=auc(races))
print(f"races={len(rows)}")
print(f"{'leaf':28s}{'n':>6s}{'SD':>6s}{'wSD':>6s}{'min':>6s}{'max':>6s}{'=60':>6s}{'mode':>7s}{'mode%':>6s}{'dist':>5s}{'AUC':>7s}")
leaves=sorted({k for r in rows for h in r["horses"] for k in h["f"]})
for L in leaves:
    s=stats(lambda h:h["f"].get(L))
    print(f"{L:28s}{s['n']:6d}{s['sd']:6.2f}{s['wsd']:6.2f}{s['mn']:6.1f}{s['mx']:6.1f}{s['p60']:6.2f}{s['mode']:7.2f}{s['modesh']:6.2f}{s['distinct']:5.0f}{s['auc']:7.4f}")
print("\n-- dimensions (raw m), influence = weight × within-race SD")
for D,(w,_) in W.items():
    s=stats(lambda h:h["m"].get(D))
    print(f"{D:28s}{s['n']:6d}{s['sd']:6.2f}{s['wSD']if False else s['wsd']:6.2f}{s['mn']:6.1f}{s['mx']:6.1f}{s['p60']:6.2f}{s['mode']:7.2f}{s['modesh']:6.2f}{s['distinct']:5.0f}{s['auc']:7.4f}  w={w:.4f} infl={w*s['wsd']:.3f}")
s=stats(lambda h:h["raw"]); print(f"{'composite raw':28s}{s['n']:6d}{s['sd']:6.2f}{s['wsd']:6.2f}{s['mn']:6.1f}{s['mx']:6.1f}  auc {s['auc']:.4f}")
