"""Paired fixed-corpus context diagnostics; never selects or fits an arm."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPO=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(REPO/'.agents/skills/nba'))
from nba_identity import player_name_key
from nba_schedule import canonical_game_tag


def key(leg):
    stats={'pts':'PTS','reb':'REB','ast':'AST','fg3m':'FG3M'}
    return player_name_key(leg['player']),stats[leg['market']],float(leg['line'])


def paired(base,candidate,labels,dates,field):
    changes=[];y=[];before=[];after=[];days=[];missing=0
    for identity,old in base.items():
        new=candidate[identity];left,right=old.get(field),new.get(field)
        if left is not None and right is not None:changes.append(abs(left-right))
        if identity not in labels:continue
        if left is None or right is None:missing+=1;continue
        if not all(np.isfinite(value) and 0<=value<=1 for value in (left,right)):raise ValueError('invalid probability')
        y.append(labels[identity]);before.append(left);after.append(right);days.append(dates[identity[0]])
    target=np.array(y);before=np.array(before);after=np.array(after);days=np.array(days)
    if not y:return {'changed_rows':sum(value>1e-12 for value in changes),'labeled_rows':0,'missing':missing}
    delta=(after-target)**2-(before-target)**2
    unique=sorted(set(days));groups=[np.flatnonzero(days==day) for day in unique];rng=np.random.default_rng(20261023)
    draws=[np.concatenate([groups[index] for index in rng.integers(0,len(groups),size=len(groups))]) for _ in range(2000)]
    return {'changed_rows':sum(value>1e-12 for value in changes),'labeled_rows':len(y),'missing':missing,
            'max_abs_probability_change':max(changes,default=0),'baseline_brier':float(np.mean((before-target)**2)),
            'candidate_brier':float(np.mean((after-target)**2)),'paired_brier_delta':float(delta.mean()),
            'paired_date_bootstrap_95':np.percentile([delta[index].mean() for index in draws],[2.5,97.5]).tolist(),
            'date_clusters':len(unique)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.root;exp=root/'context_ablation_v1';protocol=json.loads((exp/'protocol.json').read_text())
    manifest=json.loads((root/'strict_priced_manifest.json').read_text());cases=manifest['cases'];dates={c['case_id']:c['us_game_date'] for c in cases}
    by_source={c['game']:c['case_id'] for c in cases}
    unique_games={c['us_game_date']+':'+canonical_game_tag(c['case_id'].split('__')[-1]) for c in cases}
    frame=pd.read_csv(root/'verified_dataset_v2/dataset.csv');labels={}
    for _,row in frame[frame.hit.notna()].iterrows():
        labels[(by_source[row.source_game_path],row.player_key,row.stat_category,float(row.line_value))]=int(row.hit)
    def read(directory):
        all_legs={};combos=[]
        for case in cases:
            data=json.loads((directory/(case['case_id']+'.md.market_legs.json')).read_text())
            for leg in data['legs']:
                identity=(case['case_id'],*key(leg))
                if identity in all_legs:raise ValueError('duplicate evaluation leg')
                all_legs[identity]=leg
            combos.extend((case['case_id'],c['combo_id']) for c in data['combos'])
        return all_legs,combos
    base,base_combos=read(root/'baseline-0bffbeb6');result={}
    all_arms={}
    for name in protocol['arms']:
        summary=json.loads((exp/name/'capture_summary.json').read_text())
        if summary['state']!='complete' or any(row['exit_code'] for row in summary['results']):raise ValueError('arm not successfully complete: '+name)
        legs,combos=read(exp/name/'reports')
        if set(legs)!=set(base):raise ValueError('arm population changed')
        all_arms[name]=legs
        result[name]={'cases':len(cases),'legs':len(legs),'formal_prequote_combos':len(combos),
                      'combo_membership_changes':len(set(combos)^set(base_combos)),
                      'probabilities':{field:paired(base,legs,labels,dates,field) for field in ('p_final','p_hit_rate_10f','p_monte_carlo')}}
    marginal={name:paired(all_arms['minus_'+name],all_arms['full'],labels,dates,'p_monte_carlo') for name in ('injury_status','mc_usage','team_pace','blowout')}
    out={'status':'complete','base_commit':protocol['base_commit'],'cases':len(cases),'unique_games':len(unique_games),'legs':len(base),'labeled_legs':len(labels),
         'label_identities_absent_from_renderer':[list(identity) for identity in labels if identity not in base],
         'baseline_formal_prequote_combos':len(base_combos),'arms':result,'full_minus_feature_mc':marginal,
         'interpretation':'Fixed historical diagnostics only. C coefficients unchanged; no new model or parameter is selected here. SGM bookmaker quotes are outside this experiment.'}
    args.output.write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'cases':len(cases),'legs':len(base),'arms':{name:data['probabilities']['p_monte_carlo'] for name,data in result.items()}},indent=2))


if __name__=='__main__':main()
