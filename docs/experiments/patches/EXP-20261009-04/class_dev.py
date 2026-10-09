import json, sys, random
sys.path.insert(0, sys.argv[1])
import au_eval as E
from au_racing_engine.scoring import MATRIX_WEIGHTS
R=[r for r in E.load_races(sys.argv[2]) if r['date'] < '2026-09-09']
CW=MATRIX_WEIGHTS['class_weight']
def metrics(races, scorer):
    out=[]
    for r in races:
        rows=sorted(r['rows'], key=lambda x:(-scorer(x), x['n']))
        pos={x['n']:x['pos'] for x in rows}; top3=[n for n,p in pos.items() if p and p<=3]
        if len(top3)<3: out.append(None); continue
        m=E.race_metrics([x['n'] for x in rows], top3, None, pos, len(rows))
        out.append((int(m['gold']), int(m['good_positional'])))
    return out
def ci(d,B=2000,seed=7):
    rng=random.Random(seed); m=len(d); s=sorted(sum(d[rng.randrange(m)] for _ in range(m))/m for _ in range(B)); return s[int(.025*B)], s[int(.975*B)-1]
base=metrics(R, E.default_scorer)
dates=sorted({r['date'] for r in R}); folds=[set(dates[i*len(dates)//5:(i+1)*len(dates)//5]) for i in range(5)]
print(f'dev races {len(R)}  dates {dates[0]}..{dates[-1]}  class_weight coef {CW:.4f}')
for k in (0.15, 0.30, 0.60):
    c=CW*k
    cand=metrics(R, lambda x,c=c: E.default_scorer(x)+c*(x['features']['class_score']-60))
    idx=[i for i in range(len(R)) if base[i] and cand[i]]
    dg=[cand[i][0]-base[i][0] for i in idx]; dd=[cand[i][1]-base[i][1] for i in idx]
    fpos=sum(1 for f in folds if sum(dg[j]+dd[j] for j,i in enumerate(idx) if R[i]['date'] in f)>=0)
    lo,hi=ci(dg); lo2,hi2=ci(dd)
    print(f'k={k}: Gold {100*sum(dg)/len(idx):+.2f}pp [{100*lo:+.2f},{100*hi:+.2f}]  Good {100*sum(dd)/len(idx):+.2f}pp [{100*lo2:+.2f},{100*hi2:+.2f}]  sum {sum(dg)+sum(dd):+d} races  fold≥0 {fpos}/5')
