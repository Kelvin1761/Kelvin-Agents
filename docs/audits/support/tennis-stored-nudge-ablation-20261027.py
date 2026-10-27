"""Dev-only ablation of recorded components, never rebuilt historical features."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import sqlite3
import numpy as np

NAMES=('serve_return_edge','recent_form_edge','opponent_rank_bucket_edge','tournament_level_edge',
       'round_performance_edge','big_match_edge','pressure_edge','head_to_head_edge','fatigue_edge')
ARMS=('all_off',)+NAMES
SEED=20260826
TRIALS=4000


def probability(logit):
    return min(.98,max(.02,1/(1+math.exp(-max(-700,min(700,logit))))))


def variants(model):
    base=float(model['elo_base_logit']);stored=float(model['total_nudge_logit'])
    parts={p['name']:p for p in model['components']}
    if len(parts)!=len(model['components']):raise ValueError('duplicate components')
    if not all(name in parts for name in (*NAMES,'surface_elo_edge','overall_elo_edge')):
        raise ValueError('missing components')
    if not any(parts[k].get('active') is True for k in ('surface_elo_edge','overall_elo_edge')):
        raise ValueError('no active Elo')
    terms={}
    for name in NAMES:
        p=parts[name]
        if not isinstance(p.get('active'),bool):raise ValueError('activity not recorded')
        w,q=float(p['weight']),float(p['probability'])
        if not math.isfinite(w) or not math.isfinite(q) or w<0 or not 0<=q<=1:raise ValueError('invalid component')
        terms[name]=w*(q-.5) if p['active'] else 0.
    raw=sum(terms.values());capped=max(-1.2,min(1.2,raw))
    if not all(math.isfinite(v) for v in (base,stored)) or abs(capped-stored)>1e-6:
        raise ValueError('nudge reconstruction mismatch')
    return {'baseline':probability(base+capped),'all_off':probability(base),
            **{k:probability(base+max(-1.2,min(1.2,raw-terms[k]))) for k in NAMES}}


def priced_variants(pricing):
    ps=variants(pricing['model'])
    side=pricing['selection_side']
    if side not in ('player_a','player_b'):raise ValueError('selection side not recorded')
    if side=='player_b':ps={k:1-v for k,v in ps.items()}
    discount=float(pricing['segment_risk_discount'])
    market=float(pricing['no_vig_market_probability'])
    if not math.isfinite(discount) or not 0<=discount<=1 or not math.isfinite(market) or not 0<market<1:
        raise ValueError('invalid recorded segment risk')
    return {k:market+(v-market)*(1-discount) for k,v in ps.items()}


def bootstrap_columns(matrix):
    data=np.asarray(matrix,dtype=float);n=len(data);rng=random.Random(SEED)
    if not n:return []
    samples=[]
    for _ in range(TRIALS):
        indices=[rng.randrange(n) for _ in range(n)]
        samples.append(data[indices].mean(axis=0))
    samples=np.asarray(samples);sorted_samples=np.sort(samples,axis=0)
    results=[]
    for j,value in enumerate(data.mean(axis=0)):
        p=min(1.,2*min((1+int(np.sum(samples[:,j]<=0)))/(TRIALS+1),(1+int(np.sum(samples[:,j]>=0)))/(TRIALS+1)))
        results.append({'mean':float(value),'ci95':[float(sorted_samples[int(.025*TRIALS),j]),float(sorted_samples[int(.975*TRIALS)-1,j])],
                        'bootstrap_two_sided_p':p})
    return results


def holm(ps):
    order=sorted(range(len(ps)),key=lambda i:ps[i]);out=[0.]*len(ps);previous=0.
    for rank,i in enumerate(order):previous=max(previous,min(1.,ps[i]*(len(ps)-rank)));out[i]=previous
    return out


def loss(p,y):
    return -y*math.log(max(1e-9,p))-(1-y)*math.log(max(1e-9,1-p))


def run(conn,source):
    counts=Counter();rows=[]
    for r in source['paired_rows']:
        counts['eligible_from_fixed_study']+=1
        p=conn.execute('SELECT * FROM predictions WHERE id=?',(r['prediction_id'],)).fetchone()
        try:
            pricing=json.loads(p['pricing_json']).get('pricing') or {}
            ps=priced_variants(pricing)
        except (KeyError,TypeError,ValueError) as e:
            counts['excluded_'+str(e)]+=1;continue
        if abs(ps['baseline']-r['model'])>1e-6:
            counts['excluded_shipped_probability_mismatch']+=1;continue
        rows.append({**r,'probabilities':ps})
    counts['faithful_same_subset']=len(rows)
    if not rows:return {'counts':dict(counts),'verdict':'NO FAITHFUL CORPUS','promotion_eligible':False}
    matrix=[]
    for r in rows:
        ps=r['probabilities'];y=r['won'];base=ps['baseline'];pnl=(r['odds']-1) if y else -1.
        base_pnl=pnl if base*r['odds']>1 else 0.
        matrix.append([loss(ps[a],y)-loss(base,y) for a in ARMS]
                      +[(ps[a]-y)**2-(base-y)**2 for a in ARMS]
                      +[(pnl if ps[a]*r['odds']>1 else 0.)-base_pnl for a in ARMS])
    stats=bootstrap_columns(matrix);adjusted=holm([stats[i]['bootstrap_two_sided_p'] for i in range(len(ARMS))])
    def summary(key):
        pnl=[r['odds']-1 if r['won'] else -1 for r in rows if r['probabilities'][key]*r['odds']>1]
        return {'bets':len(pnl),'pnl_units':sum(pnl),'roi':sum(pnl)/len(pnl) if pnl else None,
                'logloss':sum(loss(r['probabilities'][key],r['won']) for r in rows)/len(rows),
                'brier':sum((r['probabilities'][key]-r['won'])**2 for r in rows)/len(rows)}
    arms={}
    for i,a in enumerate(ARMS):
        tiers={}
        for tour in ('ATP','WTA','UNKNOWN'):
            group=[r for r in rows if (r['tour'] if r['tour'] in ('ATP','WTA') else 'UNKNOWN')==tour]
            tiers[tour]={'n':len(group),'ll_delta':sum(loss(r['probabilities'][a],r['won'])-loss(r['probabilities']['baseline'],r['won']) for r in group)/len(group) if group else None}
        arms[a]={'summary':summary(a),'ll_delta':stats[i],'ll_holm_p':adjusted[i],
                 'brier_delta':stats[len(ARMS)+i],'paired_pnl_delta_per_eligible_match':stats[2*len(ARMS)+i],
                 'tour_descriptive':tiers}
    return {'counts':dict(counts),'baseline':summary('baseline'),
            'market':{'logloss':sum(loss(r['market'],r['won']) for r in rows)/len(rows),
                      'brier':sum((r['market']-r['won'])**2 for r in rows)/len(rows)},
            'arms':arms,'method':{'seed':SEED,'trials':TRIALS,'unit':'match','fidelity_tolerance':1e-6,'holm_family':'10 LL ablations','parity':'recorded raw combiner, side and segment risk' },
            'promotion_eligible':False,'qualification':'All outcomes previously inspected: dev-only; no untouched holdout, CLV or live profit claim.',
            'verdict':'RESEARCH ONLY: decide whether all-off warrants a frozen prospective candidate, never select the best single ablation',
            'row_ids':[r['match_id'] for r in rows]}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',required=True);p.add_argument('--source-results',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    db=Path(a.db).resolve();source=json.loads(Path(a.source_results).read_text());sha=hashlib.sha256(db.read_bytes()).hexdigest()
    assert source['dataset_sha256']==sha
    c=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    try:result=run(c,source)
    finally:c.close()
    result['dataset_sha256']=sha;result['implementation_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    Path(a.output).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='row_ids'},indent=2))


if __name__=='__main__':main()
