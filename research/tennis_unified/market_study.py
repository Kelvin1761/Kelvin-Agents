"""Conditional, unclocked historical-quote development. Never live pricing."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
import openpyxl
from tennis_wc.betting import devig as devig_module

from .features import BASE_FEATURES
from .book_inventory import valid_pair
from .study import fit, holm, method_hashes as base_hashes, paired_bootstrap, sigmoid
from .warehouse import digest, storage_guard, write_new

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / 'protocol_market.json'
METHODS = ('proportional', 'power', 'shin')
COMPARISONS = [('power_vs_proportional', 'power', 'proportional'),
               ('shin_vs_proportional', 'shin', 'proportional'),
               ('inner_devig_vs_proportional', 'inner_devig', 'proportional'),
               ('offset_vs_market', 'offset', 'market'), ('offset_vs_tennis', 'offset', 'head_logistic')]


def logit(p):
    return np.log(p / (1 - p))


def weighted_fit(x, y, weights, offsets, scale):
    if not np.isfinite(x).all() or not np.isfinite(offsets).all() or np.any(weights <= 0):
        raise ValueError('invalid weighted fit input')
    z = x / scale
    beta = np.zeros(x.shape[1])
    for i in range(100):
        p = sigmoid(offsets + z @ beta)
        gradient = z.T @ (weights * (p - y)) + beta
        hessian = z.T @ ((weights * p * (1 - p))[:, None] * z) + np.eye(len(beta))
        step = np.linalg.solve(hessian, gradient)
        beta -= step
        if np.max(np.abs(step)) < 1e-10:
            return {'beta': beta.tolist(), 'scale': scale.tolist(), 'iterations': i + 1}
    raise ValueError('FIT_ERROR: frozen weighted Newton did not converge')


def raw_prediction(x, fitted, offsets=0.):
    return sigmoid(offsets + (x / np.array(fitted['scale'])) @ np.array(fitted['beta']))


def fair(odds_a, odds_b, method):
    p, q = devig_module.devig_two_way(odds_a, odds_b, method)
    swapped = devig_module.devig_two_way(odds_b, odds_a, method)
    if not 0 < p < 1 or not 0 < q < 1 or abs(p + q - 1) > 1e-10 or abs(p - swapped[1]) > 1e-10:
        raise ValueError('de-vig probability/swap failure; no row fallback allowed')
    return p


def match_losses(rows, arm):
    values = []
    for r in rows:
        y = r['y']
        pieces = []
        for q in r['quotes']:
            p = q['p'][arm]
            pieces.append([-np.log(p if y else 1 - p), (p - y) ** 2])
        values.append(np.mean(pieces, axis=0))
    return np.asarray(values)


def quote_arrays(rows, arm):
    labels, probabilities, weights = [], [], []
    for r in rows:
        for q in r['quotes']:
            labels.append(r['y']); probabilities.append(q['p'][arm]); weights.append(1 / len(r['quotes']))
    return np.array(labels), np.array(probabilities), np.array(weights)


def weighted_calibration(y, p, w):
    bins, ece = [], 0.
    for i in range(10):
        selected = (p >= i / 10) & ((p < (i + 1) / 10) if i < 9 else (p <= 1))
        mass = float(w[selected].sum())
        mean = float(np.average(p[selected], weights=w[selected])) if mass else None
        observed = float(np.average(y[selected], weights=w[selected])) if mass else None
        bins.append({'lower': i / 10, 'upper': (i + 1) / 10, 'weight': mass,
                     'quote_rows': int(selected.sum()), 'probability': mean, 'observed': observed})
        if mass:
            ece += mass / w.sum() * abs(mean - observed)
    x, beta, converged = np.column_stack((np.ones(len(p)), logit(p))), np.zeros(2), False
    for _ in range(100):
        q = sigmoid(x @ beta)
        try:
            step = np.linalg.solve(x.T @ ((w * q * (1 - q))[:, None] * x), x.T @ (w * (q - y)))
        except np.linalg.LinAlgError:
            break
        beta -= step
        if np.max(np.abs(step)) < 1e-10:
            converged = True
            break
    return {'ece_10_equal_width': float(ece), 'bins': bins,
            'intercept': float(beta[0]) if converged else None, 'slope': float(beta[1]) if converged else None}


def metrics(rows, arm):
    losses = match_losses(rows, arm)
    y, p, w = quote_arrays(rows, arm)
    return {'n_matches': len(rows), 'n_quotes': len(p), 'log_loss': float(losses[:, 0].mean()),
            'brier': float(losses[:, 1].mean()), 'accuracy': float(np.average((p >= .5) == y, weights=w)),
            'calibration': weighted_calibration(y, p, w)}


def historical_methods(rows):
    # Pure quote transformations, calculated only after the phase lock is written.
    return {r['key']: [{m: fair(q['odds_a'], q['odds_b'], m) for m in METHODS} for q in r['quotes']] for r in rows}


def inner_choice(rows, probabilities, outer_start):
    year, month = int(outer_start[:4]), int(outer_start[5:7])
    start = date(year - 1, month, 1).isoformat()
    eligible = [r for r in rows if start <= r['date'] < outer_start and r['available'] < outer_start]
    if len(eligible) < 600:
        raise ValueError('insufficient fixed inner history')
    scored = {}
    for method in METHODS:
        vector = []
        for r in eligible:
            ps = np.clip([q[method] for q in probabilities[r['key']]], .02, .98)
            y = r['y']
            vector.append([float(-np.log(ps if y else 1 - ps).mean()), float(((ps - y) ** 2).mean())])
        scored[method] = np.mean(vector, axis=0).tolist()
    # Fixed tolerance and ordering avoid floating-point tie changes, no ROI selection.
    best = METHODS[0]
    for method in METHODS[1:]:
        ll, brier = scored[method]
        if ll < scored[best][0] - 1e-12 or (abs(ll - scored[best][0]) <= 1e-12 and brier < scored[best][1] - 1e-12):
            best = method
    return {'selected': best, 'window': [start, outer_start], 'matches': len(eligible),
            'maximum_label_available': max(r['available'] for r in eligible), 'losses': scored}


def methods_hashes():
    expected = HERE.parents[1] / 'tennis-wong-choi/src/tennis_wc/betting/devig.py'
    if Path(devig_module.__file__).resolve() != expected.resolve():
        raise ValueError('Use PYTHONPATH=tennis-wong-choi/src:. to load this worktree devig source')
    files = [Path(__file__), HERE / 'prices.py', HERE / 'market_cohort.py', HERE / 'book_inventory.py', PROTOCOL, expected]
    return {str(p.relative_to(HERE.parents[1])): digest(p) for p in files}


def validate_inputs(base, price_path, clean_directory):
    if base_hashes() != base['methods']:
        raise ValueError('original frozen methods changed')
    if digest(Path(base['features'])) != base['features_sha256']:
        raise ValueError('original feature data changed')
    if digest(Path(base['cohort'])) != base['cohort_sha256']:
        raise ValueError('original source cohort changed')
    price = json.loads(price_path.read_text())
    clean_cohort, clean_features = clean_directory / 'cohort.json', clean_directory / 'features.json'
    data = json.loads(clean_cohort.read_text())
    feature_data = json.loads(clean_features.read_text())
    if (data['parent_cohort_sha256'] != base['cohort_sha256']
            or price['cohort_sha256'] != digest(clean_cohort)
            or feature_data['cohort_sha256'] != digest(clean_cohort)):
        raise ValueError('price/feature populations do not share source cohort')
    features = {r['key']: r for r in feature_data['rows']}
    held = set(data['quarantine']['keys'])
    if any(r['key'] in held for r in data['rows']) or any(
            held.intersection(r['a_history_keys'] + r['b_history_keys'] + r['h2h_keys']) for r in features.values()):
        raise ValueError('quarantined event returned to model inputs')
    for spec in price['source_files']:
        if digest(Path(spec['path'])) != spec['sha256']:
            raise ValueError('original publisher price file changed')
    keys = [r['key'] for r in price['rows']]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate price match IDs')
    for r in price['rows']:
        if r['date'] >= base['protocol']['train_start']:
            f = features.get(r['key'])
            if f is None or any(r[k] != f[k] for k in ('date', 'available', 'tour', 'surface', 'level', 'best_of', 'y')):
                raise ValueError('price/feature identity-label mismatch')
        if not r['quotes'] or len({q['book'] for q in r['quotes']}) != len(r['quotes']):
            raise ValueError('invalid same-match book roster')
        if abs(sum(q['weight'] for q in r['quotes']) - 1) > 1e-12:
            raise ValueError('match total weight is not one')
        for q in r['quotes']:
            if (q['book'] not in ('B365', 'PS') or abs(q['weight'] - 1 / len(r['quotes'])) > 1e-12
                    or not valid_pair(q['odds_a'], q['odds_b'])
                    or not 1 - 1e-12 <= 1 / q['odds_a'] + 1 / q['odds_b'] <= 1.30):
                raise ValueError('unqualified price/book/weight contract')
    return price, features


def lock(base_path, price_path, clean_directory, prior_summary, test_log, output):
    storage_guard(output)
    base = json.loads(base_path.read_text())
    price, _ = validate_inputs(base, price_path, clean_directory)
    text = test_log.read_text()
    if 'passed' not in text or 'failed' in text.lower() or 'error' in text.lower():
        raise ValueError('prerequisite tests are not passing')
    protocol = json.loads(PROTOCOL.read_text())
    if [x[0] for x in COMPARISONS] != protocol['comparisons'] or base['protocol']['statistics']['holm_tests'] != 76:
        raise ValueError('reserved comparison family changed')
    previous_manifest = json.loads((prior_summary.parent / 'artifact_manifest.json').read_text())
    if digest(prior_summary) != previous_manifest[prior_summary.name]:
        raise ValueError('previous immutable result summary changed')
    report = {'experiment': protocol['experiment'], 'locked_at': datetime.now(timezone.utc).isoformat(),
              'candidate_price_results_inspected': False, 'base_lock': str(base_path), 'base_lock_sha256': digest(base_path),
              'price_cohort': str(price_path), 'price_cohort_sha256': digest(price_path),
              'clean_directory': str(clean_directory),
              'clean_cohort_sha256': digest(clean_directory / 'cohort.json'),
              'clean_features_sha256': digest(clean_directory / 'features.json'),
              'prior_summary': str(prior_summary), 'prior_summary_sha256': digest(prior_summary),
              'prerequisites': str(test_log), 'prerequisites_sha256': digest(test_log),
              'methods': methods_hashes(), 'protocol': protocol, 'python': sys.version,
              'numpy': np.__version__, 'openpyxl': openpyxl.__version__, 'source_matches': price['matches'],
              'split_status': 'SEEN_DEV', 'pit_verified': False, 'promotion_eligible': False}
    write_new(output, report)
    print(json.dumps({'locked_at': report['locked_at'], 'sha256': digest(output)}))


def roi_vectors(rows, arm, book=None):
    profit, stake, clipping_edges = [], [], 0
    for r in rows:
        pnl = staked = 0.
        quotes = [q for q in r['quotes'] if book is None or q['book'] == book]
        for q in quotes:
            p, raw = q['p'][arm], q['raw_p'][arm]
            ev = [p * q['odds_a'] - 1, (1 - p) * q['odds_b'] - 1]
            if max(ev) <= 0:
                continue
            if max(raw * q['odds_a'] - 1, (1 - raw) * q['odds_b'] - 1) <= 0:
                clipping_edges += 1
            pick_a = ev[0] >= ev[1]
            odds = q['odds_a'] if pick_a else q['odds_b']
            weight = 1 / len(r['quotes']) if book is None else 1.
            pnl += weight * (odds - 1 if bool(r['y']) == pick_a else -1.)
            staked += weight
        profit.append(pnl); stake.append(staked)
    return np.array(profit), np.array(stake), clipping_edges


def report_roi(rows, arms):
    reports = {}
    for book in (None, 'B365', 'PS'):
        vectors = []
        for arm in arms:
            pnl, stake, _ = roi_vectors(rows, arm, book)
            vectors.extend((pnl, stake))
        samples, _, _, _ = paired_bootstrap(np.column_stack(vectors))
        by_arm = {}
        for i, arm in enumerate(arms):
            pnl, stake, clipping = roi_vectors(rows, arm, book)
            valid = samples[:, 2 * i + 1] > 0
            ratios = samples[valid, 2 * i] / samples[valid, 2 * i + 1]
            path = np.r_[0., np.cumsum(pnl)]
            by_arm[arm] = {'hypothetical_profit': float(pnl.sum()), 'hypothetical_stake': float(stake.sum()),
                           'bet_match_count': int((stake > 0).sum()), 'roi': float(pnl.sum() / stake.sum()) if stake.sum() else None,
                           'ci95_match_bootstrap': np.quantile(ratios, [.025, .975]).tolist() if len(ratios) else None,
                           'valid_bootstrap_draws': int(valid.sum()), 'clipping_created_edge_quote_count': clipping,
                           'maximum_drawdown_units': float(np.max(np.maximum.accumulate(path) - path)),
                           'qualification': 'As-if completed outcomes and unclocked prices; no executable-profit/CLV claim'}
        reports[book or 'match_weighted_all_books'] = by_arm
    return reports


def summarise(rows, folds, base, prior):
    arms = list(rows[0]['quotes'][0]['p'])
    vectors = {a: match_losses(rows, a) for a in arms}
    deltas = np.column_stack([vectors[b][:, j] - vectors[a][:, j] for _, a, b in COMPARISONS for j in range(2)])
    samples, observed, bounds, pvalues = paired_bootstrap(deltas)
    all_p = {n + ':' + m: 1. for n, _, _ in base['protocol']['comparisons'] for m in ('log_loss', 'brier')}
    for name, value in prior['comparisons'].items():
        for metric, result in value.get('metrics', {}).items():
            all_p[name + ':' + metric] = result['p_raw']
    comparisons = {}
    for i, (name, candidate, control) in enumerate(COMPARISONS):
        result = {'candidate': candidate, 'control': control, 'n_matches': len(rows), 'metrics': {}}
        for j, metric in enumerate(('log_loss', 'brier')):
            col = 2 * i + j
            gains = [f['metrics'][control][metric] - f['metrics'][candidate][metric] for f in folds]
            result['metrics'][metric] = {'gain': float(observed[col]), 'ci95': bounds[:, col].tolist(),
                                         'p_raw': float(pvalues[col]), 'fold_gains': gains,
                                         'nonworsening_folds': sum(v >= 0 for v in gains)}
            all_p[name + ':' + metric] = float(pvalues[col])
        comparisons[name] = result
    adjusted = holm(all_p)
    for name, result in comparisons.items():
        for metric, value in result['metrics'].items():
            value['p_holm_76'] = adjusted[name + ':' + metric]
        stable = all(v['gain'] > 0 and v['nonworsening_folds'] == 5 for v in result['metrics'].values())
        supported = all(v['p_holm_76'] <= .05 for v in result['metrics'].values())
        result['decision'] = ('ADVANCE_DEV_ONLY' if supported else 'PENDING_MULTIPLICITY_FAMILY') if stable else 'REJECT_DEV'
    subgroups = {}
    for field in ('tour', 'surface', 'level', 'best_of'):
        for value in sorted({r[field] for r in rows}, key=str):
            group = [r for r in rows if r[field] == value]
            subgroups[field + ':' + str(value)] = {a: metrics(group, a) for a in arms}
    for name, lower, upper in (('<=2', 0, 2), ('2-3', 2, 3), ('3-5', 3, 5), ('>5', 5, float('inf'))):
        group = []
        for r in rows:
            selected = [q for q in r['quotes'] if lower < max(q['odds_a'], q['odds_b']) <= upper]
            if selected:
                group.append(dict(r, quotes=selected))
        if group:
            subgroups['odds:' + name] = {a: metrics(group, a) for a in arms}
    for name, lower, upper in (('0', 0, 0), ('1-4', 1, 4), ('5-19', 5, 19), ('20+', 20, float('inf'))):
        group = [r for r in rows if lower <= min(r['n_a'], r['n_b']) <= upper]
        if group:
            subgroups['history:' + name] = {a: metrics(group, a) for a in arms}
    required = ['offset_vs_market', 'offset_vs_tennis']
    offset_decisions = [comparisons[n]['decision'] for n in required]
    offset_status = 'REJECT_DEV' if 'REJECT_DEV' in offset_decisions else (
        'ADVANCE_DEV_ONLY' if set(offset_decisions) == {'ADVANCE_DEV_ONLY'} else 'PENDING_MULTIPLICITY_FAMILY')
    return {'n_matches': len(rows), 'n_book_rows': sum(len(r['quotes']) for r in rows), 'holm_tests': len(all_p),
            'metrics': {a: metrics(rows, a) for a in arms}, 'comparisons': comparisons,
            'offset_decision': offset_status, 'all_family_raw_p': all_p, 'all_family_holm_p': adjusted,
            'prior_rejected_feature_decisions_unchanged': True, 'subgroups': subgroups,
            'roi': report_roi(rows, arms), 'B_live': 'N/A: no matched full live feature evidence',
            'CLV': 'N/A: historical quote/closing clocks not established'}, samples


def run(lock_path, output):
    storage_guard(output)
    lk = json.loads(lock_path.read_text())
    if methods_hashes() != lk['methods'] or sys.version != lk['python'] or np.__version__ != lk['numpy']:
        raise ValueError('locked market method/runtime changed')
    for key in ('base_lock', 'price_cohort', 'prior_summary', 'prerequisites'):
        if digest(Path(lk[key])) != lk[key + '_sha256']:
            raise ValueError('locked input changed: ' + key)
    base = json.loads(Path(lk['base_lock']).read_text())
    clean = Path(lk['clean_directory'])
    if digest(clean / 'cohort.json') != lk['clean_cohort_sha256'] or digest(clean / 'features.json') != lk['clean_features_sha256']:
        raise ValueError('cleaned model input changed')
    price, features = validate_inputs(base, Path(lk['price_cohort']), clean)
    rows = [r for r in price['rows'] if r['key'] in features]
    output.mkdir(exist_ok=False)
    probabilities = historical_methods(rows)
    predictions, folds = [], []
    for start, end in base['protocol']['folds']:
        train = [r for r in rows if r['date'] >= base['protocol']['train_start'] and r['available'] < start]
        test = [r for r in rows if start <= r['date'] < end]
        if len(train) < 600 or not test:
            raise ValueError('fixed five-fold population incomplete')
        names = list(BASE_FEATURES)
        x = np.array([[features[r['key']]['x'][n] for n in names] for r in train])
        y = np.array([r['y'] for r in train])
        linear = fit(x, y)
        scale = np.array(linear['scale'])
        qx = np.repeat(x, [len(r['quotes']) for r in train], axis=0)
        qy = np.repeat(y, [len(r['quotes']) for r in train])
        weights = np.array([1 / len(r['quotes']) for r in train for _ in r['quotes']])
        offsets = logit(np.array([p['proportional'] for r in train for p in probabilities[r['key']]]))
        fitted = weighted_fit(qx, qy, weights, offsets, scale)
        # Encompassing coefficients describe training only, never another test arm.
        diagnostic_x = np.column_stack((offsets, qx))
        mean = np.average(diagnostic_x, axis=0, weights=weights)
        ds = np.sqrt(np.average((diagnostic_x - mean) ** 2, axis=0, weights=weights)); ds[ds == 0] = 1.
        diagnostic = weighted_fit(diagnostic_x, qy, weights, np.zeros(len(qy)), ds)
        diagnostic['raw_unit_coefficients'] = (np.array(diagnostic['beta']) / ds).tolist()
        diagnostic['columns'] = ['market_logit', *names]
        choice = inner_choice(rows, probabilities, start)
        saved = []
        for r in test:
            xx = np.array([[features[r['key']]['x'][n] for n in names]])
            tennis = float(raw_prediction(xx, linear)[0])
            quotes = []
            for q, transformed in zip(r['quotes'], probabilities[r['key']]):
                offset = float(logit(np.array(transformed['proportional'])))
                p = float(raw_prediction(xx, fitted, np.array([offset]))[0])
                swapped = float(raw_prediction(-xx, fitted, np.array([-offset]))[0])
                if abs(p + swapped - 1) > 1e-10:
                    raise ValueError('offset swap failed')
                raw = dict(transformed, inner_devig=transformed[choice['selected']], offset=p,
                           market=transformed['proportional'], head_logistic=tennis)
                quotes.append(dict(q, raw_p=raw, p={a: float(np.clip(v, .02, .98)) for a, v in raw.items()}))
            saved.append({k: r[k] for k in ('key', 'date', 'available', 'tour', 'surface', 'level', 'best_of', 'y', 'book_event_date', 'locator')} |
                         {'fold': start, 'quotes': quotes, 'n_a': features[r['key']]['n_a'], 'n_b': features[r['key']]['n_b']})
        report = {'window': [start, end], 'train_matches': len(train), 'train_book_rows': len(weights),
                  'total_training_weight': float(weights.sum()), 'test_matches': len(test),
                  'max_training_label_available': max(r['available'] for r in train),
                  'features': names, 'linear': linear, 'offset': fitted, 'inner_choice': choice,
                  'encompassing_training_only': diagnostic,
                  'metrics': {a: metrics(saved, a) for a in saved[0]['quotes'][0]['p']}}
        write_new(output / (start + '-fold.json'), report)
        predictions.extend(saved); folds.append(report)
        print(json.dumps({'fold': start, 'train_matches': len(train), 'test_matches': len(test)}), flush=True)
    with (output / 'predictions.jsonl').open('x') as stream:
        for r in predictions:
            stream.write(json.dumps(r, separators=(',', ':')) + '\n')
    summary, samples = summarise(predictions, folds, base, json.loads(Path(lk['prior_summary']).read_text()))
    summary.update({'experiment': lk['experiment'], 'completed_at': datetime.now(timezone.utc).isoformat(),
                    'lock_sha256': digest(lock_path), 'split_status': 'SEEN_DEV', 'pit_verified': False,
                    'promotion_eligible': False, 'estimand': lk['protocol']['estimand'], 'folds': folds})
    with (output / 'paired_bootstrap_means.npy').open('xb') as stream:
        np.save(stream, samples, allow_pickle=False)
    write_new(output / 'summary.json', summary)
    write_new(output / 'artifact_manifest.json', {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()})
    print(json.dumps({'results': str(output / 'summary.json'), 'n_matches': len(predictions),
                      'offset_decision': summary['offset_decision'], 'promotion_eligible': False}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    l = sub.add_parser('lock')
    for n in ('base-lock', 'price-cohort', 'clean-directory', 'prior-summary', 'test-log', 'output'):
        l.add_argument('--' + n, type=Path, required=True)
    r = sub.add_parser('run')
    r.add_argument('--lock', type=Path, required=True); r.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.command == 'lock':
        lock(a.base_lock, a.price_cohort, a.clean_directory, a.prior_summary, a.test_log, a.output)
    else:
        run(a.lock, a.output)


if __name__ == '__main__':
    main()
