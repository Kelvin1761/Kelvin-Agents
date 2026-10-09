"""§7 正確性修正檢查：primary dev/terminal 配對 CI + 預先聲明 cohort（馬群 ×4、首選 SP ×5）。"""
import json, sys, random
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import au_eval as E
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ab_merge import merge  # noqa: E402
merged = merge(E.load_races(sys.argv[2]), E.load_races(sys.argv[3]))
cand = lambda row: E.default_scorer(row['_c'])
def per_race(races, scorer):
    out=[]
    for r in races:
        rows = sorted(r['rows'], key=lambda x: -scorer(x))
        picks=[x['n'] for x in rows]; pos={x['n']:x['pos'] for x in rows}
        top3=[n for n,p in pos.items() if p and p<=3]
        if len(top3)<3: out.append(None); continue
        m=E.race_metrics(picks, top3, None, pos, len(rows))
        sp = next((x.get('sp') for x in rows[:1]), None)
        out.append({'gold':m['gold'],'good':m['good_positional'],'field':len(rows),'sp':sp})
    return out
b=per_race(merged, E.default_scorer); c=per_race(merged, cand)
dev, term = E.date_partitions(merged)
def ci(idx, key, seed=7, B=2000):
    pairs=[(int(c[i][key]),int(b[i][key])) for i in idx if b[i] and c[i]]
    rng=random.Random(seed); m=len(pairs)
    pt=sum(x-y for x,y in pairs)/m
    ds=sorted(sum(pairs[rng.randrange(m)][0]-pairs[rng.randrange(m)][1] if False else (lambda p:p[0]-p[1])(pairs[rng.randrange(m)]) for _ in range(m))/m for _ in range(B))
    return m, pt, ds[int(.025*B)], ds[int(.975*B)-1]
for name, idx in (('dev',dev),('terminal',term),('all',list(range(len(merged))))):
    for k in ('gold','good'):
        m,pt,lo,hi=ci(idx,k); print(f'{name:8s} {k:5s} n={m} Δ={pt*100:+.2f}pp CI[{lo*100:+.2f},{hi*100:+.2f}]')
def fb(n): return '≤8' if n<=8 else ('9-10' if n<=10 else ('11-12' if n<=12 else '13+'))
def sb(s):
    if not s: return None
    return '≤2' if s<=2 else ('2-4' if s<=4 else ('4-8' if s<=8 else ('8-15' if s<=15 else '15+')))
allidx=list(range(len(merged)))
for label, f in (('field', lambda i: fb(b[i]['field'])), ('base top-pick SP', lambda i: sb(b[i]['sp']))):
    groups={}
    for i in allidx:
        if b[i] and c[i]:
            g=f(i)
            if g: groups.setdefault(g,[]).append(i)
    for g,idx in sorted(groups.items()):
        for k in ('gold','good'):
            m,pt,lo,hi=ci(idx,k); flag='  ❌ CI 全負' if hi<0 else ''
            print(f'{label:16s} {g:6s} {k:5s} n={m} Δ={pt*100:+.2f}pp CI[{lo*100:+.2f},{hi*100:+.2f}]{flag}')
