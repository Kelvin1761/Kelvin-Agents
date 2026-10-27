"""Reuse frozen EXP08 quote join/rule; explicit mapping, no price tuning."""
import argparse
import json
from pathlib import Path
import numpy as np
import score_model as base
import market_diagnostic as inherited

ROOT=Path(__file__).resolve().parent
ROLES={'baseline':'rank_control','binary':'raw','rank':'adjusted','market':'market'}


def profit(p,ow,ol,y):
    oa,ob=(ow,ol) if y else (ol,ow)
    ea,eb=p*oa-1,(1-p)*ob-1
    if max(ea,eb)<=0:return 0.,False
    pick=ea>=eb;won=bool(y)==pick
    return ((oa if pick else ob)-1 if won else -1.),True


def run(predictions,corpus,cache,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    rows=json.loads(Path(predictions).read_text())
    mapped=[dict(r,binary_control_p=r['binary_p'],baseline_p=r['rank_p'],binary_p=r['raw_p'],rank_p=r['adjusted_p']) for r in rows]
    mapped_path=out/'mapped_predictions.json';mapped_path.write_text(json.dumps(mapped,separators=(',',':')))
    inherited.run(mapped_path,corpus,cache,out/'inherited')
    result=json.loads((out/'inherited/summary.json').read_text())
    joined=json.loads((out/'inherited/joined.json').read_text())
    # Reproduce the pre-existing rank baseline, on EXACTLY the old population.
    if result['coverage']['joined']!=8240:raise ValueError('baseline population changed')
    if abs(result['metrics']['baseline']['log_loss']-.6212115661946416)>1e-10:raise ValueError('rank baseline differs')
    if abs(result['metrics']['baseline']['hypothetical_roi']-(-.1436997236720905))>1e-10:raise ValueError('rank profit baseline differs')
    result['metrics']={ROLES[a]:v for a,v in result['metrics'].items()}
    result['comparisons']={k.replace('rank_vs_baseline','adjusted_vs_rank_control').replace('rank_vs_binary','adjusted_vs_raw').replace('rank_vs_market','adjusted_vs_market'):v for k,v in result['comparisons'].items()}
    yt=np.array([r['y'] for r in joined])
    pb=np.array([r['binary_control_p'] for r in joined]);pa=np.array([r['rank_p'] for r in joined])
    lb,bb=base.losses(pb,yt);la,ba=base.losses(pa,yt)
    pnl_b=np.array([profit(r['binary_control_p'],r['winner_odds'],r['loser_odds'],r['y'])[0] for r in joined])
    pnl_a=np.array([profit(r['rank_p'],r['winner_odds'],r['loser_odds'],r['y'])[0] for r in joined])
    bets=sum(profit(r['binary_control_p'],r['winner_odds'],r['loser_odds'],r['y'])[1] for r in joined)
    result['metrics']['binary_control']={'n':len(joined),'log_loss':float(lb.mean()),'brier':float(bb.mean()),'bets':bets,'hypothetical_pnl':float(pnl_b.sum()),'hypothetical_roi':float(pnl_b.sum()/bets)}
    if abs(float(lb.mean())-.6259056651106578)>1e-10:raise ValueError('binary baseline differs')
    result['comparisons']['adjusted_vs_binary_control']={}
    for metric,d in [('log_loss',la-lb),('brier',ba-bb),('profit_difference_per_match',pnl_a-pnl_b)]:
        result['comparisons']['adjusted_vs_binary_control'][metric]={'delta':float(d.mean()),'ci95':base.paired_ci(d)}
    result['mapping']=dict(ROLES,binary_control_p='original fitted binary-only; retained before mapping')
    result['serve_protocol_sha256']=base.digest(ROOT/'serve_protocol.json')
    result['market_cohort_spec_sha256']=base.digest(ROOT/'market_cohort_spec.json')
    result['code_sha256']=base.digest(__file__)
    result['original_predictions_sha256']=base.digest(predictions)
    result['baseline_parity']='PASS: 8240 joined, prior rank LL and ROI exactly reproduced within 1e-10'
    result['cohorts']={}
    for r in joined:
        longer=max(r['winner_odds'],r['loser_odds'])
        r['odds_cohort']='max<=2' if longer<=2 else '2<max<=3' if longer<=3 else '3<max<=5' if longer<=5 else 'max>5'
    for field in ('tour','surface','level','odds_cohort'):
        groups={}
        for val in sorted({r[field] for r in joined}):
            group=[r for r in joined if r[field]==val];yt=np.array([r['y'] for r in group]);metrics={}
            for arm in ('baseline','binary','rank','market'):
                p=[];pnl=[];bets=0
                for r in group:
                    ow,ol=r['winner_odds'],r['loser_odds']
                    nv=(1/ow)/(1/ow+1/ol)
                    q=(nv if r['y'] else 1-nv) if arm=='market' else r[arm+'_p']
                    p.append(q)
                    if arm!='market':
                        v,b=profit(q,ow,ol,r['y']);pnl.append(v);bets+=b
                loss,brier=base.losses(np.array(p),yt)
                metrics[ROLES[arm]]={'log_loss':float(loss.mean()),'brier':float(brier.mean())}
                if arm!='market':metrics[ROLES[arm]].update(bets=bets,hypothetical_pnl=sum(pnl),hypothetical_roi=sum(pnl)/bets if bets else None)
            groups[val]={'n':len(group),'metrics':metrics}
        result['cohorts'][field]=groups
    result['promotion_decision']='REJECT: model development gate already failed; descriptive economics cannot rescue it'
    (out/'summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({'coverage':result['coverage'],'metrics':result['metrics'],'comparisons':result['comparisons']},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--predictions',required=True);p.add_argument('--corpus',required=True);p.add_argument('--cache',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();run(a.predictions,a.corpus,a.cache,a.out)
