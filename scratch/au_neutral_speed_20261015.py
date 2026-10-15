#!/usr/bin/env python3
"""EXP-20261015-08 locked retrospective research; no production writes."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.agents/skills/au_racing/au_wong_choi_auto/scripts'))
from au_eval import _counts, _counts_by_field, _stage4_metric_rows  # noqa: E402
from au_leaf_power import within_race_auc  # noqa: E402
from au_matrix_refit import Dataset, DIMS  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402
from model_evaluation_decision import evaluate_full_record, holm_adjust  # noqa: E402

LEAVES = ('pace_figure_score', 'performance_quality_score', 'form_score',
          'rating_score', 'jockey_score', 'trainer_score')
METRICS = ('gold', 'good_positional', 'top3_capture_at5', 'mean_top3_model_rank',
           'competitive_recall_at5', 'ndcg_at5', 'top5_pairwise_auc')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table(races, scores):
    """Same canonical place objective as existing cutoff-refit accelerator."""
    result = np.empty((len(scores), len(races), 4))
    start = 0
    for i, race in enumerate(races):
        width = len(race['rows'])
        order = np.argsort(-scores[:, start:start+width], axis=1, kind='stable')
        placed = np.array([r['pos'] <= 3 for r in race['rows']])
        hits = placed[order]
        h3 = hits[:, :3].sum(axis=1)
        result[:, i, 0] = hits[:, :4].sum(axis=1) == placed.sum()
        result[:, i, 1] = hits[:, :2].all(axis=1)
        result[:, i, 2] = h3 >= 2
        result[:, i, 3] = h3 / 3
        start += width
    return result


def estimate(daily, paired=False):
    a = np.array(daily, dtype=float)
    if not len(a) or not a[:, 1].sum():
        return {'pairs': 0, 'value': None, 'ci95': None}
    chosen = np.random.default_rng(7).integers(0, len(a), (2000, len(a)))
    summed = a[chosen].sum(axis=1)
    values = summed[:, 0] / np.maximum(summed[:, 1], 1)
    value = a[:, 0].sum() / a[:, 1].sum()
    return {'pairs': int(a[:, 1].sum()), 'value': float(value),
            'ci95': np.quantile(values, [.025, .975]).tolist(),
            'p_two_sided': float(min(1, 2*min(np.mean(values <= (0 if paired else .5)),
                                           np.mean(values >= (0 if paired else .5))))),
            'six_blocks': [float(b[:, 0].sum()/b[:, 1].sum()) if b[:, 1].sum() else None
                           for b in np.array_split(a, 6)]}


def auc(races, key, leaf=None):
    daily = defaultdict(lambda: np.zeros(2))
    other = defaultdict(lambda: np.zeros(2))
    covered = compared = 0
    for race in races:
        rows = [r for r in race['rows'] if r['context_speed'][key] is not None
                and (leaf is None or r['features'][leaf] != 60)]
        covered += len(rows)
        c, n = within_race_auc([(r['context_speed'][key], r['pos'] <= 3) for r in rows])
        daily[race['date']] += [c, n]
        compared += n > 0
        if leaf:
            c2, n2 = within_race_auc([(r['features'][leaf], r['pos'] <= 3) for r in rows])
            assert n == n2
            other[race['date']] += [c2, n2]
    days = sorted(daily)
    out = {'covered': covered, 'races_compared': compared,
           'speed': estimate([daily[d] for d in days])}
    if leaf:
        out['leaf'] = estimate([other[d] for d in days])
        out['speed_minus_leaf'] = estimate([[daily[d][0]-other[d][0], daily[d][1]]
                                             for d in days], paired=True)
    return out


def diff(races, baseline, candidate):
    bm = _stage4_metric_rows(races, lambda r: r[baseline])
    cm = _stage4_metric_rows(races, lambda r: r[candidate])
    days = sorted({r['date'] for r in races})
    evidence = {}
    for metric in METRICS:
        daily = defaultdict(lambda: np.zeros(2))
        for race, b, c in zip(races, bm, cm):
            if b[metric] is not None and c[metric] is not None:
                daily[race['date']] += [c[metric]-b[metric], 1]
        item = estimate([daily[d] for d in days], paired=True)
        evidence[metric] = item
    decision = evaluate_full_record(domain='au', mode='walk_forward_oos',
        dates=[r['date'] for r in races], baseline_rows=bm, candidate_rows=cm,
        leakage_audit_passed=False)
    return {'baseline': _counts(races, lambda r: r[baseline]),
            'candidate': _counts(races, lambda r: r[candidate]),
            'evidence': evidence, 'decision': decision}


def score(mx, weights, overlays):
    # Match ordered production summation and Python rounding, not BLAS reductions.
    delta = np.zeros(len(mx))
    for j, weight in enumerate(weights):
        delta += (mx[:, j]-60)*float(weight)
    return np.array([round(round(float(60+d), 4)+float(o), 4)
                     for d, o in zip(delta, overlays)])


def fit(races, mx, overlays, reference, names):
    """Only prior-date feature/label arrays are passed by caller."""
    proposals = np.random.default_rng(7).dirichlet(np.ones(mx.shape[1]), 512)
    proposals *= sum(MATRIX_WEIGHTS.values())
    scores = np.array([score(mx, w, overlays) for w in proposals])
    values = table(races, scores)
    base = table(races, reference[None, :])[0]
    means = values.mean(axis=1)
    good = ((means[:, 0] >= base[:, 0].mean()) &
            (means[:, 1] >= base[:, 1].mean()) & (means.mean(axis=1) > base.mean()))
    days = sorted({r['date'] for r in races})
    groups = [[i for i, r in enumerate(races) if r['date'] in chunk]
              for chunk in np.array_split(days, 5)]
    wins = sum(values[:, g, :].mean(axis=(1, 2)) >= base[g].mean() for g in groups)
    good &= wins >= 4
    count = int(good.sum())
    meta = {'accepted_proposals': count, 'training_races': len(races),
            'train_through': max(days), 'fallback': None}
    if not count:
        meta['fallback'] = 'no_qualified_proposal'
        return None, meta
    weights = np.median(proposals[good], axis=0)
    weights *= sum(MATRIX_WEIGHTS.values()) / weights.sum()
    consensus = table(races, score(mx, weights, overlays)[None, :])[0]
    if (np.any(consensus.mean(axis=0)[:2] < base.mean(axis=0)[:2]) or
            consensus.mean() <= base.mean() or
            sum(consensus[g].mean() >= base[g].mean() for g in groups) < 4):
        meta['fallback'] = 'consensus_failed_gate'
        return None, meta
    meta['weights'] = dict(zip(names, map(float, weights)))
    return weights, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--leaves', type=Path, required=True)
    ap.add_argument('--context', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    current = json.loads(args.leaves.read_text())['races']
    frozen = json.loads(args.context.read_text())['races']
    key = lambda r: (r['date'], r['meeting'], r['race'])
    index = {key(r): r for r in current}
    assert len(index) == len(current)
    races = []
    max_old_diff = 0.
    for old in frozen:
        if not '2026-08-05' <= old['date'] <= '2026-10-14':
            continue
        new = index.get(key(old))
        assert new is not None, key(old)
        oldrows = sorted(old['rows'], key=lambda r: r['n'])
        newrows = sorted(new['rows'], key=lambda r: r['n'])
        assert [(r['n'], r['name'], r['pos']) for r in oldrows] == [
            (r['n'], r['name'], r['pos']) for r in newrows], key(old)
        new['rows'] = newrows
        for row, prior in zip(newrows, oldrows):
            max_old_diff = max(max_old_diff, abs(row['ability']-prior['ability']))
            row.update({k: prior[k] for k in ('context_speed', 'A', 'B', 'gps_runs', 'gps_reliability')})
            row['baseline'] = row['ability']
            row['deployed'] = round(row['ability'] + 1.5*row['A'], 4)
            assert not row.get('full_time', 0), 'Prevent double-counting deployed overlay'
        if sum(r['pos'] <= 3 for r in newrows) >= 3 and any(r['pos'] == 1 for r in newrows):
            races.append(new)
    races.sort(key=key)
    clean = args.out.with_suffix('.inputs.json')
    clean.write_text(json.dumps({'races': races}))
    ds = Dataset(clean)
    mx = ds.dim_matrix()
    original = ds.ability(mx, MATRIX_WEIGHTS)
    error = float(np.max(np.abs(original-ds.engine_ability)))
    assert error < .000051, error
    # Every tie uses horse number because rows were explicitly sorted above.
    fast = table(races, original[None, :])[0].mean(axis=0)*100
    canonical = _counts(races, lambda r: r['baseline'])
    assert np.max(np.abs(fast-np.array([canonical[k] for k in
        ('gold', 'good_positional', 'pass', 't3prec')]))) < 1e-8
    days = sorted({r['date'] for r in races})
    oos = [r for r in races if r['date'] in days[30:]]
    report = {'input_sha256': {'current': sha(args.leaves), 'context': sha(args.context)},
              'races': len(races), 'oos_races': len(oos), 'oos_days': len(days[30:]),
              'range': [days[0], days[-1]], 'engine_replica_error': error,
              'fresh_vs_frozen_max_ability_diff': max_old_diff,
              'leakage_audit': 'FLAG: original historical capture/publication not certified',
              'status': 'RETROSPECTIVE_RESEARCH_ONLY_NO_PROMOTION',
              'standalone': {k: auc(oos, k) for k in ('A', 'B')},
              'matched_leaves': {k: auc(oos, 'A', k) for k in LEAVES}}
    # A constant neutral model must get 0.5 with tied pairs, never horse-number skill.
    assert within_race_auc([(60, True), (60, False)])[0] == .5
    gain_checks = 0
    for race in oos:
        covered = [r for r in race['rows'] if r['context_speed']['A'] is not None]
        a = sorted(covered, key=lambda r: (-r['context_speed']['A'], r['n']))
        b = sorted(covered, key=lambda r: (-10*r['context_speed']['A'], r['n']))
        assert [r['n'] for r in a] == [r['n'] for r in b]
        gain_checks += bool(covered)
    report['neutral_checks'] = {'constant_auc': .5, 'positive_gain_invariant_races': gain_checks,
                                'standalone_other_features': 60, 'standalone_all_overlays': 0}
    report['matched_holm'] = holm_adjust({k: v['speed_minus_leaf']['p_two_sided']
                                        for k, v in report['matched_leaves'].items()})
    def distance(r):
        d = int(re.search(r'\d+', str(r['rows'][0]['distance']))[0])
        return 'short' if d <= 1200 else ('middle' if d <= 1700 else 'staying')
    report['standalone_distance'] = {g: {k: auc([r for r in oos if distance(r) == g], k)
                                         for k in ('A', 'B')} for g in ('short', 'middle', 'staying')}
    print('Standalone done', flush=True)
    # Locked power calculation before evaluating fitted arms.
    power = diff(oos, 'baseline', 'deployed')
    report['component_budget_pre_fit'] = {k: {'budget': abs(v['value']),
        'mde_halfwidth': (v['ci95'][1]-v['ci95'][0])/2,
        'informative': abs(v['value']) >= (v['ci95'][1]-v['ci95'][0])/2}
        for k, v in power['evidence'].items() if k not in ('gold', 'good_positional')}
    report['fixed_deployed_retrospective'] = power
    print('Power done', flush=True)
    ab = np.array([[60+10*r['A'], 60+10*r['B']] for r in ds.rows])
    matrices = {'R0': mx, 'R1': np.column_stack([mx, ab[:, 0]]),
                'R2': np.column_stack([mx, ab])}
    overlays = ds.wet + ds.fixed_overlays
    report['windows'] = []
    for start in range(30, len(days), 7):
        target = days[start:start+7]
        train = [r for r in races if r['date'] < target[0]]
        test = [r for r in races if r['date'] in target]
        ntrain = sum(len(r['rows']) for r in train)
        ntest = sum(len(r['rows']) for r in test)
        window = {'test_dates': target, 'train_through': train[-1]['date'], 'arms': {}}
        assert train[-1]['date'] < min(target)
        for arm, fullmx in matrices.items():
            names = [*DIMS, *(['A'] if arm == 'R1' else ['A', 'B'] if arm == 'R2' else [])]
            weights, meta = fit(train, fullmx[:ntrain], overlays[:ntrain], original[:ntrain], names)
            predictions = (original[ntrain:ntrain+ntest] if weights is None else
                           score(fullmx[ntrain:ntrain+ntest], weights, overlays[ntrain:ntrain+ntest]))
            cursor = 0
            for race in test:
                for row in race['rows']:
                    row[arm] = float(predictions[cursor])
                    cursor += 1
            window['arms'][arm] = meta
            print(target[0], arm, meta, flush=True)
        report['windows'].append(window)
    report['comparisons'] = {f'{c}_vs_{b}': diff(oos, b, c) for b, c in
        [('baseline', 'R0'), ('baseline', 'R1'), ('baseline', 'R2'),
         ('R0', 'R1'), ('R1', 'R2'), ('deployed', 'R1'), ('deployed', 'R2')]}
    report['family_holm'] = holm_adjust({f'{arm}:{k}': v['p_two_sided']
        for arm in ('R0_vs_baseline', 'R1_vs_baseline', 'R2_vs_baseline')
        for k, v in report['comparisons'][arm]['evidence'].items()})
    report['cohorts'] = {}
    groupers = {'distance': distance, 'going': lambda r: r['rows'][0].get('going') or 'unknown',
        'venue': lambda r: re.sub(r'^\d{4}-\d{2}-\d{2}\s*', '', r['meeting']).split(' Race ')[0],
        'top_pick_result_sp': lambda r: str(next((bound for bound in (3, 6, 11, 21)
             if float(max(r['rows'], key=lambda x: x['baseline']).get('sp') or 999) < bound), '21+'))}
    for label, grouper in groupers.items():
        groups = defaultdict(list)
        for race in oos:
            groups[grouper(race)].append(race)
        report['cohorts'][label] = {g: {'races': len(rr), **{arm: _counts(rr, lambda r: r[arm])
             for arm in ('baseline', 'deployed', 'R0', 'R1', 'R2')}} for g, rr in groups.items()}
    report['field_buckets'] = {arm: _counts_by_field(oos, lambda r: r[arm])
                               for arm in ('baseline', 'deployed', 'R0', 'R1', 'R2')}
    args.out.write_text(json.dumps(report, indent=2))
    args.out.with_suffix('.predictions.json').write_text(json.dumps({'races': oos}))
    print('Wrote', args.out, flush=True)


if __name__ == '__main__':
    main()
