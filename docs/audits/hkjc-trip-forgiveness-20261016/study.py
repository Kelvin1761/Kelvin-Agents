"""Paired fixed-rule trip experiment. No production or archive writes."""
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

import arm
import replay as r
from hkjc_racing_engine.engine_core import DrawScorer
from model_evaluation_decision import holm_adjust
from wongchoi_paths import HK_RACING

FOLDER = Path(__file__).parent
OUT = Path('/private/tmp/hkjc-trip-20261016-study')
BASE = Path('/private/tmp/hkjc-draw-20261016-baseline.jsonl')
EVIDENCE = Path('/private/tmp/hkjc-draw-20261016-evidence.jsonl')
ARMS = ('winner', 'close_top3', 'neutral_trip')


def candidate(ev, name, original):
    horses = r.prepare(ev)
    changed, segments, deltas = 0, 0, []
    for horse in horses.values():
        engine = r.RacingEngine(horse, ev['context'])
        _, count = arm.transformed(engine, name)
        if name == 'neutral_trip' and engine._is_sha_tin_context() and not engine._is_debut():
            count = 1
        if not count:
            continue
        old = original(engine)[0]
        new = arm.score_trip(engine, name, original)[0]
        auto = horse['python_auto']
        if old == new:
            continue
        changed += 1
        segments += count
        deltas.append(new-old)
        features = dict(auto['feature_scores'])
        features['draw_score'] = DrawScorer(horse, ev['context']).compute()[0]
        saved = r.RacingEngine._trip_consumption_score
        try:
            r.RacingEngine._trip_consumption_score = lambda self: arm.score_trip(self, name, original)
            shape = engine._race_shape_context_score(features)[0]
        finally:
            r.RacingEngine._trip_consumption_score = saved
        auto['matrix_scores']['race_shape'] = round(shape, 2)
    scored = r.score(horses)
    return scored, {'changed_runners': changed, 'changed_segments': segments, 'trip_deltas': deltas}


def describe(base, cand):
    report = r.screen(base, cand, 'fixed_rule')
    report['changed_races'] = sum(b['picks'] != c['picks'] for b, c in zip(base, cand))
    report['cohorts'] = {}
    tests = {'ST_turf': lambda x: x['venue'] == '沙田' and not x['awt'],
             'HV': lambda x: x['venue'] == '跑馬地', 'AWT': lambda x: x['awt'],
             'unknown_venue': lambda x: not x['venue'], 'has_debut': lambda x: x['has_debut']}
    for bucket in ('le8', '9_10', '11_12', '13plus'):
        tests['field_'+bucket] = lambda x, bucket=bucket: r.field_bucket(x['field']) == bucket
    for label, low, high in (('sp1_3', 0, 3), ('sp3_7', 3, 7), ('sp7_15', 7, 15), ('sp15_30', 15, 30), ('sp30plus', 30, float('inf'))):
        tests[label] = lambda x, low=low, high=high: x['sp'] is not None and low < x['sp'] <= high
    for going in sorted({b['going'] for b in base}):
        tests['going_'+going] = lambda x, going=going: x['going'] == going
    from model_evaluation_decision import _full_record_metric
    for label, test in tests.items():
        ix = [i for i, b in enumerate(base) if test(b)]
        if not ix:
            continue
        stats = {}
        for k in r.METRICS[:2]:
            stats[k] = vars(_full_record_metric([base[i][k] for i in ix], [cand[i][k] for i in ix],
                       [base[i]['date'] for i in ix], higher_is_better=True, blocks=6, bootstrap=2000, seed=7))
        report['cohorts'][label] = {'races': len(ix), 'primary': stats}
    return report


