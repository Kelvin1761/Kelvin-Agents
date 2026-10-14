from pathlib import Path
import sys,json,copy,hashlib,statistics,csv
from contextlib import redirect_stdout
from collections import Counter,defaultdict
import numpy as np
R=Path('/Users/imac/Antigravity-repo');W=Path('/Users/imac/.codex/worktrees/au-history-source-fix/Antigravity-repo');S=W/'.agents/skills/au_racing/au_wong_choi_auto/scripts';sys.path.insert(0,str(S))
from au_serve_training_projection import _capture_worker,replay_projection
from au_racing_engine.scoring import MATRIX_WEIGHTS
import au_runtime_micro_ablation
from eval_metrics import race_metrics
from au_archive_calibrator import load_historical_results,choose_track_rows,normalize_horse_name
OUT=R/'scratch/au_fixed_40_60_20261013'
def metric(r,rank):
 ids={str(q['n']) for q in r['rows']};order=[n for n in rank if n in ids];positions={str(q['n']):q['pos'] for q in r['rows']}
 x=race_metrics(order,[n for n,p in positions.items() if p<=3],actual_pos=positions,field_size=len(ids));return {k:float(x[k]) for k in ['gold','good_positional','pass','top3_capture_at5','top3_mean_model_rank','ndcg_at5']}
def summary(rows):
 if not rows:return {'n':0}
 dates=sorted({q['date'] for q in rows});groups={d:[i for i,q in enumerate(rows) if q['date']==d] for d in dates};rng=np.random.default_rng(7);draws=[np.concatenate([groups[d] for d in rng.choice(dates,len(dates),replace=True)]) for _ in range(2000)]
 out={'n':len(rows),'days':len(dates)}
 for k in rows[0]['baseline']:
  b=np.array([q['baseline'][k] for q in rows]);c=np.array([q['candidate'][k] for q in rows]);d=c-b
  out[k]={'baseline':float(b.mean()),'candidate':float(c.mean()),'delta':float(d.mean()),'ci95':np.quantile([d[i].mean() for i in draws],[.025,.975]).tolist()}
  if k in ['gold','good_positional','pass']:out[k].update({'baseline_count':int(b.sum()),'candidate_count':int(c.sum()),'gained':int(((b==0)&(c==1)).sum()),'lost':int(((b==1)&(c==0)).sum())})
 return out
runtime=json.loads((R/'scratch/au_race_weight_oracle_20261013/runtime.json').read_text())['races'];dev=json.loads((R/'scratch/au_stability_format_20261013/audit.json').read_text())['races'];term=json.loads((R/'scratch/au_stability_format_20261013/terminal.json').read_text())['races'];dev_ids={(r['meeting'],r['race']) for r in dev};eligible=dev_ids|{(r['meeting'],r['race']) for r in term}
results=load_historical_results(R.parent/'WongChoiData/Wong Choi Horse Race Analysis/AU_Racing/AU_Historical_Raw_Race_Results.csv')
rows=[];transitions=[];projections=[]
for race in runtime:
 if (race['meeting'],race['race']) not in eligible:continue
 captured=_capture_worker({'logic_path':race['source']});base=captured['baseline'];p=captured['projection'];cp=copy.deepcopy(p)
 for row in cp['rows'].values():
  f=row['feature_scores'];row['matrix_scores']['stability']=round(max(0,min(100,60+.4*(f['form_score']-60)+.6*(f['performance_quality_score']-60))),2)
 cand=replay_projection(cp,dict(MATRIX_WEIGHTS));bm=metric(race,base['ranking']);cm=metric(race,cand['ranking']);ids={str(q['n']) for q in race['rows']};first=next(n for n in base['ranking'] if n in ids);sp={q['horse_slug']:q.get('sp') for q in choose_track_rows(results.get((race['date'],race['race']),[]),race['metadata']['track'])};name=p['rows'][first]['horse_name']
 row={'date':race['date'],'meeting':race['meeting'],'race':race['race'],'field':len(ids),'full_field':len(p['rows']),'venue':race['metadata']['track'],'going':race['metadata'].get('going',''),'phase':'old_dev' if (race['meeting'],race['race']) in dev_ids else 'later_period','first_sp':sp.get(normalize_horse_name(name)),'baseline':bm,'candidate':cm}
 rows.append(row);projections.append({'date':race['date'],'meeting':race['meeting'],'race':race['race'],'projection':p,'candidate':cand,'baseline':base})
 if any(bm[k]!=cm[k] for k in ['gold','good_positional']):
  byid={str(q['n']):q for q in race['rows']};item={**row,'baseline_top4':base['ranking'][:4],'candidate_top4':cand['ranking'][:4]}
  item['horses']=[{'n':n,'name':p['rows'][n]['horse_name'],'pos':byid.get(n,{}).get('pos'),'form':p['rows'][n]['feature_scores']['form_score'],'pq':p['rows'][n]['feature_scores']['performance_quality_score'],'ability_before':base['ability'][n],'ability_after':cand['ability'][n]} for n in set(base['ranking'][:4]+cand['ranking'][:4])];transitions.append(item)
 if len(rows)%200==0:print('Current main projected',len(rows),flush=True)
(OUT/'rows.json').write_text(json.dumps(rows,ensure_ascii=False));(OUT/'transitions.json').write_text(json.dumps(transitions,ensure_ascii=False));(OUT/'projections.json').write_text(json.dumps(projections,ensure_ascii=False))
report={'design':{'main':'a0bf0f388bd6053641cc08d41b2915ee73bb7c5f','baseline_production_parity':'all captured scores and final rankings exact','candidate':'fixed FORM .4 / PQ .6; data-selected retrospective review, not independent validation','dataset_sha256':hashlib.sha256((R/'scratch/au_race_weight_oracle_20261013/runtime.json').read_bytes()).hexdigest()},'full':summary(rows),'old_dev':summary([q for q in rows if q['phase']=='old_dev']),'later_period':summary([q for q in rows if q['phase']=='later_period'])}
dates=sorted({q['date'] for q in rows});report['six_blocks']=[{'dates':[min(ds),max(ds)],**summary([q for q in rows if q['date'] in set(ds)])} for ds in np.array_split(dates,6)]
cohorts={}
for name,pred in [('field<=8',lambda r:r['field']<=8),('field9-10',lambda r:9<=r['field']<=10),('field11-12',lambda r:11<=r['field']<=12),('field13+',lambda r:r['field']>=13),('before_aug25',lambda r:r['date']<'2026-08-25'),('from_aug25',lambda r:r['date']>='2026-08-25')]+[(f'SP{lo}-{hi}',lambda r,lo=lo,hi=hi:r['first_sp'] is not None and lo<float(r['first_sp'])<=hi) for lo,hi in [(0,3),(3,6),(6,10),(10,21),(21,float('inf'))]]:
 cohorts[name]=summary([r for r in rows if pred(r)])
report['cohorts']=cohorts;report['venues']={v:summary([r for r in rows if r['venue']==v]) for v,count in Counter(r['venue'] for r in rows).items() if count>=50};report['going']={g:summary([r for r in rows if r['going'].lower().startswith(g)]) for g in ['good','soft','heavy','synthetic']};(OUT/'current_main_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:report[k] for k in ['full','old_dev','later_period']}),flush=True)
