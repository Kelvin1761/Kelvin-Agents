#!/usr/bin/env python3
"""HKJC hindsight diagnostics; never exports production configuration.

The input is a frozen standalone-engine replay, not published live predictions.
Quarantined dates are excluded before label validation or fitting.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
from itertools import combinations
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
from scipy.optimize import linprog, minimize

ROOT = Path(__file__).resolve().parents[3]
AUTO = ROOT / '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'
sys.path.insert(0, str(AUTO))
from hkjc_racing_engine.scoring import MATRIX_WEIGHTS, DISPLAY_SLOPE

DIMS = tuple(MATRIX_WEIGHTS)
BASE = np.array(list(MATRIX_WEIGHTS.values()))
MARGIN = 0.01


def bounds(tier):
    if tier == 'local':
        return [(max(0., v-.05), min(1., v+.05)) for v in BASE]
    if tier == 'positive':
        return [(0., 1.)] * len(BASE)
    if tier == 'signed':
        return [(-1., 1.)] * len(BASE)
    raise ValueError(tier)


def metrics(scores, pos, numbers):
    order = np.lexsort((numbers, -scores))
    hits = pos[order] <= 3
    winner = np.flatnonzero(pos[order] == 1)
    return {'gold': bool(hits[:4].sum() == 3), 'good': bool(hits[:2].sum() == 2),
            'top3_hits_at4': int(hits[:4].sum()),
            'winner_rank': int(winner[0]+1) if len(winner) else None,
            'pairwise': float(np.mean([scores[i] > scores[j] or
                                      (scores[i] == scores[j] and numbers[i] < numbers[j])
                                      for i in range(len(pos)) for j in range(len(pos))
                                      if pos[i] < pos[j]])),
            'order': numbers[order].astype(int).tolist()}


def arrays(frame):
    matrix = frame[['matrix_'+d for d in DIMS]].to_numpy(float)
    score = frame.current_live_recomputed_ability.to_numpy(float)
    x = DISPLAY_SLOPE * matrix
    # Initial runners retain their dedicated weights and all current scores.
    x[frame.is_debut.to_numpy(bool)] = 0
    residual = score - x @ BASE
    if not np.isfinite(x).all() or not np.isfinite(score).all():
        raise ValueError('Nonfinite score/matrix; do not silently fill neutral')
    assert np.max(np.abs(x @ BASE + residual - score)) < 1e-8
    return x, residual, score


def solve(x, residual, comparisons, tier):
    n = len(BASE)
    a = np.array([x[j]-x[i] for i,j in comparisons])
    b = np.array([residual[i]-residual[j]-MARGIN for i,j in comparisons])
    constraints = np.vstack([np.c_[a, np.zeros_like(a)],
                              np.c_[np.eye(n), -np.eye(n)],
                              np.c_[-np.eye(n), -np.eye(n)]])
    result = linprog(np.r_[np.zeros(n), np.ones(n)], A_ub=constraints,
                     b_ub=np.r_[b, BASE, -BASE],
                     A_eq=[np.r_[np.ones(n), np.zeros(n)]], b_eq=[1.],
                     bounds=bounds(tier)+[(0,None)]*n, method='highs')
    if result.success:
        weights = result.x[:n]
        if np.max(a @ weights - b) > 1e-6:
            raise RuntimeError('LP witness failed verification')
        return weights
    if result.status != 2:
        raise RuntimeError(result.message)
    return None


def joint(x, residual, pos, tier, target="joint"):
    podium = np.flatnonzero(pos <= 3)
    outsiders = np.flatnonzero(pos > 3)
    best = None
    for pair in combinations(podium, 2):
        other = next(i for i in podium if i not in pair)
        for spare in outsiders:
            comparisons = [(i,j) for i in pair for j in range(len(pos)) if j not in pair]
            comparisons += [(other,j) for j in outsiders if j != spare]
            if target == 'gold':
                comparisons = [(i,j) for i in podium for j in outsiders if j != spare]
            elif target == 'good':
                comparisons = [(i,j) for i in pair for j in range(len(pos)) if j not in pair]
            w = solve(x, residual, comparisons, tier)
            if w is not None and (best is None or np.abs(w-BASE).sum() < np.abs(best-BASE).sum()-1e-9):
                best = w
    return best


def fit_order(x, residual, pos, tier):
    pairs = [(i,j) for i in range(len(pos)) for j in range(len(pos)) if pos[i] < pos[j]]
    delta = np.array([x[i]-x[j] for i,j in pairs]) / 6.
    offset = np.array([residual[i]-residual[j] for i,j in pairs]) / 6.
    def loss(w):
        return float(np.logaddexp(0., -(delta @ w + offset)).mean() + .02*np.sum((w-BASE)**2))
    result = minimize(loss, BASE, method='SLSQP', bounds=bounds(tier),
                      constraints=[{'type':'eq','fun':lambda w: w.sum()-1}],
                      options={'maxiter':300,'ftol':1e-10})
    if not result.success:
        raise RuntimeError(result.message)
    return result.x


def dev_frame(frame, quarantine):
    return frame[frame.date.astype(str) < quarantine].copy()


def health(frame):
    result = {}
    for column in [c for c in frame.columns if c.startswith(('matrix_', 'feat_'))]:
        v = frame[column].to_numpy(float)
        result[column] = {'neutral_fraction':float(np.isclose(v,60,atol=.01).mean()),
                          'sd':float(np.std(v)), 'range':float(np.ptp(v))}
    return result


def diagnose(frame):
    frame = frame.sort_values('horse_number')
    first = frame.iloc[0]
    x, residual, score = arrays(frame)
    pos = frame.finish_pos.to_numpy(int)
    numbers = frame.horse_number.to_numpy(int)
    baseline = metrics(score, pos, numbers)
    record = {'meeting':first.meeting_name,'date':first.date,'race':int(first.race_number),
              'venue':first.venue,'surface':first.track,'field':len(frame),
              'debut_count':int(frame.is_debut.sum()),'baseline':baseline,
              'missed':not (baseline['gold'] or baseline['good']),
              'health':health(frame),'tiers':{}}
    archive = frame.current_live_rank.to_numpy(float)
    record['stored_ranking_available'] = bool(np.isfinite(archive).all() and len(set(archive)) == len(frame))
    if record['stored_ranking_available']:
        old = metrics(-archive,pos,numbers)
        record['stored_archive'] = old
        record['archive_order_changed'] = old['order'] != baseline['order']
    for tier in ('local','positive','signed'):
        w = joint(x,residual,pos,tier)
        result = {'joint_feasible':w is not None}
        for target in ('gold','good'):
            wt = w if w is not None else joint(x,residual,pos,tier,target)
            result[target+'_feasible'] = wt is not None
            if wt is not None:
                mt = metrics(x @ wt+residual,pos,numbers)
                assert mt[target]
                result[target+'_witness'] = {'weights':dict(zip(DIMS,wt.tolist())),
                                           'l1':float(np.abs(wt-BASE).sum()), 'metrics':mt}
        result['either_feasible'] = result['gold_feasible'] or result['good_feasible']
        if w is not None:
            witness = metrics(x @ w+residual,pos,numbers)
            assert witness['gold'] and witness['good']
            result.update(weights=dict(zip(DIMS,w.tolist())),l1=float(np.abs(w-BASE).sum()), metrics=witness)
        if tier != 'signed':
            ordered = fit_order(x,residual,pos,tier)
            result['order_fit'] = {'weights':dict(zip(DIMS,ordered.tolist())),
                                   'metrics':metrics(x @ ordered+residual,pos,numbers)}
        record['tiers'][tier] = result
    podium = frame[frame.finish_pos <=3]
    record['full_order_positive_feasible'] = solve(x,residual,
        [(i,j) for i in range(len(pos)) for j in range(len(pos)) if pos[i]<pos[j]],
        'positive') is not None
    record['podium'] = [{'number':int(r.horse_number),'name':r.horse_name,'finish':int(r.finish_pos),
                        'baseline_rank':baseline['order'].index(int(r.horse_number))+1,
                        'matrices':{d:float(r['matrix_'+d]) for d in DIMS}}
                        for _,r in podium.iterrows()]
    return record


def summary(records):
    if not records:
        return {'races':0}
    return {'races':len(records), 'misses':sum(r['missed'] for r in records),
            'gold':sum(r['baseline']['gold'] for r in records),
            'good':sum(r['baseline']['good'] for r in records),
            'tier_either_feasible':{t:sum(r['tiers'][t]['either_feasible'] for r in records)
                                    for t in ('local','positive','signed')},
            'tier_joint_feasible':{t:sum(r['tiers'][t]['joint_feasible'] for r in records)
                                   for t in ('local','positive','signed')}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--quarantine-from',default='2026-09-09')
    args = parser.parse_args()
    path = Path(args.dataset)
    frame = dev_frame(pd.read_csv(path),args.quarantine_from)
    records, excluded = [], Counter()
    for _,race in frame.groupby(['date','meeting_name','race_number'],sort=True):
        pos = race.finish_pos.to_numpy(float)
        if len(race)<5 or not (race.race_label_valid == 1).all() or not np.isfinite(pos).all():
            excluded['invalid_or_small_race'] +=1
            continue
        records.append(diagnose(race))
        if len(records)%25==0:
            print('Diagnosed',len(records),flush=True)
    sources = [Path(__file__),AUTO/'hkjc_racing_engine/scoring.py',
               AUTO/'hkjc_racing_engine/engine_core.py',
               ROOT/'.agents/skills/hkjc_racing/hkjc_reflector/scripts/build_hkjc_ranking_dataset.py']
    hashes = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    payload = {'design':{'baseline':'standalone current RacingEngine replay; SIP not reapplied',
                        'not_prediction_evidence':True,'pit_provenance':'FLAG',
                        'quarantine_from':args.quarantine_from,'baseline_weights':dict(zip(DIMS,BASE.tolist())),
                        'dataset_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                        'source_sha256':hashes,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                        'exclusions':dict(excluded)},
               'summary':summary(records),'missed':summary([r for r in records if r['missed']]),
               'cohorts':{str(k):summary(v) for k,v in
                          ((k,[r for r in records if (r['venue'],r['surface'])==k])
                           for k in sorted(set((r['venue'],r['surface']) for r in records)))},
               'races':records}
    dest = Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(payload['summary'],ensure_ascii=False),flush=True)

if __name__ == '__main__':
    main()
