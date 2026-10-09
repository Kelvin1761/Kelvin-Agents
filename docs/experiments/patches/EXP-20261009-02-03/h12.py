import json, sys, random
sys.path.insert(0, sys.argv[1])
import au_eval as E
R = [r for r in E.load_races(sys.argv[2])]
CUT = '2026-09-09'
def fu180(x): return x.get('prep_stage') == 'first_up' and (x.get('days_since_last') or 0) >= 180
def debut(x): return x.get('prep_stage') == 'debut'
def shrink(f, keys, k):
    f = dict(f)
    for key in keys: f[key] = 60 + k * (f[key] - 60)
    return f
def arm(name):
    def scorer(row):
        f = row['features']
        if name in ('H1a','H1b') and fu180(row):
            f = shrink(f, ('form_score','performance_quality_score','pace_figure_score'), 0.5 if name=='H1a' else 0.0)
        if name in ('H2a','H2b') and debut(row):
            f = dict(f); f['form_score'] = f['trial_score']
            if name == 'H2b': f['performance_quality_score'] = f['trial_score']
        return E.default_scorer({**row, 'features': f})
    return scorer
def metrics(races, scorer):
    out=[]
    for r in races:
        rows=sorted(r['rows'], key=lambda x:(-scorer(x), x['n']))
        pos={x['n']:x['pos'] for x in rows}; top3=[n for n,p in pos.items() if p and p<=3]
        if len(top3)<3: out.append(None); continue
        m=E.race_metrics([x['n'] for x in rows], top3, None, pos, len(rows))
        out.append({'gold':m['gold'],'good':m['good_positional'],'field':len(rows),'sp':rows[0].get('sp')})
    return out
def ci(b,c,idx,key,B=2000,seed=7):
    p=[(int(c[i][key])-int(b[i][key])) for i in idx if b[i] and c[i]]
    if not p: return 0,0,0,0
    rng=random.Random(seed); m=len(p)
    ds=sorted(sum(p[rng.randrange(m)] for _ in range(m))/m for _ in range(B))
    return m, sum(p)/m, ds[int(.025*B)], ds[int(.975*B)-1]
def auc_ci(races, bs, cs):
    bp=E._pairs(races,bs,True); cp=E._pairs(races,cs,True); idx=list(range(len(races)))
    return E._auc_indices(cp,idx)-E._auc_indices(bp,idx), E._boot_ci(bp,cp,idx)
for window, races in (('判決語料 <09-09', [r for r in R if r['date']<CUT]),
                      ('  clean PIT 08-05→09-08', [r for r in R if '2026-08-05'<=r['date']<CUT]),
                      ('發現窗口(唔判) 09-09→', [r for r in R if r['date']>=CUT])):
    base=metrics(races, E.default_scorer)
    dates=sorted({r['date'] for r in races}); folds=[set(dates[i*len(dates)//5:(i+1)*len(dates)//5]) for i in range(5)]
    print(f'==== {window}: {len(races)} 場')
    for a in ('H1a','H1b','H2a','H2b'):
        cs=arm(a); cand=metrics(races, cs); idx=list(range(len(races)))
        g=ci(base,cand,idx,'gold'); d=ci(base,cand,idx,'good'); au,(lo,hi)=auc_ci(races,E.default_scorer,cs)
        fpos=0
        for f in folds:
            fi=[i for i in idx if races[i]['date'] in f]
            s=sum(int(cand[i]['gold'])+int(cand[i]['good'])-int(base[i]['gold'])-int(base[i]['good']) for i in fi if base[i] and cand[i])
            fpos+= s>=0
        affected=sum(1 for r in races if any((fu180(x) if a.startswith('H1') else debut(x)) for x in r['rows']))
        print(f'  {a}: 受影響場 {affected}  Gold {g[1]*100:+.2f}pp [{g[2]*100:+.2f},{g[3]*100:+.2f}]  Good {d[1]*100:+.2f}pp [{d[2]*100:+.2f},{d[3]*100:+.2f}]  AUC5 {au:+.5f} [{lo:+.5f},{hi:+.5f}]  fold≥0 {fpos}/5')
