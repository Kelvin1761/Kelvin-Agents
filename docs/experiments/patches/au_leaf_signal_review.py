from pathlib import Path
import sys,json
from collections import defaultdict
import numpy as np
R=Path('/Users/imac/Antigravity-repo');W=Path('/Users/imac/.codex/worktrees/au-history-source-fix/Antigravity-repo');sys.path.insert(0,str(W/'.agents/skills/au_racing/au_wong_choi_auto/scripts'))
from au_leaf_power import within_race_auc
O=R/'scratch/au_fixed_40_60_20261013';ps=json.loads((O/'projections.json').read_text());runtime=json.loads((R/'scratch/au_race_weight_oracle_20261013/runtime.json').read_text())['races'];by={(r['meeting'],r['race']):r for r in runtime}
records=[]
for p in ps:
 r=by[(p['meeting'],p['race'])];rows={str(q['n']):q for q in r['rows']};fs=p['projection']['rows'];scores={}
 for f in ['form_score','performance_quality_score','class_score','rating_score']:
  for mode in ['all','nonneutral']:
   pairs=[(fs[n]['feature_scores'][f],q['pos']<=3) for n,q in rows.items() if mode=='all' or abs(fs[n]['feature_scores'][f]-60)>.005];scores[f+':'+mode]=within_race_auc(pairs)
 for arm in ['baseline','candidate']:scores['ability:'+arm]=within_race_auc([(p[arm]['ability'][n],q['pos']<=3) for n,q in rows.items()])
 for label,other in [('pq_vs_form','form_score'),('pq_vs_baseline','ability')]:
  win=count=0
  for g,q in rows.items():
   if q['pos']>3:continue
   for n,b in rows.items():
    if b['pos']<=3:continue
    pq=fs[g]['feature_scores']['performance_quality_score']-fs[n]['feature_scores']['performance_quality_score'];o=(p['baseline']['ability'][g]-p['baseline']['ability'][n]) if other=='ability' else fs[g]['feature_scores'][other]-fs[n]['feature_scores'][other]
    if pq*o<0:count+=1;win+=int(pq>0)
  scores[label]=(win,count)
 records.append({'date':p['date'],'scores':scores})
def summary(rs):
 out={};ds=sorted({r['date'] for r in rs});idx={d:[i for i,r in enumerate(rs) if r['date']==d] for d in ds};rng=np.random.default_rng(7);draws=[np.concatenate([idx[d] for d in rng.choice(ds,len(ds),replace=True)]) for _ in range(2000)]
 for name in rs[0]['scores']:
  w=np.array([r['scores'][name][0] for r in rs],dtype=float);n=np.array([r['scores'][name][1] for r in rs],dtype=float);vals=[w[i].sum()/n[i].sum() for i in draws if n[i].sum()];out[name]={'auc':float(w.sum()/n.sum()) if n.sum() else None,'pairs':int(n.sum()),'ci_day95':np.quantile(vals,[.025,.975]).tolist() if vals else None}
 return out
report={'full':summary(records),'old_dev':summary([r for r in records if r['date']<='2026-09-21']),'later_period':summary([r for r in records if r['date']>'2026-09-21'])};(O/'signal_power.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
