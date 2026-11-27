#!/usr/bin/env python3
"""Pre-registered AU weight refit predictions (EXP-20261127-33)."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / 'shared_racing'))

import au_matrix_refit as refit
from au_eval import _stage4_metric_rows
from au_racing_engine.scoring import MATRIX_WEIGHTS
from au_walkforward_refit import exact_score
from model_evaluation_decision import evaluate_full_record

RANKING = ('top3_capture_at5', 'ndcg_at5', 'top5_pairwise_auc')


def predict(ds, fit=refit.fit_consensus):
    """Fit on strictly earlier dates; return windows and paired race records."""
    races = ds.races
    if races != sorted(races, key=lambda r: (r['date'], r['meeting'], r['race'])):
        raise ValueError('races must be sorted by date, meeting and race')
    dates = sorted({r['date'] for r in races})
    if len(dates) <= 20:
        raise ValueError('more than 20 race days required')
    refit.set_objective('place')
    mx = ds.dim_matrix()
    windows, predictions = [], []
    for start in range(20, len(dates), 7):
        days = dates[start:start + 7]
        train_end = sum(r['date'] < days[0] for r in races)
        if any(r['date'] >= days[0] for r in races[:train_end]):
            raise ValueError('training date is not strictly earlier than prediction')
        weights, accepted = fit(ds, mx, MATRIX_WEIGHTS, train_end, 20260826, 400, 4)
        weights = dict(MATRIX_WEIGHTS if weights is None else weights)
        windows.append({'training_dates': dates[:start], 'training_races': train_end,
                        'prediction_dates': days, 'accepted_draws': accepted,
                        'fallback': accepted == 0, 'weights': weights})
        for race in races[train_end:]:
            if race['date'] not in days:
                continue
            rows = [{**row, 'ability_baseline': exact_score(row, MATRIX_WEIGHTS),
                     'ability_candidate': exact_score(row, weights)} for row in race['rows']]
            predictions.append({**race, 'window': len(windows) - 1, 'rows': rows})
    return windows, predictions


def arm(predictions, name):
    return [{**race, 'rows': [{**row, 'ability': row['ability_' + name]}
                              for row in race['rows']]} for race in predictions]


def judge(predictions, *, leakage_audit_passed=False):
    baseline, candidate = (arm(predictions, n) for n in ('baseline', 'candidate'))
    return evaluate_full_record(domain='au', mode='walk_forward_oos',
        dates=[r['date'] for r in predictions],
        baseline_rows=_stage4_metric_rows(baseline, lambda r: r['ability']),
        candidate_rows=_stage4_metric_rows(candidate, lambda r: r['ability']),
        leakage_audit_passed=leakage_audit_passed, ranking_metrics=RANKING, blocks=6, bootstrap=2000)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True, help='clean, authorised leaves corpus')
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--leakage-audit-passed', action='store_true', help='assert independent source and feature leakage audit passed')
    args = parser.parse_args()
    ds = refit.Dataset(Path(args.data))
    ds.races.sort(key=lambda r: (r['date'], r['meeting'], r['race']))
    # Dataset arrays follow input order: do not silently reorder them.
    if [r for race in ds.races for r in race['rows']] != ds.rows:
        raise ValueError('input races must already be sorted')
    if any(r['date'] < '2026-08-05' for r in ds.races):
        raise ValueError('input must be filtered to 2026-08-05 onwards')
    windows, predictions = predict(ds)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sample = [(r['date'], r['meeting'], r['race'], [x['n'] for x in r['rows']]) for r in predictions]
    digest = hashlib.sha256(json.dumps(sample, ensure_ascii=False).encode()).hexdigest()
    for name in ('baseline', 'candidate'):
        (out / f'{name}.json').write_text(json.dumps({'sample_sha256': digest, 'races': arm(predictions, name)}, ensure_ascii=False))
    (out / 'windows.json').write_text(json.dumps(windows, ensure_ascii=False, indent=2))
    (out / 'verdict.json').write_text(json.dumps(judge(predictions, leakage_audit_passed=args.leakage_audit_passed), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
