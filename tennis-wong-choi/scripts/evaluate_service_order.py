#!/usr/bin/env python3
"""EXP-20261026-05: legacy history, fixed prices, one kernel correction."""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

import evaluate_wta_history as study


def legacy_profiles(conn, overlay, a, b, day, surface, start):
    pair=[study.baseline_profile(conn,pid,day,surface,start) for pid in (a,b)]
    return {arm:pair for arm in study.ARMS}


def compare(baseline, candidate):
    def index(rows):
        return {tuple(row['contract']):row for row in rows}
    old,new=index(baseline),index(candidate)
    if old.keys()!=new.keys():
        raise ValueError('kernel changed coverage; investigate instead of dropping unmatched contracts')
    paired=[]
    for key,b in old.items():
        c=new[key]
        if any(b[field]!=c[field] for field in ('quote_id','won','market','odds')):
            raise ValueError('baseline and candidate do not share immutable quote/outcome')
        paired.append({**b,'losses':{'baseline':b['losses']['A0'],'candidate':c['losses']['A0'],
                                   'market':b['losses']['market']},
                       'probabilities':{'baseline':b['probabilities']['A0'],
                                        'candidate':c['probabilities']['A0']}})
    arms=('baseline','candidate','market')
    def summary(rows):
        return study.paired_summary(rows,arms,'baseline')
    output={'all':summary(paired),'vs_market':study.paired_summary(paired,arms,'market'),
            'tour':{t:summary([r for r in paired if r['tour']==t]) for t in sorted({r['tour'] for r in paired})},
            'family':{f:summary([r for r in paired if r['family']==f]) for f in sorted({r['family'] for r in paired})},
            'surface':{s:summary([r for r in paired if (r['surface'] or 'unknown')==s])
                       for s in sorted({r['surface'] or 'unknown' for r in paired})},
            'secondary':{}}
    for name in ('baseline','candidate'):
        selected=[r for r in paired if r['probabilities'][name]-r['market']>=.04]
        output['secondary'][name]={'n':len(selected),'flat_profit':sum(r['odds']*r['won']-1 for r in selected)}
    output['by_date']=dict(Counter(r['date'] for r in paired))
    return output


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--candidate',type=Path)
    parser.add_argument('--baseline',type=Path)
    args=parser.parse_args()
    if bool(args.candidate)!=bool(args.baseline):
        parser.error('--candidate and --baseline must be supplied together')
    if args.candidate:
        spec=importlib.util.spec_from_file_location('candidate_match_simulator',args.candidate)
        module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module
        spec.loader.exec_module(module)
        study.simulate_match=module.simulate_match
        study.distribution.cache_clear()
    conn=sqlite3.connect(f'file:{args.db}?mode=ro',uri=True)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    conn.execute('PRAGMA cache_size=-65536')
    result=study.prop_study(conn,None,all_tours=True,profile_provider=legacy_profiles,records_only=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False)+'\n')
    print(json.dumps({'output':str(args.output),'coverage':result['coverage'],'records':len(result['records'])}),flush=True)
    if args.baseline:
        baseline=json.loads(args.baseline.read_text())
        comparison=compare(baseline['records'],result['records'])
        target=args.output.with_name(args.output.stem+'_comparison.json')
        target.write_text(json.dumps(comparison,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
        print(json.dumps({'comparison':str(target),'all':comparison['all']}),flush=True)


if __name__=='__main__':
    main()
