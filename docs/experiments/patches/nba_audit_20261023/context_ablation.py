"""Code-only ablations on a fixed pre-tip NBA corpus; no publishing or fitting.

Each arm is materialized from immutable 0bffbeb6 plus explicit context patches.
The formal SGM quote fix is deliberately outside this experiment: these are
proposed combinations before a bookmaker quote, never actionable bets.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

BASE = '0bffbeb674d32ef9cc79722c931751c35250315a'
REL = Path('.agents/skills/nba/nba_wong_choi/scripts')
FEATURES = ('injury_status', 'mc_usage', 'team_pace', 'blowout')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError(f'patch anchor is not unique: {before[:70]}')
    return source.replace(before, after, 1)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline-code',type=Path,required=True)
    parser.add_argument('--candidate-code',type=Path,required=True)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=3)
    args=parser.parse_args()
    if not os.path.ismount('/Volumes/Kelvin Hardisk 1'):
        raise SystemExit('external volume is not mounted')
    actual=subprocess.check_output(['git','-C',str(args.baseline_code),'rev-parse','HEAD'],text=True).strip()
    if actual!=BASE:raise ValueError('baseline commit changed')
    experiment=args.root/'context_ablation_v1';experiment.mkdir(exist_ok=False)
    manifest=args.root/'strict_priced_manifest.json';cases=json.loads(manifest.read_text())['cases']
    model=Path('/Users/imac/WongChoiData/NBA_ML_Dataset/models/v3')
    model_hashes={name:sha(model/name) for name in ('model.pkl','feature_names.json')}
    arms={name:{feature:feature==name for feature in FEATURES} for name in FEATURES}
    arms['full']={feature:True for feature in FEATURES}
    arms.update({'minus_'+name:{feature:feature!=name for feature in FEATURES} for name in FEATURES})
    current_renderer=(args.candidate_code/REL/'generate_nba_reports.py').read_text()
    current_mc=(args.candidate_code/REL/'monte_carlo_nba.py').read_text()
    mc_helper=current_mc[current_mc.index('def usage_bonus_stat_units('):current_mc.index('def compute_context_factors(')]
    protocol={'base_commit':BASE,'input_manifest_sha256':sha(manifest),'cases':len(cases),'arms':arms,
              'model_hashes':model_hashes,'simulation_draws':10000,'seed_policy':'unchanged stable per-game/per-leg',
              'purpose':'feature/selection diagnostics; no quotes, betting, weight fitting or promotion',
              'sources':{},'mc_usage_assumption':'constant scoring efficiency; relative USG volume for PTS/3PM only'}
    for name,flags in arms.items():
        code=experiment/name/'code';code.mkdir(parents=True)
        for directory in ('.agents/skills/nba','.agents/scripts/nba_ml'):
            shutil.copytree(args.baseline_code/directory,code/directory,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        shutil.copy2(args.baseline_code/'wongchoi_paths.py',code/'wongchoi_paths.py')
        shutil.copy2(args.candidate_code/'.agents/skills/nba/nba_availability.py',code/'.agents/skills/nba/nba_availability.py')
        source=(code/REL/'generate_nba_reports.py').read_text()
        if flags['injury_status']:
            source=replace_once(source,'from nba_identity import player_name_key',
                                'from nba_identity import player_name_key\nfrom nba_availability import usage_from_injuries, usage_bonus_for')
            source=replace_once(source,'usg_redistribution = extractor.get("usage_redistribution", {})',
                                'usg_redistribution = usage_from_injuries(ext_players, injuries)')
            source=replace_once(source,'usg_bonus = usg_redistribution.get(team, {}).get(player_name, {}).get("bonus_USG", 0)',
                                'usg_bonus = usage_bonus_for(usg_redistribution, team, player_name)')
        if flags['mc_usage']:
            start=current_renderer.index('    from monte_carlo_nba import usage_bonus_stat_units\n')
            stop=current_renderer.index('    # Hit rates for each Sportsbet line',start)
            source=replace_once(source,'    # Hit rates for each Sportsbet line\n',current_renderer[start:stop]+'    # Hit rates for each Sportsbet line\n')
            mc=(code/REL/'monte_carlo_nba.py').read_text()
            mc=replace_once(mc,'def compute_context_factors(',mc_helper+'def compute_context_factors(')
            (code/REL/'monte_carlo_nba.py').write_text(mc)
        if flags['team_pace']:
            source=replace_once(source,'            team_pace=None, l10=data_for_hr, min_avg=card.get("min_avg", 0),',
                                '            team_pace=(team_stats or {}).get(team_abbr, {}).get("PACE"), l10=data_for_hr, min_avg=card.get("min_avg", 0),')
        if flags['blowout']:
            source=replace_once(source,'                "adj_line": la.get("adj_line", ""),',
                                '                "adj_line": la.get("adj_line", ""),\n                "adj_breakdown": dict(la.get("adj_breakdown") or {}),')
        (code/REL/'generate_nba_reports.py').write_text(source)
        protocol['sources'][name]={str(path.relative_to(code)):sha(path) for path in code.rglob('*.py')}
    (experiment/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','WC_TELEGRAM_DISABLE':'1','WC_DISABLE_POST_SUCCESS_DEPLOY':'1',
         'NBA_WC_MODEL_DIR':str(model),'TMPDIR':str(args.root),'NBA_WC_PROB_LAYER':'1','NBA_HYBRID_ML_ADJUST_ENABLED':'0'}
    def run_arm(name):
        code=experiment/name/'code';output=experiment/name/'reports';output.mkdir()
        rows=[]
        for case in cases:
            for key in ('game','odds'):
                if sha(Path(case[key]))!=case[key+'_sha256']:raise ValueError('input changed')
            report=output/(case['case_id']+'.md')
            try:
                run=subprocess.run([sys.executable,str(code/REL/'generate_nba_reports.py'),'--sportsbet',case['odds'],
                    '--extractor',case['game'],'--output',str(report)],env=env,capture_output=True,text=True,timeout=180)
                row={'case_id':case['case_id'],'exit_code':run.returncode}
                sidecar=Path(str(report)+'.market_legs.json')
                if run.returncode or not sidecar.exists():row['error_tail']=(run.stderr+run.stdout)[-1600:]
                else:
                    data=json.loads(sidecar.read_text());row.update(legs=len(data['legs']),combos=len(data['combos']),sidecar_sha256=sha(sidecar))
            except subprocess.TimeoutExpired:row={'case_id':case['case_id'],'exit_code':124,'error_tail':'timeout'}
            rows.append(row)
            (experiment/name/'capture_summary.json').write_text(json.dumps({'state':'running','results':rows},indent=2)+'\n')
            print(json.dumps({'arm':name,**row}),flush=True)
        result={'state':'complete','results':rows}
        (experiment/name/'capture_summary.json').write_text(json.dumps(result,indent=2)+'\n')
        return name,result
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(run_arm,name) for name in arms]):
            name,result=future.result();print(json.dumps({'arm_complete':name,'cases':len(result['results'])}),flush=True)
    if model_hashes!={name:sha(model/name) for name in model_hashes}:raise ValueError('model artifact changed during replay')
    (experiment/'completed.json').write_text(json.dumps({'state':'complete','protocol_sha256':sha(experiment/'protocol.json')},indent=2)+'\n')


if __name__=='__main__':main()
