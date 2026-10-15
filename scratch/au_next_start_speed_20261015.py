#!/usr/bin/env python3
"""EXP-10 locked next-start pairwise learning. Research only; no live writes."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import json
import math
from pathlib import Path
import re
import statistics

import numpy as np

from au_neutral_speed_20261015 import diff, estimate, sha
from au_racing_engine import full_time_speed as live
from au_eval import _counts, _counts_by_field
from au_leaf_power import within_race_auc
from model_evaluation_decision import holm_adjust

FEATURES = ('T', 'P', 'Q', 'P2', 'Q2', 'PQ')
RIDGE = 10.


def profile_lookup(events, target):
    """All standard fitting is strictly earlier than this prediction's date."""
    history = [e for e in events if e['date'] < target]
    if len(history) < 100:
        return {}, len(history)
    total = live.ContextStandard(history, 'total')
    early = live.ContextStandard(history, 'early')
    by_day = {segment: defaultdict(list) for segment in ('total', 'early')}
    for event in history:
        key = tuple(event['key'])
        for segment, model in [('total', total), ('early', early)]:
            residual = math.log(event[segment]/model.length(event))-model.predict(event)
            by_day[segment][event['track'], event['date']].append((key, residual))
    lookup = {}
    for event in history:
        key = tuple(event['key'])
        variants = {}
        for segment in ('total', 'early'):
            others = [v for k, v in by_day[segment][event['track'], event['date']] if k != key]
            variants[segment] = (float(np.clip(statistics.median(others), -.05, .05))*len(others)/(len(others)+3)
                                 if len(others) >= 3 else 0.)
        total_par = total.predict(event, True)+variants['total']
        early_par = early.predict(event)+variants['early']
        tempo = float(np.clip(-(math.log(event['early']/early.length(event))-early_par)/.03, -3, 3))
        for row in event['rows']:
            assert row['distance'] == event['distance']
            identity = (key, row['horse'])
            assert identity not in lookup
            t = -(math.log(row['time']/event['distance'])-total_par)*1000
            q = float(np.clip(-math.log(row['early']/event['early'])/.03, -3, 3))
            lookup[identity] = {'A': t, 'going': event['going'],
                'profile': [t, tempo, q, tempo*tempo, q*q, tempo*q]}
    return lookup, len(history)


def runner_profile(keys, name, target, distance, going, lookup):
    """Use the latest actual formal run; never skip a missing latest race."""
    eligible = sorted({tuple(k) for k in keys if k[1] < target}, key=lambda k: k[1], reverse=True)
    if not eligible:
        return None, 0., {'status': 'no_previous_formal_run'}
    last_day = eligible[0][1]
    same_day = [k for k in eligible if k[1] == last_day]
    if len(same_day) != 1:
        return None, 0., {'status': 'ambiguous_previous_day', 'previous_date': last_day}
    key = same_day[0]
    observation = lookup.get((key, name))
    if observation is None:
        return None, 0., {'status': 'latest_run_uncovered', 'previous_date': last_day,
                          'previous_key': key}
    gap = (date.fromisoformat(target)-date.fromisoformat(last_day)).days
    weight = 2**(-gap/90)*math.exp(-abs(math.log(key[3]/distance))/.25)
    if going and going != observation['going']:
        weight *= .5
    reliability = weight/(weight+3)
    return observation['profile'], reliability, {'status': 'observed', 'previous_date': last_day,
        'previous_key': key, 'gap_days': gap, 'weight': weight, 'reliability': reliability}


def loss(beta, x, offset):
    return float(np.logaddexp(0, -(offset+x@beta)).sum()+RIDGE/2*np.dot(beta, beta))


def fit_logistic(x, offset):
    """One convex objective, fixed regularization; no hyperparameter selection."""
    beta = np.zeros(x.shape[1])
    if len(x) < 20:
        return beta, {'pairs': len(x), 'fallback': 'insufficient_pairs', 'converged': True}
    converged = False
    for iteration in range(50):
        margin = offset+x@beta
        p = np.exp(-np.logaddexp(0, margin))
        gradient = -x.T@p+RIDGE*beta
        if np.max(np.abs(gradient)) < 1e-8:
            converged = True
            break
        hessian = x.T@((p*(1-p))[:, None]*x)+RIDGE*np.eye(x.shape[1])
        step = np.linalg.solve(hessian, gradient)
        alpha = 1.
        current = loss(beta, x, offset)
        while alpha > 1e-8:
            trial = beta-alpha*step
            if loss(trial, x, offset) <= current-1e-4*alpha*np.dot(gradient, step):
                beta = trial
                break
            alpha *= .5
        else:
            break
    # Recheck at the final iterate rather than trusting step size alone.
    p = np.exp(-np.logaddexp(0, offset+x@beta))
    converged |= bool(np.max(np.abs(-x.T@p+RIDGE*beta)) < 1e-7)
    if not converged:
        raise RuntimeError('fixed logistic solver did not converge')
    return beta, {'pairs': len(x), 'fallback': None, 'converged': True,
                  'iterations': iteration+1, 'loss': loss(beta, x, offset)}


