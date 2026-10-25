"""Frozen OOF diagnostics. No production imports, fitting of base models, or promotion."""
import argparse
import collections
import csv
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import random

MODELS = ('core', 'full', 'minus_minutes', 'minus_role', 'minus_opponent', 'minus_schedule', 'C')
NUMERIC = (*MODELS, 'market_price', 'hit', 'hit_rate_l10', 'hit_rate_l5', 'line_value', 'n_history')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def eligible(row):
    return row['n_history'] >= 10 and row['hit_rate_l10'] >= 80 and row['hit_rate_l5'] >= 80


def select(rows, model):
    pool = [r for r in rows if eligible(r) and 1.15 <= r['market_price'] <= 3.5
            and r[model] * r['market_price'] > 1]
    pool.sort(key=lambda r: (-(r[model] * r['market_price'] - 1), r['player_key'],
                             r['stat_category'], r['line_value']))
    chosen = {}
    for row in pool:
        chosen.setdefault(row['game_group'], row)
    return list(chosen.values())


def adjusted(probability, offset):
    p = min(max(probability, 1e-9), 1 - 1e-9)
    logit = math.log(p / (1 - p)) + offset
    return 1 / (1 + math.exp(-logit))


def fit_offset(rows, ridge):
    """Penalized Bernoulli likelihood, one raw-selected observation per event."""
    if ridge <= 0:
        raise ValueError('positive ridge required')
    lo, hi = -40., 40.
    for _ in range(100):
        mid = (lo + hi) / 2
        gradient = sum(adjusted(r['full'], mid) - r['hit'] for r in rows) + ridge * mid
        if gradient > 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def forward(rows, config):
    dates = sorted({r['game_date'] for r in rows})
    output, records = [], []
    for day in dates:
        cutoff = (date.fromisoformat(day) - timedelta(days=config['label_embargo_calendar_days'])).isoformat()
        train = select([r for r in rows if r['game_date'] <= cutoff], 'full')
        train_dates = sorted({r['game_date'] for r in train})
        record = {'test_date': day, 'latest_allowed_train_date': cutoff,
                  'train_dates': train_dates, 'train_events': len(train)}
        if len(train_dates) < config['min_train_dates'] or len(train) < config['min_train_events']:
            records.append(dict(record, status='insufficient_training'))
            continue
        offset = fit_offset(train, config['ridge'])
        records.append(dict(record, status='evaluated', offset=offset))
        for row in rows:
            if row['game_date'] == day:
                output.append(dict(row, calibrated=adjusted(row['full'], offset)))
    return output, records


def metrics(rows, model):
    n = len(rows)
    if not n:
        return {'n': 0, 'events': 0, 'dates': 0}
    p = sum(r[model] for r in rows) / n
    hit = sum(r['hit'] for r in rows) / n
    return {'n': n, 'events': len({r['game_group'] for r in rows}),
            'dates': len({r['game_date'] for r in rows}), 'hits': sum(r['hit'] for r in rows),
            'mean_probability': p, 'hit_rate': hit, 'overprediction_pp': (p - hit) * 100,
            'brier': sum((r[model] - r['hit']) ** 2 for r in rows) / n,
            'mean_price': sum(r['market_price'] for r in rows) / n,
            'flat_single_leg_roi': sum(r['hit'] * r['market_price'] - 1 for r in rows) / n}


def paired_brier(rows, first, second):
    if not rows:
        return {'n': 0}
    groups = collections.defaultdict(list)
    for row in rows:
        groups[row['game_date']].append((row[first] - row['hit']) ** 2 - (row[second] - row['hit']) ** 2)
    days = sorted(groups)
    rng = random.Random(20261025)
    draws = []
    for _ in range(2000):
        sample = [x for d in rng.choices(days, k=len(days)) for x in groups[d]]
        draws.append(sum(sample) / len(sample))
    draws.sort()
    return {'n': len(rows), 'date_clusters': len(days),
            'delta_first_minus_second': sum(sum(v) for v in groups.values()) / len(rows),
            'descriptive_date_cluster_95': [draws[49], draws[1949]], 'resamples': 2000}


