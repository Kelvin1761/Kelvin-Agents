"""F09 fixed-feature head comparison; uses the existing 76-test family."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pickle
import sys

import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier

from .features import BASE_FEATURES
from .study import fit, method_hashes, predict, summarise, validate_inputs
from .warehouse import digest, storage_guard, write_new

PARAMETERS = dict(learning_rate=.05, max_iter=200, max_leaf_nodes=7, max_depth=None,
                  min_samples_leaf=30, l2_regularization=1., max_features=1., max_bins=255,
                  categorical_features=None, early_stopping=False, random_state=20260826,
                  warm_start=False, loss='log_loss')


def new_model():
    return HistGradientBoostingClassifier(**PARAMETERS)


def symmetric_predict(model, x):
    return np.clip((model.predict_proba(x)[:, 1] + 1 - model.predict_proba(-x)[:, 1]) / 2, .02, .98)


def lock(base_lock_path, tests, output):
    storage_guard(output)
    base = json.loads(base_lock_path.read_text())
    if base['methods'] != method_hashes():
        raise ValueError('base method changed')
    text = tests.read_text()
    if 'passed' not in text or 'failed' in text.lower() or 'error' in text.lower():
        raise ValueError('head prerequisite tests not passing')
    if sklearn.__version__ != '1.6.1':
        raise ValueError('unexpected sklearn version')
    data = json.loads(Path(base['features']).read_text())
    validate_inputs(Path(base['cohort']), data, base['protocol'])
    payload = {'experiment': 'EXP-20261029-04', 'locked_at': datetime.now(timezone.utc).isoformat(),
               'base_lock': str(base_lock_path), 'base_lock_sha256': digest(base_lock_path),
               'head_source_sha256': digest(Path(__file__)), 'test_log': str(tests), 'tests_sha256': digest(tests),
               'features': list(BASE_FEATURES), 'parameters': PARAMETERS, 'sklearn': sklearn.__version__,
               'numpy': np.__version__, 'python': sys.version,
               'symmetry': 'fit mirrored +x/-x rows with weights .5 each; p=(f(x)+1-f(-x))/2',
               'fit_scaling': 'same training-only std/no centering as the matched logistic',
               'feature_choice': 'original qualified seven-column simple control; all new single feature arms rejected, none selected',
               'comparison': 'hgb_vs_logistic, reserved in original38/76-test protocol; no reset',
               'promotion_eligible': False, 'candidate_outcomes_inspected': False}
    write_new(output, payload)
    print(json.dumps({'lock_sha256': digest(output), 'locked_at': payload['locked_at']}))


def run(lock_path, prior_results, output):
    storage_guard(output)
    head_lock = json.loads(lock_path.read_text())
    if digest(Path(__file__)) != head_lock['head_source_sha256'] or sklearn.__version__ != head_lock['sklearn']:
        raise ValueError('head method/runtime changed')
    base_path = Path(head_lock['base_lock'])
    if digest(base_path) != head_lock['base_lock_sha256']:
        raise ValueError('base lock changed')
    base = json.loads(base_path.read_text())
    if method_hashes() != base['methods']:
        raise ValueError('base method changed')
    for label in ('features', 'cohort'):
        if digest(Path(base[label])) != base[label + '_sha256']:
            raise ValueError('base data changed')
    if head_lock['features'] != list(BASE_FEATURES) or head_lock['parameters'] != PARAMETERS:
        raise ValueError('head recipe changed')
    for name, sha in json.loads((prior_results / 'artifact_manifest.json').read_text()).items():
        if digest(prior_results / name) != sha:
            raise ValueError('base prediction artifact changed')
    rows = json.loads(Path(base['features']).read_text())['rows']
    predictions = [json.loads(line) for line in (prior_results / 'predictions.jsonl').read_text().splitlines()]
    by_key = {p['key']: p for p in predictions}
    output.mkdir(exist_ok=False)
    folds, parity = [], 0.
    for start, end in base['protocol']['folds']:
        train = [r for r in rows if r['date'] >= base['protocol']['train_start'] and r['available'] < start]
        test = [r for r in rows if start <= r['date'] < end]
        x = np.array([[r['x'][n] for n in BASE_FEATURES] for r in train])
        y = np.array([r['y'] for r in train])
        xt = np.array([[r['x'][n] for n in BASE_FEATURES] for r in test])
        linear = fit(x, y)
        control = predict(xt, linear)
        prior = np.array([by_key[r['key']]['p']['simple'] for r in test])
        parity = max(parity, float(np.max(np.abs(control - prior))))
        if parity > 1e-12:
            raise ValueError('matched logistic parity failed')
        scale = np.array(linear['scale'])
        z = x / scale
        model = new_model()
        model.fit(np.concatenate((z, -z)), np.concatenate((y, 1 - y)), sample_weight=np.full(2 * len(y), .5))
        p = symmetric_predict(model, xt / scale)
        if np.max(np.abs(p + symmetric_predict(model, -xt / scale) - 1)) > 1e-10:
            raise ValueError('head swap failed')
        for index, r in enumerate(test):
            by_key[r['key']]['p'].update(hgb=float(p[index]), head_logistic=float(control[index]))
        old = json.loads((prior_results / (start + '-fold.json')).read_text())
        from .study import metrics
        labels = np.array([r['y'] for r in test])
        old['metrics'].update(hgb=metrics(labels, p), head_logistic=metrics(labels, control))
        old['head_recipe'] = {'scale': scale.tolist(), 'linear': linear, 'parameters': PARAMETERS,
                              'original_training_matches': len(y), 'mirrored_rows': 2 * len(y),
                              'total_training_weight': float(len(y))}
        with (output / (start + '-own-generated-model.pkl')).open('xb') as stream:
            pickle.dump(model, stream, protocol=4)
        write_new(output / (start + '-fold.json'), old)
        folds.append(old)
        print(json.dumps({'fold': start, 'test_n': len(test), 'matched_control_parity': parity}), flush=True)
    with (output / 'predictions.jsonl').open('x') as stream:
        for r in predictions:
            stream.write(json.dumps(r, separators=(',', ':')) + '\n')
    summary = summarise(predictions, folds, base['protocol'], output)
    summary.update({'experiment': head_lock['experiment'], 'head_lock_sha256': digest(lock_path),
                    'base_development_summary_sha256': digest(prior_results / 'summary.json'),
                    'matched_control_max_error': parity, 'split_status': 'SEEN_DEV', 'pit_verified': False,
                    'promotion_eligible': False, 'thread_env': {n: os.environ.get(n) for n in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS')},
                    'B_live': 'N/A', 'B_market': 'N/A: incomplete fixed-fold price corpus', 'roi_clv': 'N/A'})
    write_new(output / 'summary.json', summary)
    write_new(output / 'artifact_manifest.json', {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()})
    print(json.dumps(summary['comparisons']['hgb_vs_logistic']))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    lk = sub.add_parser('lock')
    lk.add_argument('--base-lock', type=Path, required=True)
    lk.add_argument('--test-log', type=Path, required=True)
    lk.add_argument('--output', type=Path, required=True)
    r = sub.add_parser('run')
    r.add_argument('--lock', type=Path, required=True)
    r.add_argument('--prior-results', type=Path, required=True)
    r.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.command == 'lock':
        lock(a.base_lock, a.test_log, a.output)
    else:
        run(a.lock, a.prior_results, a.output)


if __name__ == '__main__':
    main()
