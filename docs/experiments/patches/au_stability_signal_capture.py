from pathlib import Path
import sys,json
R=Path('/Users/imac/Antigravity-repo');W=Path('/Users/imac/.codex/worktrees/au-history-source-fix/Antigravity-repo');sys.path.insert(0,str(W/'.agents/skills/au_racing/au_wong_choi_auto/scripts'))
import au_auto_orchestrator as auto
O=R/'scratch/au_fixed_40_60_20261013';projections=json.loads((O/'projections.json').read_text());original=auto.RacingEngine
sources={(r['meeting'],r['race']):Path(r['source']) for r in json.loads((R/'scratch/au_race_weight_oracle_20261013/runtime.json').read_text())['races']}
metadata={}
class MetadataEngine(original):
 def analyze_horse(self):
  result=super().analyze_horse();n=str(self.horse_data['horse_number']);pq=getattr(self,'performance_quality_detail',{}) or {};fd=getattr(self,'form_detail',{}) or {}
  metadata[n]={'pq_source':result['score_provenance'].get('performance_quality_score'),'pq_run_count':pq.get('run_count',0),'pq_runs':pq.get('runs') or [],'form_valid_rows':len(fd.get('rows') or []),'career_starts':self._career_starts(),'official_entries':self._official_entries()}
  return result
out=[];auto.RacingEngine=MetadataEngine
try:
 for p in projections:
  metadata.clear();path=sources[(p['meeting'],p['race'])]
  logic=auto.score_logic_data(path)
  # Same source/version snapshot, not metadata from a different scoring run.
  assert {n:h['python_auto']['ability_score'] for n,h in logic['horses'].items()}==p['baseline']['ability']
  out.append({'date':p['date'],'meeting':p['meeting'],'race':p['race'],'metadata':dict(metadata)})
  if len(out)%300==0:print('metadata parity',len(out),flush=True)
finally:auto.RacingEngine=original
(O/'signal_metadata.json').write_text(json.dumps(out,ensure_ascii=False));print('complete',len(out),flush=True)
