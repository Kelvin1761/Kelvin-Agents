from pathlib import Path
import sys,json
from collections import Counter
import numpy as np
from scipy.stats import pearsonr
R=Path('/Users/imac/Antigravity-repo');W=Path('/Users/imac/.codex/worktrees/au-history-source-fix/Antigravity-repo');sys.path.insert(0,str(W/'.agents/skills/au_racing/au_wong_choi_auto/scripts'))
from au_leaf_power import within_race_auc
from au_racing_engine.scoring import parse_placing
O=R/'scratch/au_fixed_40_60_20261013';proj=json.loads((O/'projections.json').read_text());metadata={(r['meeting'],r['race']):r['metadata'] for r in json.loads((O/'signal_metadata.json').read_text())};runtime={(r['meeting'],r['race']):r for r in json.loads((R/'scratch/au_race_weight_oracle_20261013/runtime.json').read_text())['races']};race_rows={(r['meeting'],r['race']):r for r in json.loads((O/'rows.json').read_text())}
source_counts=Counter();scalars=[];records=[];transition_source=Counter()
for p in proj:
 key=(p['meeting'],p['race']);md=metadata[key];by={str(q['n']):q for q in runtime[key]['rows']};fs=p['projection']['rows'];classified={};scores={}
 for n in by:
  m=md[n];complete=m['pq_source'] in ['class_adjusted_margin_field_relative','sportsbet_complete_form_archive_recovery'];formal_valid=sum(parse_placing(e.get('placing')) is not None for e in m['official_entries'][:4]);group='complete_quality' if complete else 'fallback_quality';source_counts[group]+=1;classified[n]=(group,formal_valid)
 for group,pred in [('complete_quality',lambda n:classified[n][0]=='complete_quality'),('fallback_quality',lambda n:classified[n][0]=='fallback_quality'),('both_evidenced',lambda n:classified[n][0]=='complete_quality' and classified[n][1]>=1),('quality_without_formal_placing',lambda n:classified[n][0]=='complete_quality' and classified[n][1]==0)]:
  for feature in ['form_score','performance_quality_score']:
   scores[group+':'+feature]=within_race_auc([(fs[n]['feature_scores'][feature],q['pos']<=3) for n,q in by.items() if pred(n)])
 # Within-field centering before correlations: no between-race class shortcut.
 for feature in ['form_score','performance_quality_score','class_score','rating_score']:
  pass
 means={f:np.mean([fs[n]['feature_scores'][f] for n in by]) for f in ['form_score','performance_quality_score','class_score','rating_score']}
 for n in by:scalars.append([fs[n]['feature_scores'][f]-means[f] for f in means])
 row=race_rows[key]
 if row['baseline']['good_positional']!=row['candidate']['good_positional']:
  b=[n for n in p['baseline']['ranking'] if n in by][:2];c=[n for n in p['candidate']['ranking'] if n in by][:2];outcome='good_gain' if row['candidate']['good_positional']>row['baseline']['good_positional'] else 'good_loss'
  for n in set(c)-set(b): transition_source[(outcome,classified[n][0])]+=1
 records.append({'date':p['date'],'scores':scores})
def summary(rs):
 out={};ds=sorted({r['date'] for r in rs});rng=np.random.default_rng(7);idx={d:[i for i,r in enumerate(rs) if r['date']==d] for d in ds};draws=[np.concatenate([idx[d] for d in rng.choice(ds,len(ds),replace=True)]) for _ in range(2000)]
 for name in rs[0]['scores']:
  w=np.array([r['scores'][name][0] for r in rs]);n=np.array([r['scores'][name][1] for r in rs]);a=[w[i].sum()/n[i].sum() for i in draws if n[i].sum()];out[name]={'auc':float(w.sum()/n.sum()) if n.sum() else None,'pairs':int(n.sum()),'ci_day95':np.quantile(a,[.025,.975]).tolist() if a else None}
 return out
values=np.array(scalars);correlation={name:float(pearsonr(values[:,1],values[:,i])[0]) for name,i in [('PQ_FORM',0),('PQ_CLASS',2),('PQ_RATING',3)]}
report={'full':summary(records),'old_dev':summary([r for r in records if r['date']<='2026-09-21']),'later_period':summary([r for r in records if r['date']>'2026-09-21']),'source_runners':dict(source_counts),'within_field_centered_correlation':correlation,'new_top2_entrants':{' / '.join(k):v for k,v in transition_source.items()}}
(O/'source_signal_power.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