def main():
    OUT.mkdir(exist_ok=True)
    keys = {tuple(x) for x in json.loads((FOLDER/'canonical_keys.json').read_text())}
    bases = [b for b in r.read(BASE) if (b['meeting'], b['race']) in keys]
    assert len(bases) == len(keys) == 325
    evs = {(e['meeting'], e['race']): e for e in r.read(EVIDENCE)}
    rows = {name: [] for name in ('aa', *ARMS)}
    coverage = Counter()
    original = r.RacingEngine._trip_consumption_score
    targets = {a: [] for a in ARMS}
    source_cache = {}
    # Baseline, sample metadata and component budget before candidate outcomes.
    for base in bases:
        ev = evs[(base['meeting'], base['race'])]
        horses = r.prepare(ev)
        aa = r.score(copy.deepcopy(horses))
        assert r.ranked(aa) == base['picks']
        assert all(abs(aa[n]['python_auto']['ability_score_raw'] - ev['horses'][n]['auto']['ability_score_raw']) < 1e-6 for n in aa)
        venue, track, distance = r.identity(ev['context'])
        base.update(venue=venue, awt=track == 'AWT', distance=distance,
                    has_debut=any(r.RacingEngine(h, ev['context'])._is_debut() for h in horses.values()),
                    going=str(ev['context'].get('going') or ev['context'].get('track_condition') or 'unknown'))
        if base['meeting'] not in source_cache:
            files = list((Path(HK_RACING)/base['meeting']).glob('*全日賽果.json'))
            source_cache[base['meeting']] = json.loads(files[0].read_text()) if files else {}
        actual = next((v for k, v in source_cache[base['meeting']].items() if isinstance(v, dict) and r.integer(v.get('race_no') or k) == base['race']), {})
        first = next((h for h in actual.get('results', []) if r.integer(h.get('horse_no')) == base['picks'][0]), {})
        try:
            base['sp'] = float(first.get('win_odds'))
        except (TypeError, ValueError):
            base['sp'] = None
        rows['aa'].append(r.row_for(base, aa, 'aa'))
        neutral, _ = candidate(ev, 'neutral_trip', original)
        rows['neutral_trip'].append(r.row_for(base, neutral, 'neutral_trip'))
    aa_screen = r.screen(bases, rows['aa'], 'fixed_rule')
    assert aa_screen['verdict'] == 'REJECT'
    power = r.screen(bases, rows['neutral_trip'], 'fixed_rule')
    (OUT/'power_before_candidates.json').write_text(json.dumps({'aa': aa_screen, 'budget': power}, indent=2)+'\n')
    rows['neutral_trip'] = []
    changes = {a: [] for a in ARMS}
    for base in bases:
        ev = evs[(base['meeting'], base['race'])]
        for name in ARMS:
            horses, counts = candidate(ev, name, original)
            row = r.row_for(base, horses, name)
            row['raw_scores'] = {n: h['python_auto']['ability_score_raw'] for n, h in horses.items()}
            rows[name].append(row)
            coverage[name+'_runner_appearances'] += counts['changed_runners']
            coverage[name+'_prior_run_references'] += counts['changed_segments']
            if counts['changed_runners']:
                targets[name].append([base['meeting'], base['race']])
            changes[name].append({'meeting': base['meeting'], 'race': base['race'], **counts})
    reports = {name: describe(bases, rows[name]) for name in ARMS}
    pvalues = {name+':'+key: metric['p_value'] for name in ARMS for block in ('primary', 'ranking')
               for key, metric in reports[name]['detail'][block].items()}
    for name, rr in rows.items():
        (OUT/(name+'.jsonl')).write_text(''.join(json.dumps(x, ensure_ascii=False)+'\n' for x in rr))
    result = {'baseline_commit': '3083316d55fd35d798772514248ae2723e6b469b',
              'baseline_capture_commit': '2d7ec14c09a3d6fa0bc5733406a730f7dff344ff', 'aa_exact': True,
              'races': len(bases), 'dates': sorted({b['date'] for b in bases}),
              'baseline': {k: sum(float(b[k]) for b in bases)/len(bases) for k in r.METRICS},
              'coverage': dict(coverage), 'targets': targets, 'changes': changes,
              'arms': reports, 'holm': holm_adjust(pvalues), 'power': power,
              'source_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (BASE, EVIDENCE)},
              'leakage': 'FLAG: strict historical run dates enforced; historical artifact availability not fully certified',
              'forward': '2026-10-11 onward untouched'}
    for name in ARMS:
        result['arms'][name]['ranking_power'] = {k: {
            'budget': abs(power['detail']['ranking'][k]['delta']),
            'paired_ci_halfwidth': (m['ci_high']-m['ci_low'])/2,
            'informative': abs(power['detail']['ranking'][k]['delta']) >= (m['ci_high']-m['ci_low'])/2}
            for k, m in reports[name]['detail']['ranking'].items()}
    for name in ARMS:
        raw = reports[name]['verdict']
        metrics = reports[name]['detail'].get('winning_metrics' if raw == 'PRIMARY_WIN' else 'ci_supported_metrics', [])
        supported = [k for k in metrics if result['holm'][name+':'+k] <= .05]
        result['arms'][name]['holm_supported_metrics'] = supported
        result['arms'][name]['family_decision'] = 'REJECT / holm_not_supported' if raw.endswith('_WIN') and not supported else raw+' / '+reports[name]['reason']
    (OUT/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'coverage': dict(coverage), 'arms': {a: {'verdict': x['verdict'], 'reason': x['reason'],
        'changed_races': x['changed_races'], 'primary': x['detail']['primary'], 'ranking': x['detail']['ranking']}
        for a, x in reports.items()}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