def train(races, cutoff, width, with_offset):
    prefix = [r for r in races if '2026-08-05' <= r['date'] < cutoff]
    x, offsets = [], []
    for race in prefix:
        observed = [r for r in race['rows'] if r['next_profile_audit']['status'] == 'observed']
        for row in observed:
            assert row['next_profile_audit']['previous_date'] < race['date']
        good = [r for r in observed if r['pos'] <= 3]
        bad = [r for r in observed if r['pos'] > 3]
        for a in good:
            for b in bad:
                x.append(np.array(a['next_x'][:width])-np.array(b['next_x'][:width]))
                offsets.append((a['deployed']-b['deployed'])/10 if with_offset else 0.)
    xx = np.array(x).reshape((-1, width))
    beta, meta = fit_logistic(xx, np.array(offsets))
    meta.update({'train_through': max(r['date'] for r in prefix), 'train_races': len(prefix),
                 'features': FEATURES[:width], 'beta': beta.tolist(), 'ridge': RIDGE})
    return beta, meta


def diagnostic(races, key, compare=None):
    daily = defaultdict(lambda: np.zeros(2))
    other = defaultdict(lambda: np.zeros(2))
    covered = compared = 0
    for race in races:
        rows = [r for r in race['rows'] if r['next_profile_audit']['status'] == 'observed']
        covered += len(rows)
        c, n = within_race_auc([(r[key], r['pos'] <= 3) for r in rows])
        daily[race['date']] += [c, n]
        compared += n > 0
        if compare:
            cc, nn = within_race_auc([(r[compare], r['pos'] <= 3) for r in rows])
            assert nn == n
            other[race['date']] += [cc, nn]
    days = sorted(daily)
    out = {'covered_runners': covered, 'comparable_races': compared,
           'auc': estimate([daily[d] for d in days])}
    if compare:
        out['comparison_auc'] = estimate([other[d] for d in days])
        out['paired_difference'] = estimate([[daily[d][0]-other[d][0], daily[d][1]] for d in days], paired=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    for name in ('fresh', 'reference', 'events', 'forms', 'out'):
        ap.add_argument('--'+name, type=Path, required=True)
    args = ap.parse_args()
    reference = json.loads(args.reference.read_text())['races']
    fresh = json.loads(args.fresh.read_text())['races']
    identity = lambda r: (r['date'], r['meeting'], r['race'])
    index = {identity(r): r for r in fresh}
    races = []
    for prior in reference:
        race = index[identity(prior)]
        race['rows'].sort(key=lambda r: r['n'])
        old = sorted(prior['rows'], key=lambda r: r['n'])
        assert [(r['n'], r['name'], r['pos']) for r in race['rows']] == [(r['n'], r['name'], r['pos']) for r in old]
        for a, b in zip(race['rows'], old):
            assert abs(a['ability']-b['ability']) < .000051
            a['baseline'] = a['ability']
            a['A'] = b['A']
            a['context_speed'] = b['context_speed']
            a['deployed'] = round(a['ability']+1.5*a['A'], 4)
            assert a.get('full_time', 0) == 0
        races.append(race)
    races.sort(key=identity)
    days = sorted({r['date'] for r in races})
    oos = [r for r in races if r['date'] in days[30:]]
    assert len(races) == 2496 and len(oos) == 1493
    report = {'baseline_sha': '81597057', 'source_hashes': {k: sha(p) for k, p in
        [('fresh', args.fresh), ('reference', args.reference), ('events', args.events), ('forms', args.forms)]},
        'races': len(races), 'oos_races': len(oos), 'oos_days': len(days[30:]),
        'source_audit': 'FLAG: historical publication/capture unknown; retrospective inspected windows',
        'background_A_component_budget_before_fit': diff(oos, 'deployed', 'baseline')}
    events = json.loads(args.events.read_text())
    forms = {tuple(k): [tuple(v) for v in values] for k, values in json.loads(args.forms.read_text())}
    max_aa = 0.
    for day in days:
        lookup, n = profile_lookup(events, day)
        for race in [r for r in races if r['date'] == day]:
            raws, rels = [], []
            for row in race['rows']:
                name = live.norm(row['name'])
                keys = forms.get((race['meeting'], race['race'], name), [])
                distance = int(re.search(r'\d+', str(row['distance']))[0])
                going = live.condition_key(row.get('going') or '')
                legacy, _, _ = live.aggregate(keys, name, day, distance, going, lookup)
                prior = row['context_speed']['A']
                assert (prior is None) == (legacy['A'] is None)
                if prior is not None:
                    max_aa = max(max_aa, abs(prior-legacy['A']))
                raw, rel, audit = runner_profile(keys, name, day, distance, going, lookup)
                row['next_profile_audit'] = audit
                row['next_raw'] = raw
                raws.append(raw)
                rels.append(rel)
            columns = [live.zscores([r[j] if r is not None else None for r in raws]) for j in range(6)]
            for i, row in enumerate(race['rows']):
                row['next_x'] = [columns[j][i]*rels[i] for j in range(6)]
        print('features', day, 'prior events', n, 'A/A', max_aa, flush=True)
    assert max_aa < 1e-8
    report['aa_max_error'] = max_aa
    report['windows'] = []
    arms = {'N_total': (1, False), 'N_profile': (6, False), 'D_total': (1, True), 'D_profile': (6, True)}
    for start in range(30, len(days), 7):
        target_days = days[start:start+7]
        test = [r for r in races if r['date'] in target_days]
        window = {'test_dates': target_days, 'arms': {}}
        for arm, (width, offset) in arms.items():
            beta, meta = train(races, target_days[0], width, offset)
            assert meta['train_through'] < min(target_days)
            for race in test:
                for row in race['rows']:
                    delta = 10*float(np.dot(row['next_x'][:width], beta))
                    row[arm] = round((row['deployed'] if offset else 60)+delta, 4)
            window['arms'][arm] = meta
        report['windows'].append(window)
        print('window', target_days[0], window, flush=True)
    report['diagnostics'] = {key: diagnostic(oos, key) for key in ('N_total', 'N_profile', 'deployed')}
    report['profile_minus_total_auc'] = diagnostic(oos, 'N_profile', 'N_total')
    report['comparisons'] = {f'{c}_vs_{b}': diff(oos, b, c) for b, c in
        [('deployed', 'D_total'), ('deployed', 'D_profile'), ('D_total', 'D_profile')]}
    report['family_holm'] = holm_adjust({f'{a}:{k}': v['p_two_sided']
        for a in ('D_total_vs_deployed', 'D_profile_vs_deployed')
        for k, v in report['comparisons'][a]['evidence'].items()})
    report['coverage'] = dict(Counter(r['next_profile_audit']['status'] for race in oos for r in race['rows']))
    report['gaps_days'] = np.quantile([r['next_profile_audit']['gap_days'] for race in oos for r in race['rows']
        if r['next_profile_audit']['status'] == 'observed'], [0, .25, .5, .75, 1]).tolist()
    report['field_buckets'] = {a: _counts_by_field(oos, lambda r: r[a]) for a in ('deployed', 'D_total', 'D_profile')}
    report['cohorts'] = {}
    def distance_group(race):
        d = int(re.search(r'\d+', str(race['rows'][0]['distance']))[0])
        return 'short' if d <= 1200 else 'middle' if d <= 1700 else 'staying'
    groupers = {'distance': distance_group, 'going': lambda r: r['rows'][0].get('going') or 'unknown',
        'venue': lambda r: re.sub(r'^\d{4}-\d{2}-\d{2}\s*', '', r['meeting']).split(' Race ')[0],
        'top_pick_result_sp': lambda r: str(next((b for b in (3, 6, 11, 21)
          if float(max(r['rows'], key=lambda x: x['deployed']).get('sp') or 999) < b), '21+'))}
    for name, grouper in groupers.items():
        groups = defaultdict(list)
        for race in oos:
            groups[grouper(race)].append(race)
        report['cohorts'][name] = {g: {'races': len(rr), 'diagnostic': diagnostic(rr, 'N_profile', 'N_total'),
            **{a: _counts(rr, lambda r: r[a]) for a in ('deployed', 'D_total', 'D_profile')}} for g, rr in groups.items()}
    args.out.write_text(json.dumps(report, indent=2))
    args.out.with_suffix('.predictions.json').write_text(json.dumps({'races': oos}))
    print('Wrote', args.out, flush=True)


if __name__ == '__main__':
    main()
