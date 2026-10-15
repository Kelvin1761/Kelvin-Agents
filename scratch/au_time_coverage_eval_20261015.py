#!/usr/bin/env python3
"""EXP-12 fixed four-arm source/latest-time ablation. Research only."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, time
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo
import numpy as np

from au_neutral_speed_20261015 import diff, sha
from au_next_start_speed_20261015 import runner_profile, train
from au_racing_engine import full_time_speed as live
from au_eval import _counts, _counts_by_field
from model_evaluation_decision import holm_adjust


def available(event, target):
    if event['date'] >= target:
        return False
    stamp = event.get('published_at_utc')
    if stamp:
        return datetime.fromisoformat(stamp.replace('Z', '+00:00')) < datetime.combine(
            datetime.fromisoformat(target).date(), time.min, ZoneInfo('Australia/Sydney'))
    return True  # Original RQ source retains historical availability FLAG.


RQ_BINDINGS = {'aquisparkgoldcoast': 'goldcoast', 'ladbrokescannonpark': 'cairns',
               'picklebetparkwarwick': 'warwick'}


def bind_rq_lookup(lookup):
    expanded = dict(lookup)
    for (key, name), value in lookup.items():
        if key[0] in RQ_BINDINGS:
            alias = ((RQ_BINDINGS[key[0]], *key[1:]), name)
            if alias in expanded:
                raise ValueError('ambiguous RQ source-local binding '+str(alias))
            expanded[alias] = value
    return expanded


def features(races, events, forms, prefix, rq_bindings=False):
    days = sorted({r['date'] for r in races})
    for day in days:
        selected = [e for e in events if available(e, day)]
        lookup, count = live.context_lookup(selected, day)
        if rq_bindings:
            lookup = bind_rq_lookup(lookup)
        for v in lookup.values():
            v['profile'] = [v['A']]
        for race in (r for r in races if r['date'] == day):
            aa, ar, tt, tr = [], [], [], []
            for row in race['rows']:
                name = live.norm(row['name'])
                identity = (race['meeting'], race['race'], name)
                if identity not in forms:
                    raise ValueError('form corpus missing '+str(identity))
                keys = forms[identity]
                distance = int(re.search(r'\d+', str(row['distance']))[0])
                going = live.condition_key(row.get('going') or '')
                a, _, reliability = live.aggregate(keys, name, day, distance, going, lookup)
                t, rel, audit = runner_profile(keys, name, day, distance, going, lookup)
                row[prefix+'_audit'] = audit
                aa.append(a['A']); ar.append(reliability['A'])
                tt.append(t[0] if t is not None else None); tr.append(rel)
            az, tz = live.zscores(aa), live.zscores(tt)
            for i, row in enumerate(race['rows']):
                row[prefix] = round(row['ability']+1.5*az[i]*ar[i], 4)
                row[prefix+'_x'] = [tz[i]*tr[i]]
                row[prefix+'_raw'] = tt[i]
        print('features', prefix, day, count, flush=True)


def main():
    ap = argparse.ArgumentParser()
    for n in ('fresh', 'events', 'forms', 'tas', 'out'):
        ap.add_argument('--'+n, required=True, type=Path)
    ap.add_argument('--rq-bindings', action='store_true')
    args = ap.parse_args()
    races = [r for r in json.loads(args.fresh.read_text())['races'] if '2026-08-05' <= r['date'] <= '2026-10-14']
    races.sort(key=lambda r: (r['date'], r['meeting'], r['race']))
    for race in races:
        race['rows'].sort(key=lambda r: r['n'])
        assert all(r.get('full_time', 0) == 0 for r in race['rows'])
    forms = {tuple(k): [tuple(v) for v in vv] for k, vv in json.loads(args.forms.read_text())}
    rq = json.loads(args.events.read_text())
    tas = json.loads(args.tas.read_text())['events']
    for e in rq+tas:
        e['key'] = tuple(e['key'])
    assert not ({e['key'] for e in rq} & {e['key'] for e in tas})
    report = {'baseline_commit': '9f0360c7', 'source_hashes': {n: sha(getattr(args, n))
              for n in ('fresh', 'events', 'forms', 'tas')},
        'audit': 'FLAG: historical RQ capture unknown; TAS attachment publication metadata is not contemporaneous capture',
        'protocol': 'EXP-20261015-13' if args.rq_bindings else 'EXP-20261015-12',
        'rq_bindings': RQ_BINDINGS if args.rq_bindings else {}, 'races': len(races), 'tas_races': len(tas),
        'tas_runners': sum(len(e['rows']) for e in tas)}
    features(races, rq, forms, 'Q')
    features(races, rq+tas, forms, 'QT', args.rq_bindings)
    oos = [r for r in races if r['date'] >= '2026-09-04']
    days = sorted({r['date'] for r in oos})
    report.update({'oos_races': len(oos), 'oos_days': len(days), 'windows': []})
    for start in range(0, len(days), 7):
        window = days[start:start+7]
        meta = {'dates': window, 'fits': {}}
        for source, arm in [('Q', 'QL'), ('QT', 'QTL')]:
            for race in races:
                for r in race['rows']:
                    r['next_profile_audit'] = r[source+'_audit']
                    r['next_x'] = r[source+'_x']
                    r['deployed'] = r[source]
            beta, fit = train(races, window[0], 1, True)
            assert fit['train_through'] < window[0]
            meta['fits'][arm] = fit
            for race in (r for r in oos if r['date'] in window):
                for r in race['rows']:
                    r[arm] = round(r[source]+10*float(np.dot(r[source+'_x'], beta)), 4)
        report['windows'].append(meta)
    report['counts'] = {a: _counts(oos, lambda r: r[a]) for a in ('Q', 'QL', 'QT', 'QTL')}
    report['comparisons'] = {c+'_vs_'+b: diff(oos, b, c) for b, c in
        [('Q', 'QL'), ('Q', 'QT'), ('Q', 'QTL'), ('QT', 'QTL'), ('QL', 'QTL')]}
    report['family_holm'] = holm_adjust({a+':'+k: v['p_two_sided']
        for a in ('QL_vs_Q', 'QT_vs_Q', 'QTL_vs_Q')
        for k, v in report['comparisons'][a]['evidence'].items()})
    report['coverage'] = {s: dict(Counter(r[s+'_audit']['status'] for race in oos for r in race['rows']))
                          for s in ('Q', 'QT')}
    report['new_coverage_venues'] = dict(Counter(r['QT_audit']['previous_key'][0]
        for race in oos for r in race['rows'] if r['QT_audit']['status'] == 'observed'
        and r['Q_audit']['status'] != 'observed'))
    report['uncovered_venues'] = dict(Counter(r['Q_audit']['previous_key'][0]
        for race in oos for r in race['rows'] if r['Q_audit']['status'] == 'latest_run_uncovered'))
    report['field_buckets'] = {a: _counts_by_field(oos, lambda r: r[a]) for a in ('Q', 'QL', 'QT', 'QTL')}
    def distance_group(race):
        d = int(re.search(r'\d+', str(race['rows'][0]['distance']))[0])
        return 'short' if d <= 1200 else 'middle' if d <= 1700 else 'staying'
    groupers = {'distance': distance_group, 'going': lambda r: r['rows'][0].get('going') or 'unknown',
        'venue': lambda r: re.sub(r'^\d{4}-\d{2}-\d{2}\s*', '', r['meeting']).split(' Race ')[0],
        'top_pick_result_sp': lambda r: str(next((b for b in (3, 6, 11, 21)
        if float(max(r['rows'], key=lambda x: x['Q']).get('sp') or 999) < b), '21+'))}
    report['cohorts'] = {}
    for name, grouper in groupers.items():
        groups = defaultdict(list)
        for race in oos:
            groups[grouper(race)].append(race)
        report['cohorts'][name] = {g: {'races': len(rr), **{a: _counts(rr, lambda r: r[a])
            for a in ('Q', 'QL', 'QT', 'QTL')}} for g, rr in groups.items()}
    args.out.write_text(json.dumps(report, indent=2))
    args.out.with_suffix('.predictions.json').write_text(json.dumps({'races': oos}))
    print(json.dumps({'counts': report['counts'], 'coverage': report['coverage']}), flush=True)


if __name__ == '__main__':
    main()