def breakdown(rows, model):
    stats = {s: metrics([r for r in rows if r['stat_category'] == s], model)
             for s in sorted({r['stat_category'] for r in rows})}
    bands = {name: metrics([r for r in rows if lo <= r['market_price'] < hi], model)
             for name, lo, hi in [('1.15-1.5', 1.15, 1.5), ('1.5-2', 1.5, 2), ('2-3.5', 2, 3.50001)]}
    return {'by_stat': stats, 'by_price': bands}


def write_csv(path, rows):
    if not rows:
        return
    with Path(path).open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(protocol_path, output):
    protocol = json.loads(Path(protocol_path).read_text())
    if protocol['deployment_eligible'] or protocol['family'] != 'L10-80-L5-80-selected-calibration-v1':
        raise ValueError('research protocol required')
    if digest(protocol['source']) != protocol['source_sha256']:
        raise ValueError('OOF source hash mismatch')
    rows = list(csv.DictReader(Path(protocol['source']).open()))
    identities = set()
    event_dates = {}
    for row in rows:
        for key in NUMERIC:
            row[key] = float(row[key])
            if not math.isfinite(row[key]):
                raise ValueError('nonfinite input')
        key = (row['game_group'], row['player_key'], row['stat_category'], row['line_value'])
        if key in identities or row['hit'] not in (0, 1) or any(not 0 < row[m] < 1 for m in MODELS):
            raise ValueError('invalid OOF identity/probability/label')
        identities.add(key)
        if event_dates.setdefault(row['game_group'], row['game_date']) != row['game_date']:
            raise ValueError('event spans dates')
        date.fromisoformat(row['game_date'])
    output = Path(output)
    output.mkdir(exist_ok=False)
    pool = [r for r in rows if eligible(r) and 1.15 <= r['market_price'] <= 3.5]
    summary = {'status': 'NEEDS_MORE_TESTING; observed development only; no production switch',
               'protocol_sha256': digest(protocol_path), 'code_sha256': digest(__file__),
               'source_sha256': digest(protocol['source']), 'ablation': {}}
    for model in MODELS:
        picked = select(rows, model)
        summary['ablation'][model] = {'eligible_pool': metrics(pool, model),
                                      'selected': metrics(picked, model), **breakdown(picked, model)}
        write_csv(output / (model + '_selected.csv'), picked)
    summary['full_minus_block_same_eligible_pool'] = {
        model: paired_brier(pool, 'full', model) for model in MODELS if model != 'full'}
    full_picks = select(rows, 'full')
    summary['same_full_picked_comparator'] = {model: metrics(full_picks, model) for model in MODELS}
    calibrated, records = forward(rows, protocol['calibration'])
    fixed = select(calibrated, 'full')
    reranked = select(calibrated, 'calibrated')
    cal_pool = [r for r in calibrated if eligible(r) and 1.15 <= r['market_price'] <= 3.5]
    summary['calibration'] = {'training_records': records,
        'common_evaluation_dates': sorted({r['game_date'] for r in calibrated}),
        'fixed_raw_selection': {'raw': metrics(fixed, 'full'), 'calibrated': metrics(fixed, 'calibrated'),
                                'paired': paired_brier(fixed, 'calibrated', 'full')},
        'same_eligible_pool': {'raw': metrics(cal_pool, 'full'), 'calibrated': metrics(cal_pool, 'calibrated'),
                               'paired': paired_brier(cal_pool, 'calibrated', 'full')},
        'reselected': metrics(reranked, 'calibrated'), 'reselected_breakdown': breakdown(reranked, 'calibrated'),
        'common_date_C_selected': metrics(select(calibrated, 'C'), 'C')}
    write_csv(output / 'Forward_Calibrated_OOF.csv', calibrated)
    write_csv(output / 'Forward_Fixed_Selection.csv', fixed)
    write_csv(output / 'Forward_Reselected.csv', reranked)
    summary['limitations'] = ['C historical-fit overlap; not an independent C trial',
        'same-date embargo is conservative, not independently observed historical settlement timestamp proof',
        'selected calibration training has few events; shared offset does not learn per-prop calibration',
        'no new tracking features in these old snapshots; no historical backfill',
        'multiple descriptive ablations; no best-arm adoption or independent significance claim',
        'single-leg comparisons are not current full production SGM replay or SGM profitability']
    (output / 'Summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False))
    print(json.dumps(summary, indent=2, allow_nan=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    run(args.protocol, args.output)
