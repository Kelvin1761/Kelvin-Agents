#!/usr/bin/env python3
"""EXP-09: exact-course-distance standards; research only, fixed family."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import json
import math
from pathlib import Path
import statistics

import numpy as np

from au_neutral_speed_20261015 import ROOT, auc, diff, estimate, sha
from au_racing_engine import full_time_speed as live
from model_evaluation_decision import holm_adjust


class SegmentStandard(live.ContextStandard):
    def length(self, event):
        return 800 if self.segment == 'late' else super().length(event)


class ExactStandard(SegmentStandard):
    @staticmethod
    def category(event, kind):
        if kind == 'track_band':
            return event['track'] + ':' + str(event['distance'])
        return live.ContextStandard.category(event, kind)


def lookup(history, segment, standard):
    if len(history) < 100:
        return {}
    model = standard(history, segment)
    days = defaultdict(list)
    for event in history:
        residual = math.log(event[segment]/model.length(event))-model.predict(event)
        days[event['track'], event['date']].append((tuple(event['key']), residual))
    out = {}
    for event in history:
        key = tuple(event['key'])
        others = [v for k, v in days[event['track'], event['date']] if k != key]
        variant = (float(np.clip(statistics.median(others), -.05, .05))*len(others)/(len(others)+3)
                   if len(others) >= 3 else 0)
        par = model.predict(event, True)+variant
        field = {'total': 'time', 'early': 'early', 'late': 'l800'}[segment]
        for row in event['rows']:
            identity = (key, row['horse'])
            assert identity not in out
            out[identity] = {'A': -(math.log(row[field]/model.length(event))-par)*1000,
                             'going': event['going']}
    return out


def weighted_runs(keys, name, target, distance, going, evidence):
    found = []
    for key in keys:
        key = tuple(key)
        if key[1] >= target or (key, name) not in evidence:
            continue
        days = (date.fromisoformat(target)-date.fromisoformat(key[1])).days
        weight = 2**(-days/90)*math.exp(-abs(math.log(key[3]/distance))/.25)
        if going and evidence[key, name]['going'] != going:
            weight *= .5
        found.append((key, weight))
        if len(found) == 6:
            break
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--inputs', type=Path, required=True)
    ap.add_argument('--events', type=Path, required=True)
    ap.add_argument('--forms', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    races = json.loads(args.inputs.read_text())['races']
    events = json.loads(args.events.read_text())
    forms = {tuple(k): [tuple(v) for v in values] for k, values in json.loads(args.forms.read_text())}
    for event in events:
        event['key'] = tuple(event['key'])
        event['late'] = statistics.median(row['l800'] for row in event['rows'])
    days = sorted({r['date'] for r in races})
    report = {'base_sha': 'ca2c4bd6', 'source_hashes': {k: sha(p) for k, p in
        [('inputs', args.inputs), ('events', args.events), ('forms', args.forms)]},
        'audit': {}, 'source_audit': 'FLAG: original historical publication/capture unknown',
        'research_only': True, 'rank_gain': 1.5}
    oos = [r for r in races if r['date'] in days[30:]]
    report['power_before_comparison'] = diff(oos, 'deployed', 'baseline')
    audits = []
    max_error = 0.
    for day in days:
        history = [e for e in events if e['date'] < day]
        base = lookup(history, 'total', SegmentStandard)
        exact = {k: lookup(history, segment, ExactStandard) for k, segment in
                 [('A', 'total'), ('E', 'early'), ('L', 'late')]}
        band = Counter((e['track'], e['distance']//400) for e in history)
        precise = Counter((e['track'], e['distance']) for e in history)
        for race in [r for r in races if r['date'] == day]:
            raw = {k: [] for k in exact}
            reliabilities = {k: [] for k in exact}
            for row in race['rows']:
                name = live.norm(row['name'])
                keys = forms.get((race['meeting'], race['race'], name), [])
                distance = int(''.join(c for c in str(row['distance']) if c.isdigit()))
                going = live.condition_key(row.get('going') or '')
                old, _, _ = live.aggregate(keys, name, day, distance, going, base)
                stored = row['context_speed']['A']
                assert (old['A'] is None) == (stored is None), (race['meeting'], row['name'])
                if stored is not None:
                    max_error = max(max_error, abs(old['A']-stored))
                for k, evidence in exact.items():
                    values, count, rel = live.aggregate(keys, name, day, distance, going, evidence)
                    raw[k].append(values['A'])
                    reliabilities[k].append(rel['A'])
                    row['context_speed'][k+'_exact'] = values['A']
                found = weighted_runs(keys, name, day, distance, going, base)
                if day in days[30:] and found:
                    total = sum(w for _, w in found)
                    audits.append({'target': day, 'horse': name, 'distance': distance,
                        'runs': len(found), 'weight_sum': total,
                        'long_run_weight_share': sum(w for k, w in found if k[3] > 1700)/total,
                        'same_distance_weight_share': sum(w for k, w in found if k[3] == distance)/total,
                        'prior_band_support': [band[k[0], k[3]//400] for k, _ in found],
                        'prior_exact_support': [precise[k[0], k[3]] for k, _ in found],
                        'historical_distances': [k[3] for k, _ in found]})
            for k in exact:
                z = live.zscores(raw[k])
                for row, signal, rel in zip(race['rows'], z, reliabilities[k]):
                    row[k+'_exact_z'] = signal*rel
            for row in race['rows']:
                row['exact_rank'] = round(row['baseline']+1.5*row['A_exact_z'], 4)
        print('prior-only transforms', day, len(history), 'max A/A error', max_error, flush=True)
    assert max_error < 1e-8, max_error
    oos = [r for r in races if r['date'] in days[30:]]
    report['aa_max_raw_error'] = max_error
    report['races'] = len(races)
    report['oos_races'] = len(oos)
    report['oos_days'] = len(days[30:])
    report['diagnostics'] = {k: auc(oos, k) for k in ('A', 'A_exact', 'E_exact', 'L_exact')}
    report['diagnostic_holm'] = holm_adjust({k: report['diagnostics'][k]['speed']['p_two_sided']
        for k in ('A_exact', 'E_exact', 'L_exact')})
    daily = defaultdict(lambda: np.zeros(2))
    for race in oos:
        rows = [r for r in race['rows'] if r['context_speed']['A'] is not None
                and r['context_speed']['A_exact'] is not None]
        from au_leaf_power import within_race_auc
        a, n = within_race_auc([(r['context_speed']['A_exact'], r['pos'] <= 3) for r in rows])
        b, n2 = within_race_auc([(r['context_speed']['A'], r['pos'] <= 3) for r in rows])
        assert n == n2
        daily[race['date']] += [a-b, n]
    report['paired_exact_minus_A'] = estimate([daily[d] for d in sorted(daily)], paired=True)
    for label, predicate in [('short', lambda d: d <= 1200),
                             ('middle', lambda d: 1200 < d <= 1700), ('staying', lambda d: d > 1700)]:
        matched = [x for x in audits if predicate(x['distance'])]
        subset = [r for r in oos if predicate(int(''.join(c for c in str(r['rows'][0]['distance']) if c.isdigit())))]
        report['audit'][label] = {'matched_runners': len(matched),
            'median_runs': statistics.median(x['runs'] for x in matched),
            'median_long_run_weight_share': statistics.median(x['long_run_weight_share'] for x in matched),
            'median_same_distance_weight_share': statistics.median(x['same_distance_weight_share'] for x in matched),
            'no_long_history_runners': sum(x['long_run_weight_share'] == 0 for x in matched),
            'median_prior_band_support': statistics.median(v for x in matched for v in x['prior_band_support']),
            'median_prior_exact_support': statistics.median(v for x in matched for v in x['prior_exact_support']),
            'diagnostics': {k: auc(subset, k) for k in ('A', 'A_exact', 'E_exact', 'L_exact')}}
    # Budget is this candidate's change to the existing full-time component only.
    report['comparison'] = diff(oos, 'deployed', 'exact_rank')
    report['field_buckets'] = {}
    from au_eval import _counts_by_field
    report['field_buckets'] = {k: _counts_by_field(oos, lambda r: r[k])
                              for k in ('deployed', 'exact_rank')}
    args.out.write_text(json.dumps(report, indent=2))
    args.out.with_suffix('.audit.json').write_text(json.dumps(audits))
    args.out.with_suffix('.predictions.json').write_text(json.dumps({'races': oos}))
    print('Wrote', args.out, flush=True)


if __name__ == '__main__':
    main()
