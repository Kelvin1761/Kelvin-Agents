"""Research-only monotone prop classifier; no production hook or promotion path."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, logit
from scipy.stats import nbinom, poisson

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / '.agents/skills/nba/nba_daily_auto'))
import nba_prop_training as evidence

VERSION = 'nba-prop-monotone-challenger-v1'
ARMS = ('core', 'full', 'minus_recency', 'minus_minutes', 'minus_opportunity', 'minus_opponent')
MINIMUMS = {'dates': 8, 'events': 20, 'ladders': 100, 'class_ladders': 10}
OPPORTUNITY = {
    'PTS': ['two_pa_per_min', 'three_pa_per_min', 'fta_per_min', 'two_p_conversion', 'three_p_conversion', 'ft_conversion'],
    'REB': ['oreb_chances_per_min', 'dreb_chances_per_min', 'oreb_conversion', 'dreb_conversion', 'contested_rebound_share'],
    'AST': ['potential_ast_per_min', 'touches_per_min', 'time_of_possession_per_game'],
    'FG3M': ['three_pa_per_min', 'three_p_conversion', 'catch_shoot_3pa_per_min', 'pull_up_3pa_per_min'],
}
OPPONENT = {'PTS': ['opponent_points_allowed_per100'], 'AST': ['opponent_assists_allowed_per100'],
            'REB': ['opponent_own_fg_misses_per100', 'opponent_offensive_rebounds_per100', 'opponent_rebounds_allowed_per100'],
            'FG3M': ['opponent_3pa_allowed_per100', 'opponent_3pm_allowed_per100']}
CORE = ['count_logit', 'empirical_logit']
RECENT = ['recent_logit']
MINUTES = ['minutes_mean', 'minutes_cv', 'minutes_l3_ratio']


class InsufficientData(ValueError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encoded(obj):
    return json.dumps(obj, sort_keys=True, allow_nan=False, ensure_ascii=False).encode()


def columns(stat, arm):
    if stat not in OPPORTUNITY or arm not in ARMS:
        raise ValueError('unsupported prop/arm')
    blocks = [('recency', RECENT), ('minutes', MINUTES),
              ('opportunity', OPPORTUNITY[stat]), ('opponent', OPPONENT[stat])]
    return CORE + [c for block, fields in blocks if arm != 'core' and arm != 'minus_'+block for c in fields]


def features(row):
    """An allowlist: prices, C, outcome, names and labels cannot enter X."""
    if row.get('contract') != evidence.CONTRACT or row['prop'] not in OPPORTUNITY:
        raise ValueError('unsupported evidence contract')
    inputs = row['inputs']
    values = np.asarray(inputs['l10_values'], dtype=float)
    line = float(row['key'][4])
    if (len(values) != 10 or not np.isfinite(values).all() or (values < 0).any()
            or line < 1 or not line.is_integer()):
        raise ValueError('invalid milestone history')
    dates = inputs['l10_dates']
    tip = evidence.at(row['feature_evidence']['source']['tip_off'])
    if (len(dates) != 10 or len(set(dates)) != 10 or dates != sorted(dates, reverse=True)
            or not tip or any(datetime.fromisoformat(d).date() >= tip.astimezone(evidence.NY).date() for d in dates)):
        raise ValueError('not ten dated prior games')
    hits = values >= line
    mean, variance = max(values.mean(), .05), values.var()
    alpha = max((variance-mean)/mean**2, 0.)
    p = nbinom.sf(line-1, 1/alpha, 1/(1+alpha*mean)) if alpha > 0 else poisson.sf(line-1, mean)
    weights = .9 ** np.arange(10)
    out = {'count_logit': float(logit(np.clip(p, 1e-6, 1-1e-6))),
           'empirical_logit': float(logit((hits.sum()+.5)/11)),
           'recent_logit': float(logit((np.dot(weights, hits)+.5)/(weights.sum()+1)))}
    minutes = inputs.get('l10_minutes')
    valid = minutes is not None and len(minutes) == 10
    arr = np.asarray(minutes, dtype=float) if valid else np.array([])
    valid = valid and np.isfinite(arr).all() and (arr >= 0).all() and arr.mean() > 0
    out.update(dict(zip(MINUTES, [float(arr.mean()), float(arr.std()/arr.mean()), float(arr[:3].mean()/arr.mean())]
                        if valid else [np.nan]*3)))
    opportunities = inputs.get('opportunity') or {}
    for key in [*OPPORTUNITY[row['prop']], *OPPONENT[row['prop']]]:
        value = evidence.number(opportunities.get(key))
        out[key] = value if value is not None and value >= 0 else np.nan
    return out


def eligible(row):
    f = row['inputs']
    values = np.asarray(f['l10_values'], dtype=float)
    line = float(row['key'][4])
    return len(values) == 10 and (values >= line).mean() >= .8 and (values[:5] >= line).mean() >= .8


def load_export(folder):
    folder = Path(folder)
    report = json.loads((folder/'Readiness.json').read_text())
    if report.get('contract') != evidence.CONTRACT:
        raise ValueError('unknown export contract')
    source = []
    for day, digest in report['source_ledger_sha256'].items():
        path = folder/'source_ledger'/f'{day}.jsonl'
        if sha(path) != digest:
            raise ValueError('source ledger hash mismatch')
        source.extend(json.loads(line) for line in path.read_text().splitlines() if line.strip())
    rebuilt, _ = evidence.dataset(source)
    saved = [json.loads(line) for line in (folder/'dataset.jsonl').read_text().splitlines() if line.strip()]
    if encoded(saved) != encoded(rebuilt):
        raise ValueError('dataset does not match frozen source ledger')
    if len({tuple(row['key']) for row in saved}) != len(saved):
        raise ValueError('duplicate milestone observation')
    for row in saved:
        features(row)
        if bool(row['eligible_80_80']) != bool(eligible(row)):
            raise ValueError('eligibility differs from history')
    return saved


def ladder(row):
    return tuple(row['key'][:4])


def fit(rows, stat, arm):
    rows = [r for r in rows if r['prop'] == stat and eligible(r) and r['target']['y'] in (0, 1)]
    clusters = {ladder(r) for r in rows}
    if (len({r['key'][0] for r in rows}) < MINIMUMS['dates']
            or len({tuple(r['key'][:2]) for r in rows}) < MINIMUMS['events']
            or len(clusters) < MINIMUMS['ladders']
            or any(len({ladder(r) for r in rows if r['target']['y'] == y}) < MINIMUMS['class_ladders'] for y in (0, 1))):
        raise InsufficientData(f'{stat}/{arm}: too few prior dated independent training groups')
    names = columns(stat, arm)
    feature_rows = [features(r) for r in rows]
    if arm != 'core' and arm != 'minus_opportunity':
        covered = {tuple(r['key'][:2]) for r, f in zip(rows, feature_rows)
                   if any(np.isfinite(f[k]) for k in OPPORTUNITY[stat])}
        if len(covered) < MINIMUMS['events']:
            raise InsufficientData(f'{stat}/{arm}: new opportunity coverage missing')
    X = np.asarray([[f[k] for k in names] for f in feature_rows])
    keep = np.isfinite(X).any(axis=0)
    dropped = [k for k, active in zip(names, keep) if not active]
    names, X = [k for k, active in zip(names, keep) if active], X[:, keep]
    median = np.nanmedian(X, axis=0)
    X = np.where(np.isfinite(X), X, median)
    mean, scale = X.mean(axis=0), X.std(axis=0)
    scale[scale < 1e-9] = 1
    X = np.column_stack([np.ones(len(rows)), (X-mean)/scale])
    y = np.asarray([r['target']['y'] for r in rows], dtype=float)
    sizes = Counter(ladder(r) for r in rows)
    w = np.asarray([1/sizes[ladder(r)] for r in rows])

    def loss(beta):
        z = X@beta
        objective = np.dot(w, np.logaddexp(0, z)-y*z) + 2*np.dot(beta[1:], beta[1:])
        gradient = X.T@(w*(expit(z)-y))
        gradient[1:] += 4*beta[1:]
        return objective, gradient

    bounds = [(None, None)] + [(0, None) if k in CORE+RECENT else (None, None) for k in names]
    result = minimize(loss, np.zeros(X.shape[1]), jac=True, method='L-BFGS-B', bounds=bounds,
                      options={'maxiter': 1000, 'ftol': 1e-10})
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError(f'optimizer failed: {result.message}')
    return {'stat': stat, 'arm': arm, 'columns': names, 'dropped_all_missing': dropped,
            'median': median.tolist(), 'mean': mean.tolist(), 'scale': scale.tolist(), 'beta': result.x.tolist(),
            'training_rows': len(rows), 'training_ladders': len(clusters),
            'last_target_available_at': max(r['target']['available_at'] for r in rows),
            'last_training_date': max(r['key'][0] for r in rows)}


def predict(model, row):
    f = features(row)
    if row['prop'] != model['stat']:
        raise ValueError('wrong prop model')
    available, trained = evidence.at(row['available_at']), evidence.at(model['last_target_available_at'])
    if not available or not trained or trained >= available:
        raise ValueError('model includes labels unavailable at prediction time')
    names = model['columns']
    if names != [k for k in columns(model['stat'], model['arm']) if k not in model['dropped_all_missing']]:
        raise ValueError('model feature order mismatch')
    beta = np.asarray(model['beta'])
    if any(beta[i+1] < 0 for i, k in enumerate(names) if k in CORE+RECENT):
        raise ValueError('nonmonotone model coefficients')
    x = np.asarray([f[k] for k in names])
    x = np.where(np.isfinite(x), x, model['median'])
    z = beta[0]+np.dot((x-model['mean'])/model['scale'], beta[1:])
    return float(np.clip(expit(z), 1e-6, 1-1e-6))


def metrics(rows, name):
    if not rows:
        return {'n': 0}
    y = np.asarray([r['y'] for r in rows]);p = np.asarray([r[name] for r in rows])
    return {'n': len(rows), 'events': len({tuple(r['key'][:2]) for r in rows}),
            'mean_p': float(p.mean()), 'hit_rate': float(y.mean()), 'gap_pp': float(100*(p-y).mean()),
            'brier': float(np.mean((p-y)**2)),
            'log_loss': float(-np.mean(y*np.log(np.clip(p, 1e-6, 1-1e-6))
                                      +(1-y)*np.log1p(-np.clip(p, 1e-6, 1-1e-6))))}


def paired(rows, first, second):
    if not rows:
        return {'n': 0}
    days = sorted({r['key'][0] for r in rows})
    diffs = np.asarray([(r[first]-r['y'])**2-(r[second]-r['y'])**2 for r in rows])
    groups = [np.asarray([i for i, r in enumerate(rows) if r['key'][0] == d]) for d in days]
    rng = np.random.default_rng(20261025)
    draws = [float(diffs[np.concatenate([groups[i] for i in rng.integers(0, len(days), len(days))])].mean())
             for _ in range(2000)]
    return {'n': len(rows), 'date_clusters': len(days), 'brier_delta_first_minus_second': float(diffs.mean()),
            'descriptive_date_cluster95': np.percentile(draws, [2.5, 97.5]).tolist(),
            'note': 'multiple descriptive comparisons, no independent promotion or winner decision'}


def study(rows, model_sink=None):
    identities = {r['baseline']['model_id'] for r in rows}
    if len(identities) > 1:
        raise ValueError('mixed C identities; comparison baseline must be frozen before study')
    oof, blocked = [], []
    for day in sorted({r['key'][0] for r in rows}):
        test = [r for r in rows if r['key'][0] == day and eligible(r)]
        if not test:
            continue
        cutoff = min(evidence.at(r['available_at']) for r in test)
        train = [r for r in rows if r['key'][0] < day and r['target']['y'] in (0, 1)
                 and evidence.at(r['target']['available_at']) < cutoff]
        try:
            models = {(s, a): fit(train, s, a) for s in OPPORTUNITY for a in ARMS}
        except InsufficientData as exc:
            blocked.append({'date': day, 'reason': str(exc)})
            continue
        if model_sink is not None:
            model_sink.append({'version': VERSION, 'deployment_eligible': False, 'test_date': day,
                               'source_code_sha256': sha(__file__), 'training_cutoff': cutoff.isoformat(),
                               'C_model_id': next(iter(identities)),
                               'models': {s+'/'+a: m for (s, a), m in models.items()}})
        for r in test:
            if r['target']['y'] not in (0, 1):
                continue
            c = evidence.number(r['baseline']['probability'])
            if c is None or not 0 <= c <= 1:
                continue
            oof.append({'key': r['key'], 'prop': r['prop'], 'y': r['target']['y'], 'C': c,
                        'C_model_id': r['baseline']['model_id'], 'price': r['baseline']['price'],
                        **{a: predict(models[r['prop'], a], r) for a in ARMS}})
    selected = {}
    for name in ('C', *ARMS):
        pool = [r for r in oof if evidence.number(r['price']) is not None
                and 1.15 <= r['price'] <= 3.5 and r[name]*r['price'] > 1]
        pool.sort(key=lambda r: (-(r[name]*r['price']-1), tuple(str(k) for k in r['key'])))
        choices = {}
        for r in pool:
            choices.setdefault(tuple(r['key'][:2]), r)
        picked = list(choices.values())
        selected[name] = {**metrics(picked, name), 'flat_single_leg_roi':
                          float(np.mean([r['y']*r['price']-1 for r in picked])) if picked else None}
    report = {'status': 'NEEDS_MORE_TESTING' if oof else 'awaiting_new_data',
              'deployment_eligible': False, 'blocked_dates': blocked, 'rows': len(oof),
              'metrics': {name: metrics(oof, name) for name in ('C', *ARMS)},
              'by_prop': {s: {n: metrics([r for r in oof if r['prop'] == s], n)
                              for n in ('C', *ARMS)} for s in OPPORTUNITY},
              'paired_full_minus': {n: paired(oof, 'full', n) for n in ('C', *ARMS) if n != 'full'},
              'by_price_band': {band: {n: metrics([r for r in oof if r['price'] is not None and lo <= r['price'] < hi], n)
                                       for n in ('C', *ARMS)} for band, lo, hi in
                               [('1.15-1.5', 1.15, 1.5), ('1.5-2', 1.5, 2), ('2-3.5', 2, 3.50001)]},
              'single_leg_selection_diagnostic': selected,
              'limitations': ['operational sample floors are not statistical power or promotion gates',
                              'no uncertainty-adjusted winner, SGM or profitability verdict',
                              'shared prop model; no per-player fit; no best-arm adoption']}
    return report, oof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, help='predict only with one frozen study model snapshot')
    parser.add_argument('--export', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = load_export(args.export)
    args.output.mkdir(parents=True, exist_ok=False)
    if args.model:
        raw = args.model.read_bytes()
        if args.model.with_suffix('.sha256').read_text().strip() != hashlib.sha256(raw).hexdigest():
            raise ValueError('model artifact hash mismatch')
        artifact = json.loads(raw)
        if (artifact.get('version') != VERSION or artifact.get('deployment_eligible') is not False
                or artifact.get('source_code_sha256') != sha(__file__)):
            raise ValueError('model constructor/version mismatch')
        now = datetime.now(timezone.utc)
        forecasts = []
        for row in rows:
            tip = evidence.at(row['feature_evidence']['source']['tip_off'])
            if not evidence.at(row['available_at']) <= now < tip:
                raise ValueError('forward forecast must be frozen before tip')
            if row['baseline']['model_id'] != artifact['C_model_id']:
                raise ValueError('C baseline changed')
            if eligible(row):
                forecasts.append({'key': row['key'], 'prop': row['prop'], 'probability':
                                  predict(artifact['models'][row['prop']+'/full'], row),
                                  'decision': 'OBSERVE', 'generated_at': now.isoformat(),
                                  'model_sha256': hashlib.sha256(raw).hexdigest(),
                                  'baseline': row['baseline']})
        (args.output/'Forward.jsonl').write_text(''.join(encoded(r).decode()+'\n' for r in forecasts))
        print(json.dumps({'status': 'research_only', 'forecast_rows': len(forecasts), 'deployment_eligible': False}))
        return
    baseline = {'version': VERSION, 'created_at': datetime.now(timezone.utc).isoformat(),
                'export_dataset_sha256': sha(args.export/'dataset.jsonl'), 'source_code_sha256': sha(__file__),
                'rows': len(rows), 'minimums': MINIMUMS, 'arms': ARMS, 'deployment_eligible': False}
    (args.output/'Baseline.json').write_bytes(encoded(baseline))
    artifacts = []
    report, oof = study(rows, artifacts)
    (args.output/'Report.json').write_bytes(encoded(report))
    (args.output/'OOF.jsonl').write_text(''.join(encoded(r).decode()+'\n' for r in oof))
    for artifact in artifacts:
        path = args.output/(artifact['test_date']+'_models.json')
        path.write_bytes(encoded(artifact))
        path.with_suffix('.sha256').write_text(sha(path))
    # There is no automatic final-data refit or best-arm artifact selection.
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
