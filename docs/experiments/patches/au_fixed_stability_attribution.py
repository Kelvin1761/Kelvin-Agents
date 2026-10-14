from pathlib import Path
import json,sys,copy
from collections import Counter
R=Path('/Users/imac/Antigravity-repo');O=R/'scratch/au_fixed_40_60_20261013';W=Path('/Users/imac/.codex/worktrees/au-history-source-fix/Antigravity-repo');sys.path.insert(0,str(W/'.agents/skills/au_racing/au_wong_choi_auto/scripts'))
from au_serve_training_projection import replay_projection
from au_racing_engine.scoring import MATRIX_WEIGHTS
import au_runtime_micro_ablation
from eval_metrics import race_metrics
old=json.loads((R/'scratch/au_stability_redesign_20261013/snapshot.json').read_text())['races'];old_by={(r['meeting'],r['race']):r for r in old};fresh=json.loads((O/'projections.json').read_text());current={(r['meeting'],r['race']):r for r in json.loads((O/'rows.json').read_text())};original={}
# old transitions don't include invariant races, so compute original metrics directly.
sys.path.insert(0,str(R/'docs/experiments/patches'));from au_stability_redesign import candidate_race,scorer,_stage4_metric_rows
races=[candidate_race(r) for r in old];b=_stage4_metric_rows(races,scorer());c=_stage4_metric_rows(races,scorer(form_share=.4))
feature_changes=Counter();feature_effect=Counter();transitions=Counter();policy_changes=Counter();examples=[]
for r,bm,cm in zip(races,b,c):original[(r['meeting'],r['race'])]=(bm,cm)
for r in fresh:
 key=(r['meeting'],r['race']);p=r['projection'];q=current[key]
 # Swapping first/second cannot change Gold/Good membership; verify with aligned IDs.
 for arm in ['baseline','candidate']:
  sorted_ids=sorted(p['runner_ids'],key=lambda n:(-r[arm]['ability'][n],int(n)))
  if r[arm]['ranking']!=sorted_ids: policy_changes[arm]+=1
  if key in old_by:
   ids={str(h['n']) for h in old_by[key]['full_rows'] if h['pos'] is not None};pos={str(h['n']):h['pos'] for h in old_by[key]['full_rows'] if h['pos'] is not None}
   metric=race_metrics([n for n in sorted_ids if n in ids],[n for n,v in pos.items() if v<=3],actual_pos=pos,field_size=len(ids))
   for k in ['gold','good_positional']: assert float(metric[k])==q[arm][k], 'Primary policy mismatch'
 if key not in old_by:continue
 br,cr=original[key];delta_old=int(cr['good_positional'])-int(br['good_positional']);delta_new=int(q['candidate']['good_positional'])-int(q['baseline']['good_positional']);transitions[f'old {delta_old:+d} -> current {delta_new:+d}']+=1
 for h in old_by[key]['full_rows']:
  if str(h['n']) not in p['rows']:continue
  f=p['rows'][str(h['n'])]['feature_scores'];changes={k:round(f[k]-v,6) for k,v in h['features'].items() if abs(f[k]-v)>1e-5}
  feature_changes.update(changes.keys())
  if delta_old!=delta_new:feature_effect.update(changes.keys())
 if delta_old==1 and delta_new!=1:
  examples.append({'meeting':r['meeting'],'race':r['race'],'old_baseline_good':int(br['good_positional']),'old_candidate_good':int(cr['good_positional']),'current_baseline_good':q['baseline']['good_positional'],'current_candidate_good':q['candidate']['good_positional']})
report={'old_features_current_formulas':{'n':len(races),'baseline_good':sum(int(m['good_positional']) for m in b),'candidate_good':sum(int(m['good_positional']) for m in c),'baseline_gold':sum(int(m['gold']) for m in b),'candidate_gold':sum(int(m['gold']) for m in c)},'policy_swaps':dict(policy_changes),'primary_same_with_and_without_swaps_on_old_dev':True,'feature_changes_runners':dict(feature_changes),'feature_changes_in_races_with_changed_good_delta':dict(feature_effect),'good_transition_map':dict(transitions),'original_gain_not_surviving_examples':examples[:12]}
(O/'attribution.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False)[:5000])
