#!/usr/bin/env python3
"""Fixed EXP-20261026-04 arms; read-only counterfactual source replay."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import replace
from functools import lru_cache
import json
import math
from pathlib import Path
import random
import sqlite3

from tennis_wc.database.result_consensus import conflicting_result_matches
from tennis_wc.features.serve_return import serve_return_profile
from tennis_wc.props.hold_model import estimate_hold, estimate_hold_fitted
from tennis_wc.props.match_simulator import simulate_match
from tennis_wc.research.wta_history import WtaHistoryOverlay, _stamp

ARMS = ("A0", "A1", "A2", "D0")


def binomial_losses(probability, successes, exposure):
    p = min(1-1e-9, max(1e-9, probability))
    return (successes*(1-p)**2+(exposure-successes)*p*p,
            -successes*math.log(p)-(exposure-successes)*math.log1p(-p))


def paired_summary(rows, arms=ARMS, reference="A0"):
    """Each row has cluster, exposure and per-arm loss sums. Resample matches."""
    if not rows:
        return {"observations": 0, "matches": 0}
    clusters = defaultdict(lambda: [0.0]+[0.0]*(len(arms)*2))
    reference_index=arms.index(reference)
    for row in rows:
        values = clusters[str(row["cluster"])]
        values[0] += row["exposure"]
        for i, arm in enumerate(arms):
            for j in range(2):
                values[1+i*2+j] += row["losses"][arm][j]
    blocks = list(clusters.values())
    totals = [sum(b[i] for b in blocks) for i in range(len(blocks[0]))]
    out = {"observations": len(rows), "matches": len(blocks), "exposure": totals[0], "arms": {}}
    for i, arm in enumerate(arms):
        out["arms"][arm] = {"brier": totals[1+i*2]/totals[0],
                              "log_loss": totals[2+i*2]/totals[0]}
    randomizer = random.Random(20260826)
    draws = {arm: [[], []] for arm in arms if arm!=reference}
    for _ in range(4000):
        sample = [blocks[randomizer.randrange(len(blocks))] for _ in blocks]
        denominator = sum(b[0] for b in sample)
        for i, arm in enumerate(arms):
            if arm==reference:
                continue
            for j in range(2):
                draws[arm][j].append(sum(b[1+i*2+j]-b[1+reference_index*2+j] for b in sample)/denominator)
    for arm in draws:
        for j, metric in enumerate(("brier", "log_loss")):
            ordered = sorted(draws[arm][j])
            out["arms"][arm][metric+"_delta_"+reference+"_ci95"] = [ordered[100], ordered[3899]]
    return out


@lru_cache(maxsize=12000)
def baseline_profile(conn, player_id, day, surface, start):
    return serve_return_profile(conn, player_id, day, surface=surface, start_time=start)


def profiles(conn, overlay, a, b, day, surface, start):
    base = [baseline_profile(conn,pid,day,surface,start) for pid in (a,b)]
    fresh = [overlay.profile(pid, day, surface=surface, start_time=start,
                             allow_historical_backfill=True).profile for pid in (a,b)]
    bounded = [overlay.profile(pid, day, surface=surface, start_time=start,
                               max_age_days=90, allow_historical_backfill=True).profile for pid in (a,b)]
    control = [replace(old, serve={**old.serve, "hold_rate": new.serve["hold_rate"]})
               for old, new in zip(base, fresh)]
    return dict(zip(ARMS, (base, fresh, bounded, control)))


def estimates(pair, fitted):
    if fitted:
        return [estimate_hold_fitted(pair[0],pair[1]), estimate_hold_fitted(pair[1],pair[0])]
    return [estimate_hold(pair[0],pair[1],return_weight=.35,elo_weight=.04),
            estimate_hold(pair[1],pair[0],return_weight=.35,elo_weight=.04)]


@lru_cache(maxsize=256)
def distribution(a, b, dispersion):
    return simulate_match(a,b,trials=1500,dispersion=dispersion)


def service_study(conn, overlay):
    records = {"hand": [], "fitted": []}
    coverage = Counter()
    for observations in overlay.official.values():
        for row in observations:
            day = row["match_date"]
            if not "2026-06-01" <= day <= "2026-10-25":
                continue
            n = float(row["service_games_played"])
            successes = n*float(row["hold_rate"])
            if abs(successes-round(successes)) > 1e-6:
                coverage["noninteger_held_games"] += 1
                continue
            variants = profiles(conn,overlay,row["player_id"],row["opponent_id"],day,row["surface"],None)
            coverage["targets"] += 1
            if coverage["targets"] % 500 == 0:
                print(json.dumps({'stage':'service_profiles','targets':coverage['targets']}),flush=True)
            for name, fitted in (("hand",False),("fitted",True)):
                holds = {arm: estimates(pair,fitted) for arm,pair in variants.items()}
                for arm, hs in holds.items():
                    coverage[name+"_"+arm+"_usable"] += int(all(h.is_usable for h in hs))
                if not all(h.is_usable for hs in holds.values() for h in hs):
                    continue
                records[name].append({"cluster": f"{row['tournament_id']}:{row['year']}:{row['wta_match_id']}",
                    "date":day,"surface":row["surface"],"exposure":n,
                    "losses":{arm: binomial_losses(hs[0].probability,successes,n) for arm,hs in holds.items()}})
    return {"coverage":dict(coverage),"models":{name: stratified(rows) for name,rows in records.items()}}


def stratified(rows, arms=ARMS, reference="A0"):
    def score(subset):
        return paired_summary(subset,arms,reference)

    return {"all":score(rows),
            "before_2026_07_15":score([r for r in rows if r["date"] < "2026-07-15"]),
            "from_2026_07_15":score([r for r in rows if r["date"] >= "2026-07-15"]),
            "surface":{s:score([r for r in rows if (r["surface"] or "unknown")==s])
                       for s in sorted({r["surface"] or "unknown" for r in rows})}}


def prop_study(conn, overlay, *, all_tours=False, profile_provider=None, records_only=False):
    scopes = ('player_games','player_game_margin','player_first_set_game_margin','player_first_set')
    conflicts = conflicting_result_matches(conn)
    # Earliest observation of each EXACT feed selection, never a later/in-play price.
    first_prices = {}
    # ORDER BY primary-key + first occurrence is exactly MIN(id), without
    # materialising a sort and doing thousands of random archive-disk lookups.
    for row in conn.execute('SELECT * FROM market_odds_snapshots ORDER BY id'):
        key = (row['match_id'],row['market_key'],row['market_name'],row['selection_name'],row['line'])
        # Tracker lacks bookmaker: retain the first id across books, never shop after outcomes.
        if key not in first_prices or row['id'] < first_prices[key]['id']:
            first_prices[key] = dict(row)
    price_groups=defaultdict(list)
    for key, quote in first_prices.items():
        price_groups[key[:3]].append(quote)
    tour_filter="" if all_tours else "AND (m.tour='WTA' OR (a.tour='WTA' AND b.tour='WTA'))"
    rows = conn.execute(f"""SELECT p.*, m.player_a_id,m.player_b_id,m.start_time_utc,m.tour,m.round,
        a.tour a_tour,b.tour b_tour,
        (SELECT level FROM tournament_levels tl WHERE tl.tournament_id=m.tournament_id
         ORDER BY id DESC LIMIT 1) tournament_level,
        (SELECT surface FROM tournament_levels tl WHERE tl.tournament_id=m.tournament_id
         AND tl.surface IS NOT NULL ORDER BY id DESC LIMIT 1) surface,
        a.name a_name,b.name b_name
        FROM prop_tracker p JOIN matches m ON m.id=p.match_id
        JOIN players a ON a.id=m.player_a_id JOIN players b ON b.id=m.player_b_id
        WHERE p.is_point_in_time=1 AND p.result_status IN ('WON','LOST')
        AND p.side='over' AND p.prop_scope IN (?,?,?,?)
        {tour_filter}
        AND p.match_date BETWEEN '2026-06-01' AND '2026-10-25' ORDER BY p.id""",scopes).fetchall()
    from tennis_wc.props.daily import _two_way_odds, _head_to_head_odds, _spread_odds
    output = []
    coverage = Counter()
    seen = set()
    for row in rows:
        coverage['candidate_rows'] += 1
        identity=(row['match_id'],row['prop_scope'],row['subject_player_id'],row['line'])
        if identity in seen:
            coverage['duplicate_contract'] += 1
            continue
        seen.add(identity)
        from tennis_wc.features.bo_format import detect_match_format
        tour=row['tour']
        if tour=='UNKNOWN' and row['a_tour']==row['b_tour']:
            tour=row['a_tour']
        if (detect_match_format({'tour':tour,'level':row['tournament_level'],'round':row['round']})!='BO3'
                or (row['tournament_level']=='GRAND_SLAM' and tour not in ('ATP','WTA'))):
            coverage['unsupported_format'] += 1
            continue
        if row['match_id'] in conflicts:
            coverage['conflicting_result'] += 1
            continue
        scope=row['prop_scope']
        line=row['line']
        if scope!='player_first_set' and (line is None or abs(abs(line)%1-.5)>1e-9):
            coverage['unsupported_push_line'] += 1
            continue
        if scope=='player_games' and line>15.5:
            coverage['legacy_mislabeled_games_line'] += 1
            continue
        key=(row['match_id'],row['feed_market_key'],row['feed_market_name'],row['feed_selection_name'],row['feed_line'])
        own=first_prices.get(key)
        cutoff=_stamp(row['start_time_utc'])
        if own is None or cutoff is None or _stamp(own['fetched_at']) is None or _stamp(own['fetched_at'])>=cutoff:
            coverage['missing_earliest_prematch_quote'] += 1
            continue
        pool=[q for q in price_groups[key[:3]]
              if q['bookmaker']==own['bookmaker'] and _stamp(q['fetched_at']) is not None
              and _stamp(q['fetched_at'])<cutoff]
        pair=None
        if scope=='player_games':
            pair=_two_way_odds(pool).get((row['match_id'],key[1],key[2],float(line)))
            odds=[pair.get('over'),pair.get('under')] if pair else []
        elif scope=='player_first_set':
            pair=_head_to_head_odds(pool,row).get(key[:3])
            odds=[pair.get('a'),pair.get('b')] if pair else []
        else:
            family='player_game_handicap' if scope=='player_game_margin' else 'player_first_set_game_handicap'
            candidates=_spread_odds(pool,row,family)
            for candidate_key,candidate in candidates.items():
                if abs(float(candidate['a']['handicap'])+float(line))<1e-9:
                    pair=candidate
                    break
            odds=[pair['a']['odds'],pair['b']['odds']] if pair else []
        if len(odds)!=2 or any(o is None or not math.isfinite(o) or o<=1 for o in odds):
            coverage['missing_complementary_quote'] += 1
            continue
        if scope=='player_games':
            identities=[(pair['over_name'],float(line)),(pair['under_name'],float(line))]
        elif scope=='player_first_set':
            identities=[(pair['a_name'],own['line']),(pair['b_name'],own['line'])]
        else:
            identities=[(pair[s+'_name'],pair[s]['handicap']) for s in ('a','b')]
        quotes=[next((q for q in pool if q['selection_name']==name and q['line']==quote_line),None)
                for name,quote_line in identities]
        if any(q is None for q in quotes) or quotes[0]['fetched_at']!=quotes[1]['fetched_at']:
            coverage['asynchronous_opening_pair'] += 1
            continue
        forecast_time=quotes[0]['fetched_at']
        forecast_day=_stamp(forecast_time).date().isoformat()
        market=(1/odds[0])/(1/odds[0]+1/odds[1])
        subject=row['subject_player_id']
        if subject not in (row['player_a_id'],row['player_b_id']):
            coverage['invalid_subject'] += 1
            continue
        if scope!='player_games' and subject!=row['player_a_id']:
            coverage['noncanonical_subject'] += 1
            continue
        opponent=row['player_b_id'] if subject==row['player_a_id'] else row['player_a_id']
        provider=profile_provider or profiles
        variants=provider(conn,overlay,subject,opponent,forecast_day,row['surface'],forecast_time)
        holds={arm:estimates(pair,scope!='player_first_set') for arm,pair in variants.items()}
        for arm,hs in holds.items():
            coverage[arm+'_usable'] += int(all(h.is_usable for h in hs))
        if not all(h.is_usable for hs in holds.values() for h in hs):
            continue
        probabilities={}
        for arm,hs in holds.items():
            simulation=distribution(round(hs[0].probability,3),round(hs[1].probability,3),0 if scope=='player_first_set' else .06)
            if scope=='player_games':
                p=simulation.player_games_over(line,'a')
            elif scope=='player_game_margin':
                p=simulation.game_handicap_cover(-line,'a')
            elif scope=='player_first_set_game_margin':
                p=simulation.first_set_game_handicap_cover(-line,'a')
            else:
                p=simulation.first_set_winner('a')
            probabilities[arm]=max(.03,min(.97,p))
        won=int(row['result_status']=='WON')
        output.append({'cluster':row['match_id'],'date':row['match_date'],'surface':row['surface'],
                       'family':scope,'exposure':1,'probabilities':probabilities,'market':market,'won':won,
                       'odds':odds[0], 'quote_id':own['id'],'contract':identity,'tour':tour,
                       'losses':{**{arm:binomial_losses(p,won,1) for arm,p in probabilities.items()},
                                 'market':binomial_losses(market,won,1)}})
    if records_only:
        return {'coverage':dict(coverage),'records':output}
    result={'coverage':dict(coverage),'paired':stratified(output),
            'secondary_raw_edge_threshold':.04,
            'families':{s:stratified([r for r in output if r['family']==s]) for s in scopes}}
    result['versus_market']={
        'all':stratified(output,('market',*ARMS),'market'),
        'families':{s:stratified([r for r in output if r['family']==s],('market',*ARMS),'market')
                    for s in scopes}}
    for label, subset in [('all',output)]+[(s,[r for r in output if r['family']==s]) for s in scopes]:
        n=len(subset)
        if not n:
            continue
        result.setdefault('market_and_secondary_roi',{})[label]={
            'n':n,'market_brier':sum(binomial_losses(r['market'],r['won'],1)[0] for r in subset)/n,
            'market_log_loss':sum(binomial_losses(r['market'],r['won'],1)[1] for r in subset)/n,
            'arms':{arm:{'selected':sum(r['probabilities'][arm]-r['market']>=.04 for r in subset),
                         'flat_profit':sum(r['odds']*r['won']-1 for r in subset if r['probabilities'][arm]-r['market']>=.04)}
                    for arm in ARMS}}
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    conn=sqlite3.connect(f'file:{args.db}?mode=ro',uri=True)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    conn.execute('PRAGMA cache_size=-65536')
    overlay=WtaHistoryOverlay(conn)
    print(json.dumps({'stage':'source_loaded','usable_sides':sum(map(len,overlay.official.values()))}),flush=True)
    result={'experiment':'EXP-20261026-04','db':str(args.db),'status':'COUNTERFACTUAL_RESEARCH_ONLY',
            'official_usable_sides':sum(map(len,overlay.official.values())),
            'source_issues':dict(overlay.issues),
            'service_games':service_study(conn,overlay),'props':prop_study(conn,overlay)}
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'output':str(args.output),'official_usable_sides':result['official_usable_sides'],
                      'prop_coverage':result['props']['coverage']},ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
