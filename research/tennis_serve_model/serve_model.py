"""Offline EXP-20261027-09; reconstructed clocks stay FLAG, never live pricing."""
import argparse
from collections import Counter, defaultdict
import heapq
import json
import math
from pathlib import Path
import sqlite3
import numpy as np
import score_model as base

ROOT=Path(__file__).resolve().parent
PROTOCOL=json.loads((ROOT/'serve_protocol.json').read_text())
ARMS={'binary':[0],'rank':[0,1],'raw':[0,1,2,3], 'adjusted':[0,1,4,5],
      'serve_only_ablation':[0,1,4],'return_only_ablation':[0,1,5]}


def point_counts(raw):
    values=[]
    for side in ('w','l'):
        try:
            text=[raw[side+'_'+col] for col in ('svpt','1stIn','1stWon','2ndWon')]
            if any(not str(v).isdigit() for v in text):return None
            n,i,w,z=map(int,text)
        except (ValueError,TypeError,KeyError):return None
        if not(n>0 and 0<=w<=i<=n and 0<=z<=n-i):return None
        values.append((w+z,n))
    return values


def augment(db, data, out):
    payload=json.loads(Path(data).read_text())
    c=sqlite3.connect('file:'+str(Path(db).resolve())+'?mode=ro',uri=True)
    raw_rows={}
    for rid in base.PROTOCOL['raw_response_ids']:
        params,text=c.execute('SELECT request_params_json,response_json FROM raw_api_responses WHERE id=?',(rid,)).fetchone()
        tour=json.loads(params)['tour']
        for raw in json.loads(text):
            key='|'.join((tour,str(raw['tourney_id']),str(raw['match_num'])))
            if key in raw_rows and raw_rows[key]!=raw:raise ValueError('conflicting source key')
            raw_rows[key]=raw
    c.close();coverage=Counter()
    for r in payload['rows']:
        raw=raw_rows[r['key']]
        if (int(raw['winner_id']),int(raw['loser_id']),str(raw['tourney_date']))!=(r['winner'],r['loser'],r['date'].replace('-','')):
            raise ValueError('source identity mismatch')
        r['point_counts']=point_counts(raw)
        coverage[r['tour']+('_valid' if r['point_counts'] else '_missing_invalid')]+=1
    payload['point_coverage']=dict(coverage)
    payload['serve_protocol_sha256']=base.digest(ROOT/'serve_protocol.json')
    Path(out).write_text(json.dumps(payload,separators=(',',':')))
    print(json.dumps({'coverage':dict(coverage),'dataset_sha256':base.digest(out)}))


class PointStrength:
    def __init__(self, mu, adjusted):
        self.mu=mu; self.adjusted=adjusted
        self.state=defaultdict(float); self.count=Counter()

    def get(self, player, surface, component):
        return self.state.get((player,surface,component),self.state[(player,'',component)])

    def difference(self,a,b,surface,component):
        return .35*(self.get(a,'',component)-self.get(b,'',component))+.65*(self.get(a,surface,component)-self.get(b,surface,component))

    def update(self, a,b,surface,counts):
        # Freeze BOTH service dyads and both scopes before updating any state.
        updates=[]
        for scope in ('',surface):
            for server,returner,(won,total) in ((a,b,counts[0]),(b,a,counts[1])):
                s=self.get(server,scope,'S'); r=self.get(returner,scope,'R')
                mu=self.mu[server[0]]
                ps=float(base.sigmoid(mu+s-(r if self.adjusted else 0)))
                pr=ps if self.adjusted else float(base.sigmoid(mu-r))
                observed=won/total
                updates.extend([(server,scope,'S',s,observed-ps),(returner,scope,'R',r,pr-observed)])
        for player,scope,component,old,residual in updates:
            key=(player,scope,component)
            rate=120*math.log(10)/400/(self.count[key]+5)**.4
            self.state[key]=old+rate*residual
            self.count[key]+=1


def features(payload):
    rows=payload['rows']
    totals=defaultdict(lambda:[0,0])
    for r in rows:
        if r['available']<'2021-01-01' and r['point_counts']:
            for won,total in r['point_counts']:
                totals[r['tour']][0]+=won;totals[r['tour']][1]+=total
    mu={tour:math.log(won/(total-won)) for tour,(won,total) in totals.items()}
    if set(mu)!={'ATP','WTA'}:raise ValueError('missing warmup tour')
    original=base.make_features(rows)
    adjusted=PointStrength(mu,True); raw=PointStrength(mu,False)
    queue=[]; by_key={}
    for seq,r in enumerate(rows):
        while queue and queue[0][0]<r['date']:
            _,_,past=heapq.heappop(queue)
            if past['point_counts']:
                a,b=(past['tour'],past['winner']),(past['tour'],past['loser'])
                for model in (raw,adjusted):model.update(a,b,past['surface'],past['point_counts'])
        a,b=(r['tour'],min(r['winner'],r['loser'])),(r['tour'],max(r['winner'],r['loser']))
        f={}
        for name,model in (('raw',raw),('adjusted',adjusted)):
            for component in ('S','R'):
                f[name+'_'+component]=model.difference(a,b,r['surface'],component)
        f['point_history_both']=adjusted.count[(a,'','S')]>0 and adjusted.count[(b,'','S')]>0
        by_key[r['key']]=f
        heapq.heappush(queue,(r['available'],seq,r))
    return [dict(r,**by_key[r['key']]) for r in original],mu,dict(totals)


def matrix(rows):
    return np.array([[r['x_binary'],r['x_rank'],r['raw_S'],r['raw_R'],r['adjusted_S'],r['adjusted_R']] for r in rows])


