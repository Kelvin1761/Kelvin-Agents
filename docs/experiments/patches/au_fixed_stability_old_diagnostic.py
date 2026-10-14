from pathlib import Path
import sys,json
from collections import Counter
import numpy as np
R=Path('/Users/imac/Antigravity-repo');sys.path.insert(0,str(R/'docs/experiments/patches'))
from au_stability_redesign import scorer,candidate_race,_stage4_metric_rows
from scipy.stats import binomtest
snap=json.loads((R/'scratch/au_stability_redesign_20261013/snapshot.json').read_text());races=[candidate_race(r) for r in snap['races']];b=_stage4_metric_rows(races,scorer());c=_stage4_metric_rows(races,scorer(form_share=.4));rows=[]
for race,bm,cm in zip(races,b,c):
 for m in [bm,cm]:
  m['gold_or_good']=bool(m['gold'] or m['good_positional']);m['gold_and_good']=bool(m['gold'] and m['good_positional'])
 changed={k:cm[k]-bm[k] for k in ['gold','good_positional']}
 br=sorted(race['rows'],key=scorer(),reverse=True);cr=sorted(race['rows'],key=scorer(form_share=.4),reverse=True)
 rows.append({'date':race['date'],'meeting':race['meeting'],'race':race['race'],'field':race['field'],'missing_form':any(not (r['form_detail'].get('rows')) and r['pq_source']=='class_adjusted_margin_field_relative' for r in race['rows']),'baseline':bm,'candidate':cm,'baseline_top4':[r['n'] for r in br[:4]],'candidate_top4':[r['n'] for r in cr[:4]],'horses':[{k:r[k] for k in ['n','name','pos','pq_source']}|{'form':r['features']['form_score'],'pq':r['features']['performance_quality_score'],'has_form_rows':bool(r['form_detail'].get('rows'))} for r in race['rows'] if r['n'] in {q['n'] for q in br[:4]+cr[:4]}]})
def summary(rows):
 dates=sorted({r['date'] for r in rows});groups={d:[i for i,r in enumerate(rows) if r['date']==d] for d in dates};rng=np.random.default_rng(7);draws=[np.concatenate([groups[d] for d in rng.choice(dates,len(dates),replace=True)]) for _ in range(2000)]
 out={'n':len(rows),'days':len(dates)}
 for k in ['gold','good_positional','gold_or_good','gold_and_good']:
  base=np.array([r['baseline'][k] for r in rows],dtype=float);cand=np.array([r['candidate'][k] for r in rows],dtype=float);delta=cand-base;gain=int((delta==1).sum());loss=int((delta==-1).sum());byday=Counter()
  for r,d in zip(rows,delta):byday[r['date']]+=int(d)
  out[k]={'baseline_count':int(base.sum()),'candidate_count':int(cand.sum()),'net':int(delta.sum()),'gain':gain,'loss':loss,'ci_day95':np.quantile([delta[i].mean() for i in draws],[.025,.975]).tolist(),'positive_days':sum(v>0 for v in byday.values()),'negative_days':sum(v<0 for v in byday.values()),'biggest_day_gain':max(byday.values()),'biggest_day_loss':min(byday.values()),'day_net':dict(sorted(byday.items())),'mcnemar_exact_p_unadjusted':float(binomtest(gain,gain+loss).pvalue) if gain+loss else 1}
 return out
report={'overall':summary(rows),'original_five_folds':[summary([r for r in rows if r['date'] in set(ds)]) for ds in np.array_split(sorted({r['date'] for r in rows}),5)],'cohorts':{name:summary([r for r in rows if pred(r)]) for name,pred in [('has_missing_form',lambda r:r['missing_form']),('no_missing_form',lambda r:not r['missing_form']),('before_aug25',lambda r:r['date']<'2026-08-25'),('from_aug25',lambda r:r['date']>='2026-08-25')]}}
O=R/'scratch/au_fixed_40_60_20261013';(O/'old_all_rows.json').write_text(json.dumps(rows,ensure_ascii=False));(O/'old_snapshot_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));(O/'old_transitions.json').write_text(json.dumps([r for r in rows if any(r['baseline'][k]!=r['candidate'][k] for k in ['gold','good_positional'])],ensure_ascii=False));print(json.dumps(report['overall']),flush=True);print('cohorts',[(k,v['n'],v['gold']['net'],v['good_positional']['net']) for k,v in report['cohorts'].items()])
