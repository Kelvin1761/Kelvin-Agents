"""Fixed-rule source correctness and predeclared count shrink; no fitted values."""
import copy, importlib.util, json, sys, os
from pathlib import Path
from unittest.mock import patch
import numpy as np
R=Path(os.environ.get('AU_INTEGRITY_REPO', str(Path(__file__).resolve().parents[3]))); W=Path(os.environ.get('AU_INTEGRITY_WORKTREE', str(R)))
S=W/'.agents/skills/au_racing/au_wong_choi_auto/scripts';sys.path.insert(0,str(S))
from au_racing_engine import engine_core as new
from au_auto_orchestrator import _build_field_summary
import au_runtime_micro_ablation as rt
from eval_metrics import race_metrics
from au_archive_calibrator import load_historical_results, choose_track_rows, normalize_horse_name
spec=importlib.util.spec_from_file_location('au_racing_engine._before_source_fix', R/'scratch/au_history_source_fix_20261013/release_baseline/.agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine/engine_core.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
for key, value in vars(new).items():
 if isinstance(value, Path) and key in vars(old): setattr(old,key,value)
old.__file__=new.__file__
# baseline parser comes from the same immutable main source, not the new API.
ns={'__name__':'au_racing_engine._old_scoring','__package__':'au_racing_engine'};exec((R/'scratch/au_history_source_fix_20261013/release_baseline/.agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine/scoring.py').read_text(), ns);old.parse_recent_finishes=ns['parse_recent_finishes']
class Shrunk(new.RacingEngine):
 def _pace_figure_score(self):
  value,note,source=super()._pace_figure_score()
  if source!='pf_l600_delta_field_relative':return value,note,source
  a=self._pf_metrics()['pf_aggregates']; key='own_l600_delta' if self.pace_figure_detail['basis']=='own' else 'l600_delta'
  n=int((a.get('value_counts') or {}).get(key, a.get('pf_run_count',0)))
  return 60+(value-60)*min(1,n/3),note,source

def prepare(logic,path,module):
 with patch.object(rt,'enrich_logic_from_facts',module.enrich_logic_from_facts):return rt.prepare_logic_for_scoring(logic,path)
def score(p,fp,cls):
 ctx=copy.deepcopy(p['race_analysis']);ctx['field_summary']=_build_field_summary(p['horses']);ctx['field_horse_names']=[h['horse_name'] for h in p['horses'].values()]
 result={}
 for n,h in p['horses'].items():
  h=copy.deepcopy(h);h.setdefault('horse_number',int(n));e=cls(h,ctx,facts_section=h['_data'].get('facts_section',''),facts_path=fp);result[int(n)]=e.analyze_horse()
 return result

def metrics(r,res):
 rows=r['rows'];ids={q['n'] for q in rows}; order=sorted(ids,key=lambda n:(-res[n]['ability_score'],n));positions={q['n']:q['pos'] for q in rows}
 x=race_metrics(order,[n for n,p in positions.items() if p<=3],actual_pos=positions,field_size=len(rows));return {k:float(x[k]) for k in ('gold','good_positional','pass','top3_mean_model_rank','top3_capture_at5','ndcg_at5','top5_pairwise_auc') if k in x}
runtime=json.loads((R/'scratch/au_race_weight_oracle_20261013/runtime.json').read_text())['races']; dev=json.loads((R/'scratch/au_stability_format_20261013/audit.json').read_text())['races'];term=json.loads((R/'scratch/au_stability_format_20261013/terminal.json').read_text())['races'];eligible={(r['meeting'],r['race']) for r in dev+term}
results=load_historical_results(R.parent/'WongChoiData/Wong Choi Horse Race Analysis/AU_Racing/AU_Historical_Raw_Race_Results.csv')
out=R/'scratch/au_history_source_fix_20261013';out.mkdir(exist_ok=True)
pairs=[];changed=[0,0]; leaves=[]
for r in runtime:
 if (r['meeting'],r['race']) not in eligible:continue
 path=Path(r['source']);logic=json.loads(path.read_text()); b,fp=prepare(logic,path,old);c,_=prepare(logic,path,new); br=score(b,fp,old.RacingEngine);cr=score(c,fp,new.RacingEngine);tr=score(c,fp,Shrunk)
 row={'date':r['date'],'meeting':r['meeting'],'race':r['race'],'field':len(r['rows']),'baseline':metrics(r,br),'source_fix':metrics(r,cr),'weak_pf':metrics(r,tr)}
 first=min(r['rows'],key=lambda q:(-br[q['n']]['ability_score'],q['n'])); sp={q['horse_slug']:q.get('sp') for q in choose_track_rows(results.get((r['date'],r['race']),[]),r['metadata']['track'])};row['first_sp']=sp.get(normalize_horse_name(first['name']));pairs.append(row)
 for i,res in enumerate([cr,tr]):changed[i]+=sum(br[n]['ability_score']!=res[n]['ability_score'] for n in br)
 leaves.append({'date':r['date'],'meeting':r['meeting'],'race':r['race'],'rows':[{'n':q['n'],'pos':q['pos'],'baseline':br[q['n']]['ability_score'],'source_fix':cr[q['n']]['ability_score'],'weak_pf':tr[q['n']]['ability_score']} for q in r['rows']]})
 if len(pairs)%150==0:print('Evaluated',len(pairs), 'changed',changed,flush=True)
# Paired race-day bootstrap preserves within-day dependence.
def summary(rows,arm):
 if not rows:return {'n':0}
 dates=sorted({r['date'] for r in rows});deltas={k:np.array([r[arm][k]-r['baseline'][k] for r in rows]) for k in rows[0]['baseline']};rng=np.random.default_rng(7);groups={d:[i for i,r in enumerate(rows) if r['date']==d] for d in dates};idx=[np.concatenate([groups[d] for d in rng.choice(dates,len(dates),replace=True)]) for _ in range(2000)]
 return {'n':len(rows),**{k:{'baseline':np.mean([r['baseline'][k] for r in rows]),'delta':float(v.mean()),'ci95':np.quantile([v[a].mean() for a in idx],[.025,.975]).tolist()} for k,v in deltas.items()}}
dates=sorted({r['date'] for r in pairs});report={'baseline_sha':'c9620bd0f37381a7b3634e3b8d2e2f8b5247c6f1','mode':'fixed_rule','pairs':pairs,'changed_horses':changed}
for arm in ['source_fix','weak_pf']:
 report[arm]={'full':summary(pairs,arm),'blocks':[summary([r for r in pairs if r['date'] in set(ds)],arm) for ds in np.array_split(dates,6)],'cohorts':{}}
 for label,pred in [('field<=8',lambda r:r['field']<=8),('field9-10',lambda r:9<=r['field']<=10),('field11-12',lambda r:11<=r['field']<=12),('field13+',lambda r:r['field']>=13)]+[(f'SP{lo}-{hi}',lambda r,lo=lo,hi=hi:r['first_sp'] is not None and lo<float(r['first_sp'])<=hi) for lo,hi in [(0,3),(3,6),(6,10),(10,21),(21,float('inf'))]]:
  report[arm]['cohorts'][label]=summary([r for r in pairs if pred(r)],arm)
(out/'evaluation.json').write_text(json.dumps(report,ensure_ascii=False));(out/'paired_abilities.json').write_text(json.dumps(leaves,ensure_ascii=False));print(json.dumps({a:report[a]['full'] for a in ['source_fix','weak_pf']}),flush=True)