def evaluate(rows,start,end,confirmation=False):
    train=[r for r in rows if r['date']>='2021-01-01' and r['available']<start]
    test=[r for r in rows if start<=r['date']<end]
    x,xt=matrix(train),matrix(test)
    y=np.array([r['y'] for r in train]);yt=np.array([r['y'] for r in test])
    arms={'rank':ARMS['rank'],'raw':ARMS['raw'],'adjusted':ARMS['adjusted']} if confirmation else ARMS
    beta={a:base.fit(x[:,ix],y) for a,ix in arms.items()}
    ps={a:base.sigmoid(xt[:,arms[a]]@b) for a,b in beta.items()}
    vectors={a:base.losses(p,yt) for a,p in ps.items()}
    result={'window':[start,end],'train_n':len(train),'test_n':len(test),
            'training_last_label_available':max(r['available'] for r in train),
            'point_history_both_n':sum(r['point_history_both'] for r in test),
            'coefficients':{a:b.tolist() for a,b in beta.items()},
            'metrics':{a:{'log_loss':float(v[0].mean()),'brier':float(v[1].mean())} for a,v in vectors.items()},
            'deltas':{},'cohorts':{},'calibration':{}}
    for control in arms:
        if control=='adjusted':continue
        result['deltas'][control]={}
        for i,m in enumerate(('log_loss','brier')):
            d=vectors['adjusted'][i]-vectors[control][i]
            result['deltas'][control][m]={'mean':float(d.mean())}
            if confirmation and control in ('raw','rank'):
                result['deltas'][control][m]['ci95']=base.paired_ci(d)
    for field in ('tour','surface','level','best_of','point_history_both'):
        groups={}
        for val in sorted({str(r[field]) for r in test}):
            ix=[i for i,r in enumerate(test) if str(r[field])==val]
            groups[val]={'n':len(ix),'metrics':{a:{'log_loss':float(v[0][ix].mean()),'brier':float(v[1][ix].mean())} for a,v in vectors.items()}}
        result['cohorts'][field]=groups
    for a,p in ps.items():
        bins=[]
        for lower in np.arange(0,1,.1):
            ix=(p>=lower)&(p<lower+.1)
            if ix.any():bins.append({'lo':float(lower),'n':int(ix.sum()),'pred':float(p[ix].mean()),'observed':float(yt[ix].mean())})
        result['calibration'][a]=bins
    predictions=[dict(r,**{a+'_p':float(ps[a][i]) for a in ps}) for i,r in enumerate(test)]
    return result,predictions


def run(data,out,confirmation=False):
    payload=json.loads(Path(data).read_text())
    if payload['serve_protocol_sha256']!=base.digest(ROOT/'serve_protocol.json'):raise ValueError('protocol mismatch')
    rows,mu,warm=features(payload); folds=[];predictions=[]
    for start,end in base.PROTOCOL['development_folds']:
        f,p=evaluate(rows,start,end);folds.append(f);predictions.extend(p)
    pass_folds=all(f['deltas'][c][m]['mean']<0 for f in folds for c in ('rank','raw') for m in ('log_loss','brier'))
    pass_ablation=all(sum(f['test_n']*f['deltas'][c][m]['mean'] for f in folds)<0 for c in ('serve_only_ablation','return_only_ablation') for m in ('log_loss','brier'))
    result={'experiment':PROTOCOL['experiment'],'base_commit':PROTOCOL['base_commit'],
            'protocol_sha256':base.digest(ROOT/'serve_protocol.json'),'dataset_sha256':base.digest(data),
            'code_sha256':base.digest(__file__),'base_code_sha256':base.digest(base.__file__),
            'point_coverage':payload['point_coverage'],'warmup_mu':mu,'warmup_counts':warm,
            'feature_n':len(rows),'development':folds,'development_pass':pass_folds and pass_ablation,
            'fold_guard_pass':pass_folds,'component_ablation_pass':pass_ablation,
            'confirmation_opened':False,'decision':'NEEDS MORE TESTING' if pass_folds and pass_ablation else 'REJECT',
            'leakage_status':'FLAG: historical clocks reconstructed, 2025 reused research data, no promotion'}
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'dev_predictions.json').write_text(json.dumps(predictions,separators=(',',':')))
    if confirmation:
        if not result['development_pass']:raise ValueError('confirmation locked: development failed')
        f,p=evaluate(rows,*base.PROTOCOL['confirmation'],confirmation=True)
        result.update(confirmation=f,confirmation_opened=True)
        significant=all(f['deltas'][c][m]['ci95'][1]<0 for c in ('rank','raw') for m in ('log_loss','brier'))
        tour_pass=all(g['metrics']['adjusted'][m]<=g['metrics'][c][m] for g in f['cohorts']['tour'].values() for c in ('rank','raw') for m in ('log_loss','brier'))
        result['research_confirmation_pass']=significant and tour_pass
        result['decision']='NEEDS FORWARD VALIDATION' if significant and tour_pass else 'REJECT'
        (out/'confirmation_predictions.json').write_text(json.dumps(p,separators=(',',':')))
    (out/'summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='development' and k!='confirmation'},indent=2))
    for f in folds:print(f['window'],f['metrics'],f['deltas'])


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('augment');a.add_argument('--db',required=True);a.add_argument('--data',required=True);a.add_argument('--out',required=True)
    r=sub.add_parser('run');r.add_argument('--data',required=True);r.add_argument('--out',required=True);r.add_argument('--confirmation',action='store_true')
    args=p.parse_args()
    if args.action=='augment':augment(args.db,args.data,args.out)
    else:run(args.data,args.out,args.confirmation)
