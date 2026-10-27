"""Fixed-policy economic diagnostic; no fitting, staking or production writes."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import random
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tennis-wong-choi/src'))
from tennis_wc.evaluation.match_corpus import prematch_outcomes,earliest_match_odds
from tennis_wc.evaluation.corpus import classify_point_in_time,POINT_IN_TIME

SEED=20260826
TRIALS=4000
ODDS_CEILING=1.6
SPLIT='2026-07-15'
MIN_SAMPLE=600
MAX_PRICE_AGE_SECONDS=600  # Versioned config default, not chosen from outcomes.


def instant(value):
    try:
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d if d.tzinfo is not None and d.utcoffset() is not None else None
    except (ValueError,TypeError):
        return None


def load_rows(conn):
    forecasts=prematch_outcomes(conn)
    opening=earliest_match_odds(conn)
    predictions={r['id']:dict(r) for r in conn.execute('SELECT * FROM predictions')}
    matches={r['id']:dict(r) for r in conn.execute('SELECT * FROM matches')}
    closes=defaultdict(list)
    for r in conn.execute("SELECT * FROM odds_snapshots WHERE market='match_winner'"):
        closes[r['match_id']].append(dict(r))
    counts=Counter(canonical_agreed_forecasts=len(forecasts));rows=[]
    for f in forecasts:
        m=matches[f['match_id']];p=predictions[f['prediction_id']];o=opening.get(f['match_id'])
        reason=None
        if m.get('fixture_status')=='DISPUTED':reason='disputed_fixture'
        elif m['source_provider']=='mock':reason='mock_fixture'
        elif classify_point_in_time(p['created_at'],f['start_time_utc'])!=POINT_IN_TIME:reason='forecast_clock_unverifiable'
        elif o is None:reason='opening_unverifiable_or_post_start'
        elif o['source_provider']=='mock' or o['market']!='match_winner':reason='unsupported_opening'
        elif classify_point_in_time(o['fetched_at'],f['start_time_utc'])!=POINT_IN_TIME:reason='opening_fetch_clock_unverifiable'
        elif classify_point_in_time(o['created_at'],f['start_time_utc'])!=POINT_IN_TIME:reason='opening_ingested_after_start_or_unverifiable'
        if reason:counts[reason]+=1;continue
        if not all(math.isfinite(float(o[k])) and float(o[k])>1 for k in ('player_a_odds','player_b_odds')):
            counts['invalid_price']+=1;continue
        chosen_a=p['selection_player_id']==m['player_a_id']
        odds=float(o['player_a_odds'] if chosen_a else o['player_b_odds'])
        opponent=float(o['player_b_odds'] if chosen_a else o['player_a_odds'])
        model=float(f['model_p'] if chosen_a else 1-f['model_p'])
        written=instant(p['created_at']);observed=instant(o['created_at']);start=instant(f['start_time_utc'])
        age=(written-observed).total_seconds()
        same_stored_price=(p['current_market_odds'] is not None and math.isclose(float(p['current_market_odds']),odds,rel_tol=0,abs_tol=1e-9))
        timing_compatible=0<=age<=MAX_PRICE_AGE_SECONDS and same_stored_price
        payload=json.loads(p['pricing_json'] or '{}');fixture=payload.get('fixture_at_prediction')
        fixture_frozen=isinstance(fixture,dict) and all(fixture.get(k)==m[k] for k in ('player_a_id','player_b_id'))
        later=[q for q in closes[f['match_id']] if q['bookmaker']==o['bookmaker'] and q['source_provider']==o['source_provider']
               and instant(q['created_at']) is not None and written<instant(q['created_at'])<start
               and classify_point_in_time(q['fetched_at'],f['start_time_utc'])==POINT_IN_TIME
               and all(math.isfinite(float(q[k])) and float(q[k])>1 for k in ('player_a_odds','player_b_odds'))]
        closing=max(later,key=lambda q:(instant(q['created_at']),q['id'])) if later else None
        close_odds=float(closing['player_a_odds'] if chosen_a else closing['player_b_odds']) if closing else None
        rows.append({'match_id':f['match_id'],'date':f['match_date'],'start':f['start_time_utc'],
                     'tour':f['tour'],'odds':odds,'model':model,'market':(1/odds)/(1/odds+1/opponent),
                     'won':int(f['winner_player_id']==p['selection_player_id']),'decision':p['decision'],
                     'prediction_id':p['id'],'quote_id':o['id'],'quote_age_seconds':age,
                     'execution_timing_compatible':timing_compatible,'fixture_frozen':fixture_frozen,
                     'later_quote_id':closing['id'] if closing else None,
                     'same_book_movement':odds/close_odds-1 if closing else None})
    counts['eligible_unique_matches']=len(rows)
    assert len(rows)==len({r['match_id'] for r in rows})
    rows.sort(key=lambda r:(instant(r['start']),r['match_id']))
    return rows,dict(counts)


def interval(values):
    if not values:return {'n':0,'mean':None,'ci95':None}
    n=len(values);rng=random.Random(SEED)
    means=sorted(sum(rng.choice(values) for _ in range(n))/n for _ in range(TRIALS))
    return {'n':n,'mean':sum(values)/n,'ci95':[means[int(TRIALS*.025)],means[int(TRIALS*.975)-1]]}


def scores(rows):
    if not rows:return {'n':0}
    def ll(p,y):
        p=min(1-1e-9,max(1e-9,p));return -y*math.log(p)-(1-y)*math.log(1-p)
    losses={k:[ll(r[k],r['won']) for r in rows] for k in ('model','market')}
    briers={k:[(r[k]-r['won'])**2 for r in rows] for k in ('model','market')}
    return {'n':len(rows),'model_logloss':sum(losses['model'])/len(rows),'market_logloss':sum(losses['market'])/len(rows),
            'model_brier':sum(briers['model'])/len(rows),'market_brier':sum(briers['market'])/len(rows),
            'paired_ll_model_minus_market':interval([a-b for a,b in zip(losses['model'],losses['market'])]),
            'paired_brier_model_minus_market':interval([a-b for a,b in zip(briers['model'],briers['market'])])}


def policies(rows):
    baseline=[];candidate=[];diff=[]
    for r in rows:
        pnl=r['odds']-1 if r['won'] else -1
        b=pnl if r['decision']=='BET' else 0
        c=b if r['odds']<=ODDS_CEILING else 0
        if r['decision']=='BET':baseline.append((r,b))
        if r['decision']=='BET' and r['odds']<=ODDS_CEILING:candidate.append((r,c))
        diff.append(c-b)
    def book(entries):
        values=[v for _,v in entries];running=peak=0.;dd=0.
        for value in values:running+=value;peak=max(peak,running);dd=min(dd,running-peak)
        return {'bets':len(values),'pnl_units':sum(values),'roi':interval(values),
                'drawdown_by_start_order':dd,'timing_compatible_bets':sum(r['execution_timing_compatible'] for r,_ in entries),
                'frozen_fixture_bets':sum(r['fixture_frozen'] for r,_ in entries),
                'later_prestart_quote_bets':sum(r['later_quote_id'] is not None for r,_ in entries)}
    return {'archived_BET_baseline':book(baseline),'BET_and_short_candidate':book(candidate),
            'paired_pnl_delta_per_eligible_match':interval(diff)}


def run(conn):
    rows,counts=load_rows(conn);short=[r for r in rows if r['odds']<=ODDS_CEILING]
    short_scores=scores(short)
    report={'method':{'odds_ceiling':ODDS_CEILING,'split':SPLIT,'minimum_sample':MIN_SAMPLE,'seed':SEED,'trials':TRIALS,'unit':'match'},
            'eligibility_counts':counts,'baseline_all_prices':scores(rows),'short_favourite':short_scores,
            'original_walk_forward':{name:scores([r for r in short if (r['date']<SPLIT)==early]) for name,early in [('before',True),('after',False)]},
            'post_original_registration_descriptive':scores([r for r in short if r['date']>'2026-08-26']),
            'paper_policy_comparison':policies(rows),'execution_compatible_policy_diagnostic':policies([r for r in rows if r['execution_timing_compatible']]),
            'evidence_coverage':{'timing_compatible':sum(r['execution_timing_compatible'] for r in rows),'frozen_fixture':sum(r['fixture_frozen'] for r in rows),
                                 'later_prestart_quote':sum(r['later_quote_id'] is not None for r in rows)},
            'promotion_eligible':False,'qualification':'Legacy diagnostic, not post-repair untouched validation or live betting profit.',
            'limitations':['No independent bookmaker reference; same-book movement is not a sharp-price edge.',
                           'Opening odds may not have been obtainable at forecast time; timing-compatible subset is reported separately.',
                           'Legacy fixture identity and changing engine versions remain unverified; no price orientation certification.',
                           'Drawdown uses match-start order, not verified cash settlement order.'],
            'paired_rows':rows}
    report['research_verdict']=('NEEDS MORE TESTING: sample below frozen 600 floor' if len(short)<MIN_SAMPLE
                                else 'DIAGNOSTIC ONLY: evaluate paired intervals and prospective evidence; no promotion')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    db=Path(a.db).resolve();c=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    try:report=run(c)
    finally:c.close()
    report['dataset']=str(db);report['dataset_sha256']=hashlib.sha256(db.read_bytes()).hexdigest()
    report['implementation_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    Path(a.output).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('paired_rows','limitations')},indent=2))


if __name__=='__main__':main()
