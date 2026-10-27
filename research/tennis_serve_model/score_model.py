"""Offline EXP-20261027-07. Never imported by production pricing.

A deliberately delayed, single-source historical reconstruction; it does not
establish original observation times or tradeable odds. Read protocol.json.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta
import hashlib
import heapq
import json
import math
from pathlib import Path
import re
import sqlite3

import numpy as np

ROOT = Path(__file__).resolve().parent
PROTOCOL = json.loads((ROOT / 'protocol.json').read_text())
SURFACES = {'Hard', 'Clay', 'Grass', 'Carpet'}
LEVELS = {'A', 'M', 'G', 'F', 'I', 'P', 'PM', 'W'}


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def score_games(score, best_of):
    """Validate a *completed* conventional match, retaining TB games only.

    Unsupported match-tiebreak sets, retirements, walks and malformed text are
    rejected. A match winner can have won fewer total games; never flip it.
    """
    if best_of not in (3, 5) or not isinstance(score, str):
        return None
    tokens = score.strip().split()
    if not tokens:
        return None
    need = best_of // 2 + 1
    ws = ls = wg = lg = 0
    for token in tokens:
        if ws == need or ls == need:
            return None
        m = re.fullmatch(r'(\d+)-(\d+)(?:\(\d+\))?', token)
        if not m:
            return None
        a, b = map(int, m.groups())
        hi, lo = max(a, b), min(a, b)
        if not ((hi == 6 and lo <= 4) or (hi == 7 and lo in (5, 6))
                or (hi >= 8 and hi - lo == 2)):
            return None
        ws += a > b
        ls += b > a
        wg += a
        lg += b
    if ws != need or ls >= need:
        return None
    return wg, lg


def extract(db, out):
    conn = sqlite3.connect('file:' + str(Path(db).resolve()) + '?mode=ro', uri=True)
    records = {}
    conflicts = set()
    reasons = Counter()
    raw = []
    for rid in PROTOCOL['raw_response_ids']:
        r = conn.execute('SELECT request_params_json,response_json FROM raw_api_responses WHERE id=?', (rid,)).fetchone()
        if r is None:
            raise ValueError('missing source response ' + str(rid))
        params, text = json.loads(r[0]), r[1]
        raw.append({'id': rid, 'sha256': hashlib.sha256(text.encode()).hexdigest(), 'params': params})
        for item in json.loads(text):
            reasons['raw_rows'] += 1
            if item.get('tourney_level') not in LEVELS or item.get('surface') not in SURFACES:
                reasons['out_of_scope'] += 1
                continue
            try:
                day = date.fromisoformat(str(item['tourney_date'])[:4] + '-' + str(item['tourney_date'])[4:6] + '-' + str(item['tourney_date'])[6:8])
                best_of = int(item['best_of'])
                winner, loser = int(item['winner_id']), int(item['loser_id'])
                tid, number = str(item['tourney_id']), str(item['match_num'])
                if not tid or not number or winner <= 0 or loser <= 0 or winner == loser:
                    raise ValueError('identity')
                if not date(2020, 1, 1) <= day < date(2026, 1, 1):
                    raise ValueError('date')
            except (KeyError, ValueError, TypeError):
                reasons['invalid_identity_date'] += 1
                continue
            games = score_games(item.get('score'), best_of)
            if games is None:
                reasons['incomplete_or_unsupported_score'] += 1
                continue
            key = (params['tour'], tid, number)
            record = {'key': '|'.join(key), 'tour': params['tour'], 'date': day.isoformat(),
                      'available': (day + timedelta(days=21)).isoformat(), 'surface': item['surface'],
                      'level': item['tourney_level'], 'best_of': best_of, 'winner': winner, 'loser': loser,
                      'winner_games': games[0], 'loser_games': games[1], 'raw_id': rid,
                      'winner_name': item['winner_name'], 'loser_name': item['loser_name']}
            if key in records:
                a, b = dict(records[key]), dict(record)
                a.pop('raw_id'); b.pop('raw_id')
                if a != b:
                    conflicts.add(key)
                reasons['duplicate_keys'] += 1
            else:
                records[key] = record
    conn.close()
    rows = [v for k, v in records.items() if k not in conflicts]
    rows.sort(key=lambda r: (r['date'], r['key']))
    reasons['conflicting_keys'] = len(conflicts)
    reasons['accepted'] = len(rows)
    payload = {'protocol_sha256': digest(ROOT / 'protocol.json'), 'raw_sources': raw,
               'exclusions': dict(reasons), 'rows': rows}
    Path(out).write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
    print(json.dumps({'coverage': dict(reasons), 'dataset_sha256': digest(out)}))


class Rating:
    def __init__(self):
        self.values = defaultdict(lambda: 1500.0)
        self.counts = Counter()

    def get(self, player, surface):
        return self.values.get((player, surface), self.values[(player, '')])

    def feature(self, a, b, surface):
        return math.log(10) / 400 * (.35 * (self.get(a, '') - self.get(b, ''))
                                   + .65 * (self.get(a, surface) - self.get(b, surface)))

    def update(self, a, b, surface, target):
        # Read all initial values before changing overall, matching Elo builder.
        initial = [(s, self.get(a, s), self.get(b, s)) for s in ('', surface)]
        for s, ra, rb in initial:
            expected = 1 / (1 + math.exp(-(ra - rb) * math.log(10) / 400))
            for player, value, residual in ((a, ra, target - expected), (b, rb, expected - target)):
                key = (player, s)
                k = 120 / (self.counts[key] + 5) ** .4
                self.values[key] = value + k * residual
                self.counts[key] += 1


def make_features(rows):
    """Predict before releasing any same-date result. Release strictly < day."""
    binary, games = Rating(), Rating()
    queue = []
    result = []
    for seq, r in enumerate(rows):
        while queue and queue[0][0] < r['date']:
            _, _, past = heapq.heappop(queue)
            a, b, s = (past['tour'], past['winner']), (past['tour'], past['loser']), past['surface']
            binary.update(a, b, s, 1.)
            games.update(a, b, s, past['winner_games'] / (past['winner_games'] + past['loser_games']))
        # Canonical orientation independent of winner; antisymmetric features.
        a, b = (r['tour'], min(r['winner'], r['loser'])), (r['tour'], max(r['winner'], r['loser']))
        n_a, n_b = binary.counts[(a, '')], binary.counts[(b, '')]
        if n_a and n_b:
            result.append(dict(r, x_binary=binary.feature(a, b, r['surface']),
                               x_games=games.feature(a, b, r['surface']), y=int(a[1] == r['winner'])))
        heapq.heappush(queue, (r['available'], seq, r))
    return result


def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -40, 40)))


def fit(x, y):
    """Deterministic Newton logistic fit, ridge 1, no intercept or scaling."""
    if len(x) < 600:
        raise ValueError('insufficient training matches')
    beta = np.zeros(x.shape[1])
    for _ in range(100):
        p = sigmoid(x @ beta)
        gradient = x.T @ (p - y) + beta
        hessian = x.T @ ((p * (1 - p))[:, None] * x) + np.eye(x.shape[1])
        step = np.linalg.solve(hessian, gradient)
        beta -= step
        if np.max(np.abs(step)) < 1e-10:
            break
    else:
        raise RuntimeError('fit did not converge')
    if not np.all(np.isfinite(beta)):
        raise RuntimeError('nonfinite coefficients')
    return beta


def losses(p, y):
    p = np.clip(p, .02, .98)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p)), (p - y) ** 2


def paired_ci(delta):
    rng = np.random.default_rng(20260826)
    # Bounded memory: no 4000 x N allocation.
    means = []
    for _ in range(4000):
        means.append(float(delta[rng.integers(0, len(delta), len(delta))].mean()))
    return np.quantile(means, [.025, .975]).tolist()


def evaluate(rows, start, end, bootstrap=False):
    train = [r for r in rows if r['date'] >= '2021-01-01' and r['available'] < start]
    test = [r for r in rows if start <= r['date'] < end]
    x_train = np.array([[r['x_binary'], r['x_games']] for r in train])
    y_train = np.array([r['y'] for r in train])
    x_test = np.array([[r['x_binary'], r['x_games']] for r in test])
    y_test = np.array([r['y'] for r in test])
    control, candidate = fit(x_train[:, :1], y_train), fit(x_train, y_train)
    probabilities = {'baseline': sigmoid(x_test[:, 0]), 'control': sigmoid(x_test[:, :1] @ control),
                     'candidate': sigmoid(x_test @ candidate)}
    vectors = {arm: losses(p, y_test) for arm, p in probabilities.items()}
    summary = {'window': [start, end], 'train_n': len(train), 'test_n': len(test),
               'max_training_label_available': max(r['available'] for r in train),
               'control_coefficients': control.tolist(), 'candidate_coefficients': candidate.tolist(),
               'metrics': {arm: {'log_loss': float(v[0].mean()), 'brier': float(v[1].mean())} for arm, v in vectors.items()},
               'deltas': {}, 'cohorts': {}}
    for reference in ('baseline', 'control'):
        summary['deltas'][reference] = {}
        for idx, metric in enumerate(('log_loss', 'brier')):
            delta = vectors['candidate'][idx] - vectors[reference][idx]
            value = {'mean': float(delta.mean())}
            if bootstrap:
                value['ci95'] = paired_ci(delta)
            summary['deltas'][reference][metric] = value
    for field in ('tour', 'surface', 'level', 'best_of'):
        groups = {}
        for val in sorted({str(r[field]) for r in test}):
            indices = [i for i, r in enumerate(test) if str(r[field]) == val]
            groups[val] = {'n': len(indices), 'metrics': {a: {'log_loss': float(v[0][indices].mean()),
                            'brier': float(v[1][indices].mean())} for a, v in vectors.items()}}
        summary['cohorts'][field] = groups
    predictions = [dict(r, **{a + '_p': float(probabilities[a][i]) for a in probabilities}) for i, r in enumerate(test)]
    return summary, predictions


def run(data, out, confirmation=False):
    source = json.loads(Path(data).read_text())
    if source['protocol_sha256'] != digest(ROOT / 'protocol.json'):
        raise ValueError('dataset/protocol mismatch')
    rows = make_features(source['rows'])
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    meta = {'experiment': PROTOCOL['experiment'], 'protocol_sha256': digest(ROOT / 'protocol.json'),
            'code_sha256': digest(__file__), 'dataset_sha256': digest(data), 'coverage': source['exclusions'],
            'feature_matches': len(rows), 'leakage_status': 'FLAG: historical observation clocks unverified; delayed research reconstruction only'}
    folds = []
    predictions = []
    for start, end in PROTOCOL['development_folds']:
        summary, pred = evaluate(rows, start, end)
        folds.append(summary)
        predictions.extend(pred)
    dev_pass = all(f['deltas'][ref][metric]['mean'] < 0 for f in folds
                   for ref in ('baseline', 'control') for metric in ('log_loss', 'brier'))
    meta.update(development=folds, development_pass=dev_pass,
                confirmation_opened=False, decision='REJECT' if not dev_pass else 'NEEDS MORE TESTING')
    (out / 'dev_predictions.json').write_text(json.dumps(predictions, separators=(',', ':')))
    if confirmation:
        if not dev_pass:
            raise ValueError('confirmation locked: development failed')
        summary, pred = evaluate(rows, *PROTOCOL['confirmation'], bootstrap=True)
        meta.update(confirmation=summary, confirmation_opened=True)
        (out / 'confirmation_predictions.json').write_text(json.dumps(pred, separators=(',', ':')))
        significant = all(summary['deltas']['control'][m]['ci95'][1] < 0 for m in ('log_loss', 'brier'))
        tour_pass = all(c['metrics']['candidate'][m] <= c['metrics']['control'][m]
                        for c in summary['cohorts']['tour'].values() for m in ('log_loss', 'brier'))
        meta['research_confirmation_pass'] = significant and tour_pass
        meta['decision'] = 'NEEDS FORWARD VALIDATION' if significant and tour_pass else 'REJECT'
    (out / 'summary.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(json.dumps(meta, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='action', required=True)
    e = sub.add_parser('extract'); e.add_argument('--db', required=True); e.add_argument('--out', required=True)
    r = sub.add_parser('run'); r.add_argument('--data', required=True); r.add_argument('--out', required=True); r.add_argument('--confirmation', action='store_true')
    a = p.parse_args()
    if a.action == 'extract':
        extract(a.db, a.out)
    else:
        run(a.data, a.out, a.confirmation)


if __name__ == '__main__':
    main()
