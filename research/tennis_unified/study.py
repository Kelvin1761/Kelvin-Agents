"""Locked offline development runner. No production DB, providers or pricing writes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from .features import BASE_FEATURES, SERVE_ARMS, make_features
from .warehouse import digest, storage_guard, write_new

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / 'protocol_f03_f09.json'


def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -40, 40)))


def losses(y, p):
    p = np.clip(np.asarray(p), .02, .98)
    return np.column_stack((-(y * np.log(p) + (1 - y) * np.log1p(-p)), (p - y) ** 2))


def fit(x, y):
    scale = np.std(x, axis=0)
    scale[scale == 0] = 1.
    z = x / scale
    beta = np.zeros(x.shape[1])
    for iteration in range(100):
        p = sigmoid(z @ beta)
        gradient = z.T @ (p - y) + beta
        hessian = z.T @ ((p * (1 - p))[:, None] * z) + np.eye(len(beta))
        step = np.linalg.solve(hessian, gradient)
        beta -= step
        if np.max(np.abs(step)) < 1e-10:
            if not np.isfinite(beta).all():
                raise ValueError('nonfinite coefficients')
            return {'scale': scale.tolist(), 'beta': beta.tolist(), 'iterations': iteration + 1}
    raise ValueError('FIT_ERROR: Newton did not converge under frozen recipe')


def predict(x, fitted):
    return np.clip(sigmoid((x / np.array(fitted['scale'])) @ np.array(fitted['beta'])), .02, .98)


def calibration(y, p):
    bins, ece = [], 0.
    for index in range(10):
        mask = (p >= index / 10) & (p < (index + 1) / 10 if index < 9 else p <= 1)
        n = int(mask.sum())
        mean = float(p[mask].mean()) if n else None
        observed = float(y[mask].mean()) if n else None
        bins.append({'lower': index / 10, 'upper': (index + 1) / 10, 'n': n,
                     'probability': mean, 'observed': observed})
        if n:
            ece += n / len(y) * abs(mean - observed)
    x = np.column_stack((np.ones(len(p)), np.log(p / (1 - p))))
    beta, converged = np.zeros(2), False
    for _ in range(100):
        q = sigmoid(x @ beta)
        try:
            step = np.linalg.solve(x.T @ ((q * (1 - q))[:, None] * x), x.T @ (q - y))
        except np.linalg.LinAlgError:
            break
        beta -= step
        if np.max(np.abs(step)) < 1e-10:
            converged = True
            break
    return {'ece_10_equal_width': float(ece), 'bins': bins,
            'intercept': float(beta[0]) if converged else None,
            'slope': float(beta[1]) if converged else None,
            'slope_status': 'converged' if converged else 'unidentified_or_not_converged'}


def metrics(y, p):
    v = losses(y, p)
    return {'n': len(y), 'log_loss': float(v[:, 0].mean()), 'brier': float(v[:, 1].mean()),
            'accuracy': float(((p >= .5) == y).mean()), 'calibration': calibration(y, p)}


def holm(p_values):
    ordered = sorted(p_values, key=lambda k: (p_values[k], k))
    maximum, adjusted = 0., {}
    for i, name in enumerate(ordered):
        maximum = max(maximum, (len(ordered) - i) * p_values[name])
        adjusted[name] = min(1., maximum)
    return adjusted


def paired_bootstrap(deltas, trials=4000, seed=20260826):
    """Bounded memory, same match resamples for every predeclared comparison."""
    rng = np.random.default_rng(seed)
    n = len(deltas)
    if n == 0 or not np.isfinite(deltas).all():
        raise ValueError('invalid paired losses')
    means = []
    for start in range(0, trials, 32):
        count = min(32, trials - start)
        weights = np.stack([np.bincount(rng.integers(n, size=n), minlength=n) for _ in range(count)])
        means.append(weights @ deltas / n)
    samples = np.concatenate(means)
    observed = deltas.mean(axis=0)
    bounds = np.quantile(samples, [.025, .975], axis=0)
    p = (1 + (np.abs(samples - observed) >= np.abs(observed)).sum(axis=0)) / (trials + 1)
    return samples, observed, bounds, p


def prepare(cohort, output):
    data = json.loads(cohort.read_text())
    rows, priors = make_features(data['rows'])
    if any(not np.isfinite(list(r['x'].values())).all() for r in rows):
        raise ValueError('nonfinite feature input')
    if any(r['max_history_available'] is not None and r['max_history_available'] >= r['date'] for r in rows):
        raise ValueError('history cutoff failed')
    payload = {'schema': 'tennis-unified-features/v1', 'cohort_sha256': digest(cohort),
               'split_status': 'SEEN_DEV', 'pit_verified': False, 'priors': priors,
               'row_count': len(rows), 'rows': rows}
    write_new(output, payload)
    print(json.dumps({'feature_rows': len(rows), 'features_sha256': digest(output), 'pit_verified': False}))


def method_hashes():
    return {p.name: digest(p) for p in (HERE / 'history.py', HERE / 'features.py', HERE / 'warehouse.py', Path(__file__), PROTOCOL)}


def validate_inputs(cohort, features, protocol):
    if features['cohort_sha256'] != digest(cohort):
        raise ValueError('features came from a different cohort')
    data = json.loads(cohort.read_text())
    if [s['raw_id'] for s in data['sources']] != protocol['source_raw_ids']:
        raise ValueError('raw source roster mismatch')
    expected = {r['key']: r for r in data['rows'] if r['date'] >= protocol['train_start']}
    rows = features['rows']
    if len(expected) != len(rows) or len({r['key'] for r in rows}) != len(rows):
        raise ValueError('feature/cohort population mismatch')
    for r in rows:
        source = expected.get(r['key'])
        if source is None or any(r[k] != source[k] for k in ('date', 'available', 'tour', 'surface', 'level', 'best_of', 'y')):
            raise ValueError('feature/cohort identity or label mismatch')
        if r['max_history_available'] is not None and r['max_history_available'] >= r['date']:
            raise ValueError('future history in locked cohort')
        if not np.isfinite(list(r['x'].values())).all():
            raise ValueError('nonfinite features')


def lock(cohort, features, test_log, output):
    storage_guard(output)
    if not cohort.is_file() or not features.is_file() or not test_log.is_file():
        raise ValueError('missing data or prerequisite test evidence')
    text = test_log.read_text()
    if 'passed' not in text or 'failed' in text.lower() or 'error' in text.lower():
        raise ValueError('prerequisite test log not passing')
    proto = json.loads(PROTOCOL.read_text())
    if len(proto['comparisons']) != 38 or len({c[0] for c in proto['comparisons']}) != 38:
        raise ValueError('comparison roster changed')
    validate_inputs(cohort, json.loads(features.read_text()), proto)
    payload = {'schema': 'tennis-unified-development-lock/v1', 'locked_at': datetime.now(timezone.utc).isoformat(),
               'candidate_outcomes_inspected': False, 'cohort': str(cohort), 'cohort_sha256': digest(cohort),
               'features': str(features), 'features_sha256': digest(features),
               'test_log': str(test_log), 'test_log_sha256': digest(test_log),
               'methods': method_hashes(), 'protocol': proto,
               'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
               'git_status': subprocess.check_output(['git', 'status', '--short'], text=True),
               'python': sys.version, 'numpy': np.__version__, 'promotion_eligible': False}
    write_new(output, payload)
    print(json.dumps({'locked_at': payload['locked_at'], 'lock_sha256': digest(output), 'tests': 76}))


def model_specs():
    base = list(BASE_FEATURES)
    specs = {'elo_fit': ['elo'], 'simple': base, 'strength': base + ['strength'],
             'h2h_raw': ['elo', 'h2h_raw'], 'h2h_residual': ['elo', 'h2h_residual']}
    specs.update({'serve_' + a: base + ['serve_' + a, 'return_' + a] for a in SERVE_ARMS})
    return specs


def run(lock_path, output):
    storage_guard(output)
    protocol_lock = json.loads(lock_path.read_text())
    if protocol_lock['methods'] != method_hashes():
        raise ValueError('method changed after lock; do not run candidates')
    for label in ('cohort', 'features', 'test_log'):
        if digest(Path(protocol_lock[label])) != protocol_lock[label + '_sha256']:
            raise ValueError('locked input changed: ' + label)
    output.mkdir(exist_ok=False)
    protocol = protocol_lock['protocol']
    feature_data = json.loads(Path(protocol_lock['features']).read_text())
    validate_inputs(Path(protocol_lock['cohort']), feature_data, protocol)
    rows, specs = feature_data['rows'], model_specs()
    fold_reports, predictions = [], []
    for start, end in protocol['folds']:
        train = [r for r in rows if protocol['train_start'] <= r['date'] and r['available'] < start]
        test = [r for r in rows if start <= r['date'] < end]
        if len(train) < 600 or not test:
            raise ValueError('fixed fold incomplete')
        y_train, y_test = np.array([r['y'] for r in train]), np.array([r['y'] for r in test])
        values = {'fixed_elo': np.clip(sigmoid(np.array([r['x']['elo'] for r in test])), .02, .98),
                  'surface_dynamic': np.clip(sigmoid(np.array([r['x']['surface_dynamic'] for r in test])), .02, .98)}
        models = {}
        for arm, names in specs.items():
            x_train = np.array([[r['x'][name] for name in names] for r in train])
            x_test = np.array([[r['x'][name] for name in names] for r in test])
            fitted = fit(x_train, y_train)
            p = predict(x_test, fitted)
            if np.max(np.abs(p + predict(-x_test, fitted) - 1)) > 1e-10:
                raise ValueError('swap invariant failed')
            values[arm] = p
            models[arm] = dict(fitted, features=names)
        report = {'window': [start, end], 'train_n': len(train), 'test_n': len(test),
                  'max_training_label_available': max(r['available'] for r in train),
                  'models': models, 'metrics': {a: metrics(y_test, p) for a, p in values.items()}}
        write_new(output / (start + '-fold.json'), report)
        fold_reports.append(report)
        for index, row in enumerate(test):
            predictions.append({k: row[k] for k in ('key', 'date', 'tour', 'surface', 'level', 'best_of', 'y', 'n_a', 'n_b', 'a_profile_n', 'b_profile_n')} |
                               {'fold': start, 'p': {a: float(p[index]) for a, p in values.items()}})
        print(json.dumps({'fold': start, 'test_n': len(test), 'status': 'predictions_saved'}), flush=True)
    with (output / 'predictions.jsonl').open('x') as stream:
        for row in predictions:
            stream.write(json.dumps(row, separators=(',', ':')) + '\n')
    summary = summarise(predictions, fold_reports, protocol, output)
    summary.update({'schema': 'tennis-unified-development-result/v1', 'protocol_lock_sha256': digest(lock_path),
                    'completed_at': datetime.now(timezone.utc).isoformat(), 'split_status': 'SEEN_DEV',
                    'pit_verified': False, 'promotion_eligible': False,
                    'B_live': 'N/A: full live feature provenance unavailable on this cohort',
                    'B_market': 'N/A: fixed5-fold paired price corpus incomplete',
                    'roi_clv': 'N/A: no price/contract observations in this isolated cohort',
                    'parquet': 'NOT_YET_EXPORTED: JSONL retained losslessly; pyarrow absent from verified runtime'})
    write_new(output / 'summary.json', summary)
    write_new(output / 'artifact_manifest.json', {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()})
    print(json.dumps({'results': str(output / 'summary.json'), 'n': len(predictions), 'promotion_eligible': False}))


def summarise(rows, folds, protocol, output):
    y = np.array([r['y'] for r in rows])
    arms = list(rows[0]['p'])
    p = {arm: np.array([r['p'][arm] for r in rows]) for arm in arms}
    vectors = {arm: losses(y, v) for arm, v in p.items()}
    available = [(name, cand, control) for name, cand, control in protocol['comparisons'] if cand in vectors and control in vectors]
    deltas = np.column_stack([vectors[control][:, m] - vectors[cand][:, m]
                             for _, cand, control in available for m in range(2)])
    samples, observed, bounds, pv = paired_bootstrap(deltas)
    with (output / 'paired_bootstrap_means.npy').open('xb') as stream:
        np.save(stream, samples, allow_pickle=False)
    all_p = {name + ':' + metric: 1. for name, _, _ in protocol['comparisons'] for metric in ('log_loss', 'brier')}
    comparisons = {}
    for index, (name, cand, control) in enumerate(available):
        result = {'candidate': cand, 'control': control, 'n': len(rows), 'metrics': {}}
        for m, metric in enumerate(('log_loss', 'brier')):
            column = 2 * index + m
            fold_gains = [f['metrics'][control][metric] - f['metrics'][cand][metric] for f in folds]
            result['metrics'][metric] = {'gain': float(observed[column]), 'ci95': bounds[:, column].tolist(),
                                         'p_raw': float(pv[column]), 'fold_gains': fold_gains,
                                         'nonworsening_folds': sum(v >= 0 for v in fold_gains)}
            all_p[name + ':' + metric] = float(pv[column])
        comparisons[name] = result
    adjusted = holm(all_p)
    for name, result in comparisons.items():
        for metric, value in result['metrics'].items():
            value['p_holm_76'] = adjusted[name + ':' + metric]
        effect_passed = all(v['gain'] > 0 and v['nonworsening_folds'] == 5 for v in result['metrics'].values())
        supported = all(v['p_holm_76'] <= .05 for v in result['metrics'].values())
        result['decision'] = ('ADVANCE_DEV_ONLY' if supported else 'PENDING_MULTIPLICITY_FAMILY') if effect_passed else 'REJECT_DEV'
    for name, cand, control in protocol['comparisons']:
        if name not in comparisons:
            reason = 'DEFERRED_RECIPE_NOT_FITTED'
            if cand in ('power', 'shin', 'inner_devig', 'offset'):
                reason = 'MISSING_FIXED_FOLD_PRICE_SOURCE'
            elif cand in ('minutes', 'sets_hours', 'workload_both'):
                reason = 'MISSING_ACTUAL_MATCH_AND_END_TIMES'
            comparisons[name] = {'candidate': cand, 'control': control, 'status': reason, 'p_for_family': 1.}
    subgroups = {}
    for field in ('tour', 'surface', 'level', 'best_of'):
        for value in sorted({r[field] for r in rows}, key=str):
            mask = np.array([r[field] == value for r in rows])
            subgroups[field + ':' + str(value)] = {a: metrics(y[mask], v[mask]) for a, v in p.items()}
    for label, mask in (
            ('history:0', np.array([min(r['n_a'], r['n_b']) == 0 for r in rows])),
            ('history:1-4', np.array([1 <= min(r['n_a'], r['n_b']) <= 4 for r in rows])),
            ('history:5-19', np.array([5 <= min(r['n_a'], r['n_b']) <= 19 for r in rows])),
            ('history:20+', np.array([min(r['n_a'], r['n_b']) >= 20 for r in rows])),
            ('serve:missing_prior', np.array([min(r['a_profile_n'], r['b_profile_n']) == 0 for r in rows]))):
        if mask.any():
            subgroups[label] = {a: metrics(y[mask], v[mask]) for a, v in p.items()}
    arm_decisions = {}
    required = {'surface_dynamic': ['surface_dynamic_vs_fixed'], 'strength': ['strength_vs_simple'],
                'h2h_residual': ['h2h_residual_vs_elo', 'h2h_residual_vs_raw']}
    for arm in SERVE_ARMS[1:]:
        required['serve_' + arm] = ['serve_' + arm + '_vs_000', 'serve_' + arm + '_vs_simple']
    required['serve_RES'] += ['serve_RES_vs_RE', 'serve_RES_vs_RS', 'serve_RES_vs_ES']
    for arm, names in required.items():
        decisions = [comparisons[name]['decision'] for name in names]
        arm_decisions[arm] = {'required_comparisons': names,
                              'decision': 'REJECT_DEV' if 'REJECT_DEV' in decisions else
                              ('ADVANCE_DEV_ONLY' if all(d == 'ADVANCE_DEV_ONLY' for d in decisions) else 'PENDING_MULTIPLICITY_FAMILY')}
    return {'n': len(rows), 'folds': [{k: v for k, v in f.items() if k != 'models'} for f in folds],
            'metrics': {a: metrics(y, v) for a, v in p.items()}, 'comparisons': comparisons,
            'arm_decisions': arm_decisions, 'subgroups': subgroups, 'holm_tests': len(all_p),
            'remaining_slots_keep_p_one': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--cohort', type=Path, required=True)
    prep.add_argument('--output', type=Path, required=True)
    lk = commands.add_parser('lock')
    lk.add_argument('--cohort', type=Path, required=True)
    lk.add_argument('--features', type=Path, required=True)
    lk.add_argument('--test-log', type=Path, required=True)
    lk.add_argument('--output', type=Path, required=True)
    execute = commands.add_parser('run')
    execute.add_argument('--lock', type=Path, required=True)
    execute.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.cohort, args.output)
    elif args.command == 'lock':
        lock(args.cohort, args.features, args.test_log, args.output)
    else:
        run(args.lock, args.output)


if __name__ == '__main__':
    main()
