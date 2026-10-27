"""Fixed-book diagnostic; archived prices are NOT execution-time evidence."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, date, timedelta
import json
import math
from pathlib import Path
import unicodedata
import openpyxl
import numpy as np
import score_model as base

ROOT = Path(__file__).resolve().parent


def normalized(text):
    s = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()
    return ''.join(c for c in s if c.isalnum())


def source_name(text):
    words = text.split()
    if len(words) < 2:
        return None
    return normalized(''.join(words[1:])) + words[0][0].lower()


def sheet_name(text):
    words = str(text).split()
    if len(words) < 2:
        return None
    return normalized(''.join(words[:-1])) + words[-1][0].lower()


def run(predictions, corpus, cache, out):
    pred = json.loads(Path(predictions).read_text())
    source = json.loads(Path(corpus).read_text())
    ids = defaultdict(set)
    for r in source['rows']:
        ids[(r['tour'], source_name(r['winner_name']))].add(r['winner'])
        ids[(r['tour'], source_name(r['loser_name']))].add(r['loser'])
    index = defaultdict(list)
    for i, p in enumerate(pred):
        index[(p['tour'], p['winner'], p['loser'])].append((i,p))
    matches = defaultdict(list)
    counts = Counter()
    files = []
    for tour in ('ATP','WTA'):
        for year in (2023,2024):
            path = Path(cache) / f'tennisdata_{tour.lower()}_{year}.xlsx'
            files.append({'path': str(path), 'sha256':base.digest(path)})
            wb = openpyxl.load_workbook(path,read_only=True,data_only=True)
            rows=wb.active.iter_rows(values_only=True)
            header=next(rows)
            for row_number, values in enumerate(rows,start=2):
                counts['raw_sheet_rows']+=1
                row=dict(zip(header,values))
                if str(row.get('Comment','')).lower()!='completed':
                    counts['incomplete']+=1; continue
                try:
                    ow,ol=float(row['B365W']),float(row['B365L'])
                    if not all(math.isfinite(x) and 1<x<1000 for x in (ow,ol)):
                        raise ValueError('odds')
                    day=row['Date'].date() if isinstance(row['Date'],datetime) else date.fromisoformat(str(row['Date'])[:10])
                    if day.year != year: raise ValueError('date')
                    wids=ids[(tour,sheet_name(row['Winner']))]; lids=ids[(tour,sheet_name(row['Loser']))]
                    if len(wids)!=1 or len(lids)!=1:
                        counts['ambiguous_or_missing_name']+=1; continue
                    winner,loser=next(iter(wids)),next(iter(lids))
                    wg=lg=0
                    for s in range(1,6):
                        a,b=row.get('W'+str(s)),row.get('L'+str(s))
                        if a is not None and b is not None:
                            wg+=int(a);lg+=int(b)
                    candidates=[]
                    for i,p in index[(tour,winner,loser)]:
                        start=date.fromisoformat(p['date'])
                        if (start<=day<start+timedelta(days=21) and p['surface'].lower()==str(row['Surface']).lower()
                            and (p['winner_games'],p['loser_games'])==(wg,lg)):
                            candidates.append((i,p))
                    if len(candidates)!=1:
                        counts['no_unique_match']+=1;continue
                    i,p=candidates[0]
                    matches[i].append(dict(p, winner_odds=ow, loser_odds=ol,
                                           sheet_date=day.isoformat(), sheet_file=str(path), sheet_row=row_number))
                except (ValueError,TypeError,KeyError):
                    counts['invalid_price_or_row']+=1
            wb.close()
    joined=[v[0] for v in matches.values() if len(v)==1]
    counts['reused_prediction_rows_rejected']=sum(len(v) for v in matches.values() if len(v)!=1)
    counts['joined']=len(joined)
    if not joined: raise ValueError('no joined prices')
    yt=np.array([p['y'] for p in joined])
    vectors={}; probs={}; profit={}; metrics={}
    for arm in ('baseline','binary','rank','market'):
        ps=[]; pnl=[]; nb=0
        for p in joined:
            ow,ol=p['winner_odds'],p['loser_odds']
            nv=(1/ow)/(1/ow+1/ol)
            q=(nv if p['y'] else 1-nv) if arm=='market' else p[arm+'_p']
            ps.append(q)
            if arm=='market':continue
            o_a,o_b=(ow,ol) if p['y'] else (ol,ow)
            ev_a,ev_b=q*o_a-1,(1-q)*o_b-1
            if max(ev_a,ev_b)<=0:
                pnl.append(0.);continue
            pick_a=ev_a>=ev_b; won=bool(p['y'])==pick_a
            odds=o_a if pick_a else o_b
            pnl.append(odds-1 if won else -1.)
            nb+=1
        probs[arm]=np.array(ps);vectors[arm]=base.losses(probs[arm],yt)
        metrics[arm]={'n':len(joined),'log_loss':float(vectors[arm][0].mean()),'brier':float(vectors[arm][1].mean())}
        if arm!='market':
            profit[arm]=np.array(pnl)
            metrics[arm].update(bets=nb,hypothetical_pnl=float(sum(pnl)),hypothetical_roi=float(sum(pnl)/nb) if nb else None)
    result={'protocol_sha256':base.digest(ROOT/'market_protocol.json'),'code_sha256':base.digest(__file__),
            'predictions_sha256':base.digest(predictions),'source_files':files,'coverage':dict(counts),
            'metrics':metrics,'comparisons':{},'status':'DESCRIPTIVE ONLY: price observation/execution times unverified; not an executable ROI or CLV claim'}
    for ref in ('baseline','binary','market'):
        result['comparisons']['rank_vs_'+ref]={}
        for i,m in enumerate(('log_loss','brier')):
            d=vectors['rank'][i]-vectors[ref][i]
            result['comparisons']['rank_vs_'+ref][m]={'delta':float(d.mean()),'ci95':base.paired_ci(d)}
        if ref!='market':
            d=profit['rank']-profit[ref]
            result['comparisons']['rank_vs_'+ref]['profit_difference_per_match']={'delta':float(d.mean()),'ci95':base.paired_ci(d)}
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'joined.json').write_text(json.dumps(joined,separators=(',',':')))
    (out/'summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--predictions',required=True);p.add_argument('--corpus',required=True);p.add_argument('--cache',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();run(a.predictions,a.corpus,a.cache,a.out)
