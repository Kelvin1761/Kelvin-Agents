#!/usr/bin/env python3
"""Locked cutoff/refit research; date-forward fits with inherited PIT FLAG.

This is diagnostic research, not source-certified au_oos_predictions intake.
No output is an authorized production weight file.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / '.agents/skills/au_racing/au_wong_choi_auto/scripts'
sys.path.insert(0, str(SCRIPTS))
from au_eval import _stage4_metric_rows, _counts  # noqa: E402
from au_matrix_refit import Dataset, DIMS, dirichlet  # noqa: E402
from au_racing_engine.scoring import compose_matrix_score, MATRIX_WEIGHTS  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from model_evaluation_decision import evaluate_full_record, holm_adjust  # noqa: E402


def exact_score(row, weights):
    pure = round(compose_matrix_score(map_features_to_matrix_scores(row['features']), weights), 4)
    return round(pure + float(row.get('wet') or 0) + float(row.get('proven_class') or 0), 4)


def batch_scores(mx, weights, wet, proof):
    delta = np.zeros((len(weights), len(mx)))
    for j in range(len(DIMS)):
        delta += weights[:, j:j+1] * (mx[None, :, j] - 60.)
    return np.round(np.round(60. + delta, 4) + wet[None, :] + proof[None, :], 4)


def metric_table(races, scores):
    """Canonical place-objective proposal accelerator, verified below.

    Columns are Gold, Good positional, Pass, Top3 precision, in fractions.
    No fitted window receives future labels through this function.
    """
    metrics = np.empty((len(scores), len(races), 4))
    start = 0
    for i, race in enumerate(races):
        rows = race['rows']
        width = len(rows)
        # Dataset order is saddlecloth order, the production tie rule.
        ranked = np.argsort(-scores[:, start:start+width], axis=1, kind='stable')
        placed = np.array([r['pos'] <= 3 for r in rows])
        hits = placed[ranked]
        h3 = hits[:, :3].sum(axis=1)
        metrics[:, i, 0] = hits[:, :4].sum(axis=1) == placed.sum()
        metrics[:, i, 1] = hits[:, :2].all(axis=1)
        metrics[:, i, 2] = h3 >= 2
        metrics[:, i, 3] = h3 / 3.
        start += width
    return metrics


def folds(races):
    dates = sorted({r['date'] for r in races})
    return [[i for i, r in enumerate(races) if r['date'] in set(chunk)]
            for chunk in np.array_split(dates, 5)]


def fit(prefix, mx, wet, proof):
    """Only prior-date races, features and labels enter this call."""
    rng = random.Random(7)
    shipped = [max(MATRIX_WEIGHTS[k], 1e-4) for k in DIMS]
    draws = []
    for i in range(256):
        alpha = [1.] * len(DIMS) if i % 2 == 0 else [max(s * 25., .35) for s in shipped]
        draws.append(dirichlet(rng, alpha))
    weights = np.array([[MATRIX_WEIGHTS[k] for k in DIMS], *draws])
    proposed = metric_table(prefix, batch_scores(mx, weights, wet, proof))
    means = proposed.mean(axis=1)
    eligible = ((means[:, 0] >= means[0, 0]) & (means[:, 1] >= means[0, 1]) &
                (means.mean(axis=1) > means[0].mean()))
    groups = folds(prefix)
    wins = np.zeros(len(weights), dtype=int)
    for group in groups:
        values = proposed[:, group, :].mean(axis=(1, 2))
        wins += values >= values[0]
    eligible &= wins >= 4
    indices = np.flatnonzero(eligible)
    if not len(indices):
        return dict(MATRIX_WEIGHTS), {'accepted_draws': 0, 'fallback': 'no_consensus'}
    consensus = np.median(weights[indices], axis=0)
    consensus *= sum(MATRIX_WEIGHTS.values()) / consensus.sum()
    mapping = dict(zip(DIMS, map(float, consensus)))
    exact = np.array([[exact_score(row, mapping) for race in prefix for row in race['rows']]])
    cm = metric_table(prefix, exact)[0]
    baseline_exact = np.array([[row['ability'] for race in prefix for row in race['rows']]])
    bm = metric_table(prefix, baseline_exact)[0]
    primary_ok = np.all(cm.mean(axis=0)[:2] >= bm.mean(axis=0)[:2])
    objective_ok = cm.mean() > bm.mean()
    block_wins = sum(cm[g].mean() >= bm[g].mean() for g in groups)
    if not (primary_ok and objective_ok and block_wins >= 4):
        return dict(MATRIX_WEIGHTS), {'accepted_draws': len(indices), 'fallback': 'consensus_failed_gate'}
    return mapping, {'accepted_draws': len(indices), 'fallback': None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--prefix', default='/private/tmp/au-trial-cutoff-')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    paths = {n: Path(f'{args.prefix}{n}.json') for n in (2, 4, 6)}
    raw = {n: json.loads(p.read_text())['races'] for n, p in paths.items()}
    original = json.loads(args.baseline.read_text())['races']
    key = lambda r: (r['date'], r['meeting'], r['race'])
    for races in raw.values():
        assert [key(r) for r in original] == [key(r) for r in races]
        for br, cr in zip(original, races):
            assert [(r['n'], r['name'], r['pos']) for r in br['rows']] == [
                (r['n'], r['name'], r['pos']) for r in cr['rows']]
            for b, c in zip(br['rows'], cr['rows']):
                assert b['features']['preparation_score'] == c['features']['preparation_score']
                assert b['features']['jockey_horse_fit_score'] == c['features']['jockey_horse_fit_score']
    valid = [i for i, r in enumerate(original) if sum(x['pos'] <= 3 for x in r['rows']) >= 3
             and any(x['pos'] == 1 for x in r['rows'])]
    original = [original[i] for i in valid]
    raw = {n: [r[i] for i in valid] for n, r in raw.items()}
    # Dataset constructor takes a file; retain a small, reproducible clean-era
    # input per cutoff. No full source corpus copies and no disk artifact >1GB.
    datasets = {}
    for n, races in raw.items():
        clean = [r for r in races if r['date'] >= '2026-08-05']
        for r in clean:
            r['rows'].sort(key=lambda row: row['n'])
        clean_path = paths[n].with_suffix('.clean.json')
        clean_path.write_text(json.dumps({'races': clean}))
        datasets[n] = Dataset(clean_path)
        ds = datasets[n]
        exact = np.array([exact_score(row, MATRIX_WEIGHTS) for row in ds.rows])
        assert np.max(np.abs(exact - ds.engine_ability)) < .000051
        replica = ds.ability(ds.dim_matrix(), MATRIX_WEIGHTS)
        assert np.max(np.abs(replica - exact)) < .000051
        fast = metric_table(ds.races, replica[None, :])[0].mean(axis=0) * 100
        canonical = _counts(ds.races, lambda row: row['ability'])
        assert np.max(np.abs(fast - np.array([canonical[k] for k in
                                               ('gold', 'good_positional', 'pass', 't3prec')]))) < 1e-8

    def diagnostic(base_races, cand_races, mode='fixed_rule'):
        bm = _stage4_metric_rows(base_races, lambda r: r['ability'])
        cm = _stage4_metric_rows(cand_races, lambda r: r['ability'])
        return evaluate_full_record(
            domain='au', mode=mode, dates=[r['date'] for r in base_races],
            baseline_rows=bm, candidate_rows=cm, leakage_audit_passed=True,
            ranking_metrics=('top3_capture_at5', 'ndcg_at5', 'top5_pairwise_auc'))

    result = {'baseline_sha256': hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
              'input_hashes': {str(n): hashlib.sha256(p.read_bytes()).hexdigest() for n, p in paths.items()},
              'source_audit': 'FLAG: input and label publication/capture availability not certified',
              'promotion_authorized': False, 'fixed': {}, 'windows': [], 'oos': {}}
    for n, races in raw.items():
        result['fixed'][str(n)] = {
            'races': len(races), 'counts': _counts(races, lambda r: r['ability']),
            'diagnostic_vs_original': diagnostic(original, races)}
    dates = sorted({r['date'] for r in datasets[6].races})
    oos = {str(n): [] for n in (2, 4, 6)}
    fixed_oos = {str(n): [] for n in (2, 4, 6)}
    policy_oos = []
    for start in range(30, len(dates), 7):
        test_dates = set(dates[start:start+7])
        fit_end = sum(r['date'] < dates[start] for r in datasets[6].races)
        row_end = datasets[6].slices[fit_end-1][1]
        state = {'test_dates': sorted(test_dates), 'train_until': dates[start-1],
                 'training_races': fit_end, 'fits': {}}
        fitted = {}
        train_tables = {}
        for n in (2, 4, 6):
            ds = datasets[n]
            mx = ds.dim_matrix()
            # Different cutoffs retain precisely the same registered runners.
            assert ds.slices == datasets[6].slices
            w, metadata = fit(ds.races[:fit_end], mx[:row_end], ds.wet[:row_end], ds.proven_class[:row_end])
            fitted[n] = w
            state['fits'][str(n)] = {**metadata, 'weights': w}
            train_scores = np.array([[exact_score(row, w) for row in ds.rows[:row_end]]])
            train_tables[n] = metric_table(ds.races[:fit_end], train_scores)[0]
            for race in ds.races:
                if race['date'] not in test_dates:
                    continue
                candidate = deepcopy(race)
                for row in candidate['rows']:
                    row['ability'] = exact_score(row, w)
                oos[str(n)].append(candidate)
                fixed_oos[str(n)].append(deepcopy(race))
        base_train = metric_table(datasets[6].races[:fit_end],
                                 datasets[6].engine_ability[:row_end][None, :])[0]
        groups = folds(datasets[6].races[:fit_end])
        qualified = []
        for n, table in train_tables.items():
            if not (np.all(table.mean(axis=0)[:2] >= base_train.mean(axis=0)[:2])
                    and table.mean() >= base_train.mean()):
                continue
            if all(sum(table[g, j].mean() >= base_train[g, j].mean()
                       for g in groups) >= 4 for j in (0, 1)):
                qualified.append(n)
        selected = min(qualified) if qualified else 6
        fallback = not qualified
        state['policy_cutoff'] = selected
        state['policy_fallback'] = fallback
        source = fixed_oos['6'] if fallback else oos[str(selected)]
        policy_oos.extend(deepcopy(r) for r in source if r['date'] in test_dates)
        result['windows'].append(state)
        print(f"train through {state['train_until']}, {fit_end} races; test {sorted(test_dates)}; "
              f"consensus {[state['fits'][str(n)]['accepted_draws'] for n in (2,4,6)]}; "
              f"policy {selected}, fallback={fallback}", flush=True)

    base = fixed_oos['6']
    for n in (2, 4, 6):
        result['oos'][str(n)] = {
            'counts': _counts(oos[str(n)], lambda r: r['ability']),
            'fixed_counts': _counts(fixed_oos[str(n)], lambda r: r['ability']),
            'diagnostic_vs_fixed6': diagnostic(base, oos[str(n)], 'walk_forward_oos'),
            'refit_marginal': diagnostic(fixed_oos[str(n)], oos[str(n)], 'walk_forward_oos')}
    result['policy'] = {'counts': _counts(policy_oos, lambda r: r['ability']),
                        'baseline_counts': _counts(base, lambda r: r['ability']),
                        'diagnostic': diagnostic(base, policy_oos, 'walk_forward_oos'), 'races': len(base)}
    p_values = {}
    for arm, record in {**result['oos'], 'policy': {'diagnostic_vs_fixed6': result['policy']['diagnostic']}}.items():
        detail = record['diagnostic_vs_fixed6']['detail']
        for section in ('primary', 'ranking'):
            for metric, evidence in detail[section].items():
                p_values[f'{arm}/{metric}'] = evidence['p_value']
    result['holm'] = holm_adjust(p_values)
    result['predictions'] = {'baseline_fixed6': base, 'cutoff_refits': oos, 'policy': policy_oos}
    args.out.write_text(json.dumps(result, indent=2))
    print('saved', args.out, flush=True)


if __name__ == '__main__':
    main()
