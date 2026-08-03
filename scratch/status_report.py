"""現行引擎全貌：整體表現 + 逐個 leaf 狀態。713 場。唯讀。"""
import json, statistics, sys
from pathlib import Path
import numpy as np
sys.path.insert(0,'.agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine')
sys.path.insert(0,'.agents/skills/shared_racing')
from eval_metrics import race_metrics, summarize_races
from matrix_mapper import MATRIX_FORMULAS, MATRIX_DISPLAY_GAINS
from scoring import MATRIX_WEIGHTS

races=json.loads(Path('scratch/fl_new.json').read_text())['races']
rows=[h for rc in races for h in rc['rows']]
def ev(lo,hi):
    out=[]
    for rc in races[lo:hi]:
        pos={h['n']:h['pos'] for h in rc['rows']}
        picks=[h['n'] for h in sorted(rc['rows'],key=lambda h:(-h['ability'],h['n']))]
        t3=[n for n,p in pos.items() if p<=3]; w=[n for n,p in pos.items() if p==1]
        out.append(race_metrics(picks,t3,winner=w[0] if w else None,actual_pos=pos,field_size=rc['field']))
    return summarize_races(out)
n=len(races); split=int(n*0.85)
print("="*78); print("整體表現（現行引擎，713 場）"); print("="*78)
lab=[("至少一隻上名馬入前三","pass_any1"),("前三中兩隻","good_any2"),
     ("三隻全中（Gold）","gold"),("位置全對（good_positional）","good_positional"),
     ("首選 = 頭馬","champion"),("頭馬入前三","winner_in_top3")]
print(f"{'':34}{'全樣本':>10}{'dev 606':>10}{'holdout 107':>13}")
A,D,H=ev(0,n),ev(0,split),ev(split,n)
for nm,k in lab:
    print(f"{nm:34}{100*A['rates'][k]:>9.1f}%{100*D['rates'][k]:>9.1f}%{100*H['rates'][k]:>12.1f}%")
for nm,f in (("前三精準度",lambda s:100*s['top3_precision']),("MRR",lambda s:100*s['mrr']),
             ("首選有競爭力",lambda s:100*s['competitiveness']['top_pick_competitive']['rate']),
             ("首選爆冷",lambda s:100*s['competitiveness']['top_pick_blowout']['rate']),
             ("nDCG@5",lambda s:100*s['competitiveness']['mean_ndcg_at5'])):
    print(f"{nm:34}{f(A):>9.1f}%{f(D):>9.1f}%{f(H):>12.1f}%")

# ── leaf 狀態 ──
def rho(leaf):
    out=[]
    for rc in races:
        rs=rc['rows']
        if len(rs)<4: continue
        x=[h['features'].get(leaf,60) for h in rs]; y=[-h['pos'] for h in rs]
        if len(set(x))<2: continue
        def rk(v):
            o=sorted(range(len(v)),key=lambda i:v[i]); r=[0]*len(v); i=0
            while i<len(o):
                j=i
                while j+1<len(o) and v[o[j+1]]==v[o[i]]: j+=1
                for k in range(i,j+1): r[o[k]]=(i+j)/2+1
                i=j+1
            return r
        rx,ry=rk(x),rk(y); m=len(x); mx=sum(rx)/m; my=sum(ry)/m
        num=sum((a-mx)*(b-my) for a,b in zip(rx,ry))
        den=(sum((a-mx)**2 for a in rx)*sum((b-my)**2 for b in ry))**.5
        if den: out.append(num/den)
    return (statistics.mean(out), len(out)) if out else (0.0,0)
def gap(leaf):
    hi=lo=hn=ln=0
    for rc in races:
        rs=sorted(rc['rows'], key=lambda h:-h['features'].get(leaf,60))
        k=max(1,len(rs)//4)
        for h in rs[:k]: hn+=1; hi+=(h['pos']<=3)
        for h in rs[-k:]: ln+=1; lo+=(h['pos']<=3)
    return 100*hi/hn-100*lo/ln

eff={}
for dim,comps in MATRIX_FORMULAS.items():
    for lf,iw in comps:
        eff[lf]=eff.get(lf,0.0)+MATRIX_WEIGHTS.get(dim,0.0)*MATRIX_DISPLAY_GAINS.get(dim,1.0)*iw
sd={lf: statistics.mean(float(np.std([h['features'].get(lf,60) for h in rc['rows']],ddof=1))
                        for rc in races if len(rc['rows'])>1) for lf in eff}
infl={lf: eff[lf]*sd[lf] for lf in eff}
tot=sum(infl.values())
print("\n"+"="*78); print("逐個 leaf 狀態（按實際影響力排）"); print("="*78)
print(f"{'leaf':24}{'影響力':>8}{'有效權重':>10}{'場內SD':>8}{'場內ρ':>8}{'Q1−Q4':>8}{'中性佔比':>9}{'範圍':>14}")
for lf in sorted(eff, key=lambda k:-infl[k]):
    r,_=rho(lf); g=gap(lf)
    v=np.array([h['features'].get(lf,60) for h in rows])
    neu=100*np.mean(np.abs(v-60)<1e-6)
    print(f"{lf:24}{100*infl[lf]/tot:>7.1f}%{eff[lf]:>10.4f}{sd[lf]:>8.2f}{r:>+8.3f}{g:>+8.1f}"
          f"{neu:>8.1f}%{f'{v.min():.0f}–{v.max():.0f}':>14}")
