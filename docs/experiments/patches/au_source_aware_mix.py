from pathlib import Path
import sys,json,copy
import numpy as np
R=Path('/Users/imac/Antigravity-repo');W=Path('/Users/imac/.codex/worktrees/au-history-source-fix/Antigravity-repo');sys.path.insert(0,str(W/'.agents/skills/au_racing/au_wong_choi_auto/scripts'))
from au_serve_training_projection import replay_projection
from au_racing_engine.scoring import MATRIX_WEIGHTS
import au_runtime_micro_ablation
from eval_metrics import race_metrics
O=R/'scratch/au_fixed_40_60_20261013';projections=json.loads((O/'projections.json').read_text());meta={(r['meeting'],r['race']):r['metadata'] for r in json.loads((O/'signal_metadata.json').read_text())};runtime={(r['meeting'],r['race']):r for r in json.loads((R/'scratch/au_race_weight_oracle_20261013/runtime.json').read_text())['races']};comparison={(r['meeting'],r['race']):r for r in json.loads((O/'rows.json').read_text())}
rows=[];changed=0
for pr in projections:
 key=(pr['meeting'],pr['race']);r=runtime[key];p=copy.deepcopy(pr['projection']);md=meta[key]
 for n,row in p['rows'].items():
  if md[n]['pq_source'] in ['class_adjusted_margin_field_relative','sportsbet_complete_form_archive_recovery']:
   fs=row['feature_scores'];row['matrix_scores']['stability']=round(max(0,min(100,60+.4*(fs['form_score']-60)+.6*(fs['performance_quality_score']-60))),2);changed+=1
 result=replay_projection(p,dict(MATRIX_WEIGHTS));ids={str(q['n']) for q in r['rows']};positions={str(q['n']):q['pos'] for q in r['rows']};m=race_metrics([n for n in result['ranking'] if n in ids],[n for n,pos in positions.items() if pos<=3],actual_pos=positions,field_size=len(ids));metrics={k:float(m[k]) for k in comparison[key]['baseline']};row=dict(comparison[key]);row['source_aware']=metrics;rows.append(row)
def summary(rs,reference):
 out={'n':len(rs)};dates=sorted({r['date'] for r in rs});idx={d:[i for i,r in enumerate(rs) if r['date']==d] for d in dates};rng=np.random.default_rng(7);draws=[np.concatenate([idx[d] for d in rng.choice(dates,len(dates),replace=True)]) for _ in range(2000)]
 for k in rs[0]['baseline']:
  b=np.array([r[reference][k] for r in rs]);c=np.array([r['source_aware'][k] for r in rs]);delta=c-b;out[k]={'baseline':float(b.mean()),'candidate':float(c.mean()),'delta':float(delta.mean()),'ci_day95':np.quantile([delta[i].mean() for i in draws],[.025,.975]).tolist()}
  if k in ['gold','good_positional','pass']:out[k].update({'baseline_count':int(b.sum()),'candidate_count':int(c.sum()),'gain':int((delta==1).sum()),'loss':int((delta==-1).sum())})
 return out
report={'mode':'data-selected exploratory; no independent validation','source_eligible_pre_field_horses':changed,'full':summary(rows,'baseline'),'against_uniform40':summary(rows,'candidate'),'old_dev':summary([r for r in rows if r['phase']=='old_dev'],'baseline'),'later_period':summary([r for r in rows if r['phase']=='later_period'],'baseline')};dates=sorted({r['date'] for r in rows});report['six_blocks']=[{'dates':[min(ds),max(ds)],**summary([r for r in rows if r['date'] in set(ds)],'baseline')} for ds in np.array_split(dates,6)];report['cohorts']={name:summary([r for r in rows if pred(r)],'baseline') for name,pred in [('field<=8',lambda r:r['field']<=8),('field9-10',lambda r:9<=r['field']<=10),('field11-12',lambda r:11<=r['field']<=12),('field13+',lambda r:r['field']>=13)]+[(f'SP{lo}-{hi}',lambda r,lo=lo,hi=hi:r['first_sp'] is not None and lo<float(r['first_sp'])<=hi) for lo,hi in [(0,3),(3,6),(6,10),(10,21),(21,float('inf'))]]}
(O/'source_aware_rows.json').write_text(json.dumps(rows,ensure_ascii=False));(O/'source_aware_mix.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:report[k] for k in ['full','against_uniform40','old_dev','later_period']}),flush=True)
