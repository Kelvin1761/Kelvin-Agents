"""EXP-20261027-08: offline continuous ranking prior and explicit ablations."""
import argparse
import json
import math
from pathlib import Path
import sqlite3
import numpy as np
import score_model as base

ROOT = Path(__file__).resolve().parent
PROTOCOL = json.loads((ROOT / 'rank_protocol.json').read_text())
ARMS = {'binary': [0], 'games': [0, 1], 'rank': [0, 2], 'combined': [0, 1, 2]}


def rank_feature(winner_rank, loser_rank, winner, loser):
    try:
        wr, lr = int(winner_rank), int(loser_rank)
        if not (1 <= wr <= 10000 and 1 <= lr <= 10000):
            return 0., False
    except (ValueError, TypeError):
        return 0., False
    winner_value = math.log(lr / wr)
    return (winner_value if winner < loser else -winner_value), True


def augment(db, data, out):
    payload = json.loads(Path(data).read_text())
    conn = sqlite3.connect('file:' + str(Path(db).resolve()) + '?mode=ro', uri=True)
    ranks = {}
    for rid in base.PROTOCOL['raw_response_ids']:
        r = conn.execute('SELECT request_params_json,response_json FROM raw_api_responses WHERE id=?', (rid,)).fetchone()
        tour = json.loads(r[0])['tour']
        for raw in json.loads(r[1]):
            key = '|'.join((tour, str(raw['tourney_id']), str(raw['match_num'])))
            ranks[key] = raw
    conn.close()
    coverage = {}
    for r in payload['rows']:
        raw = ranks[r['key']]
        raw_day = str(raw['tourney_date'])
        if (int(raw['winner_id']) != r['winner'] or int(raw['loser_id']) != r['loser']
                or raw_day != r['date'].replace('-', '')):
            raise ValueError('source identity mismatch ' + r['key'])
        r['x_rank'], r['rank_present'] = rank_feature(raw.get('winner_rank'), raw.get('loser_rank'), r['winner'], r['loser'])
        key = r['tour'] + ('_present' if r['rank_present'] else '_missing')
        coverage[key] = coverage.get(key, 0) + 1
    payload['rank_protocol_sha256'] = base.digest(ROOT / 'rank_protocol.json')
    payload['rank_coverage'] = coverage
    Path(out).write_text(json.dumps(payload, separators=(',', ':')))
    print(json.dumps({'rank_coverage': coverage, 'dataset_sha256': base.digest(out)}))


def evaluate(rows, start, end, eligible=None):
    train = [r for r in rows if r['date'] >= '2021-01-01' and r['available'] < start]
    test = [r for r in rows if start <= r['date'] < end]
    x = np.array([[r['x_binary'], r['x_games'], r['x_rank']] for r in train])
    y = np.array([r['y'] for r in train])
    xt = np.array([[r['x_binary'], r['x_games'], r['x_rank']] for r in test])
    yt = np.array([r['y'] for r in test])
    selected_arms = dict(ARMS) if eligible is None else {a: ARMS[a] for a in ('binary', *eligible, *(['games'] if 'combined' in eligible else []))}
    coefficients = {arm: base.fit(x[:, indices], y) for arm, indices in selected_arms.items()}
    ps = {arm: base.sigmoid(xt[:, ARMS[arm]] @ beta) for arm, beta in coefficients.items()}
    ps['baseline'] = base.sigmoid(xt[:, 0])
    vectors = {arm: base.losses(p, yt) for arm, p in ps.items()}
    result = {'window': [start, end], 'train_n': len(train), 'test_n': len(test),
              'max_training_label_available': max(r['available'] for r in train),
              'rank_present_n': sum(r['rank_present'] for r in test),
              'coefficients': {a: b.tolist() for a, b in coefficients.items()},
              'metrics': {a: {'log_loss': float(v[0].mean()), 'brier': float(v[1].mean())} for a, v in vectors.items()},
              'deltas': {}, 'cohorts': {}}
    comparisons = [('rank', 'binary'), ('combined', 'games'), ('combined', 'rank')]
    for candidate, control in comparisons:
        if eligible is not None and candidate not in eligible:
            continue
        pair = candidate + '_vs_' + control
        result['deltas'][pair] = {}
        for i, metric in enumerate(('log_loss', 'brier')):
            d = vectors[candidate][i] - vectors[control][i]
            result['deltas'][pair][metric] = {'mean': float(d.mean())}
            if eligible is not None:
                result['deltas'][pair][metric]['ci95'] = base.paired_ci(d)
    for field in ('tour', 'surface', 'level', 'best_of', 'rank_present'):
        groups = {}
        for val in sorted({str(r[field]) for r in test}):
            ix = [i for i, r in enumerate(test) if str(r[field]) == val]
            groups[val] = {'n': len(ix), 'metrics': {a: {'log_loss': float(v[0][ix].mean()),
                                                      'brier': float(v[1][ix].mean())} for a, v in vectors.items()}}
        result['cohorts'][field] = groups
    pred = [dict(r, **{a + '_p': float(ps[a][i]) for a in ps}) for i, r in enumerate(test)]
    return result, pred


def run(data, out, confirmation=False):
    payload = json.loads(Path(data).read_text())
    if payload['rank_protocol_sha256'] != base.digest(ROOT / 'rank_protocol.json'):
        raise ValueError('protocol mismatch')
    rows = base.make_features(payload['rows'])
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    folds, predictions = [], []
    for start, end in base.PROTOCOL['development_folds']:
        result, pred = evaluate(rows, start, end)
        folds.append(result); predictions.extend(pred)
    def passes(pairs):
        return all(f['deltas'][pair][metric]['mean'] < 0 for pair in pairs for f in folds for metric in ('log_loss', 'brier'))
    eligible = []
    if passes(['rank_vs_binary']):
        eligible.append('rank')
    if passes(['combined_vs_games', 'combined_vs_rank']):
        eligible.append('combined')
    meta = {'experiment': PROTOCOL['experiment'], 'protocol_sha256': base.digest(ROOT / 'rank_protocol.json'),
            'base_protocol_sha256': base.digest(ROOT / 'protocol.json'), 'code_sha256': base.digest(__file__),
            'base_code_sha256': base.digest(base.__file__), 'dataset_sha256': base.digest(data),
            'rank_coverage': payload['rank_coverage'], 'feature_matches': len(rows),
            'development': folds, 'eligible': eligible, 'confirmation_opened': False,
            'decision': 'REJECT' if not eligible else 'NEEDS MORE TESTING',
            'leakage_status': 'FLAG: reconstructed observation times; raw pre-tournament ranks not timestamp-verified. Research only.'}
    (out / 'dev_predictions.json').write_text(json.dumps(predictions, separators=(',', ':')))
    if confirmation:
        if not eligible:
            raise ValueError('confirmation locked: development failed')
        result, pred = evaluate(rows, *base.PROTOCOL['confirmation'], eligible=eligible)
        meta['confirmation'] = result; meta['confirmation_opened'] = True
        passed = []
        for arm in eligible:
            controls = ['binary'] if arm == 'rank' else ['games', 'rank']
            ci_ok = all(result['deltas'][arm+'_vs_'+c][m]['ci95'][1] < 0 for c in controls for m in ('log_loss','brier'))
            tour_ok = all(g['metrics'][arm][m] <= g['metrics'][c][m] for g in result['cohorts']['tour'].values()
                          for c in controls for m in ('log_loss','brier'))
            if ci_ok and tour_ok:
                passed.append(arm)
        meta['research_confirmation_pass'] = passed
        meta['decision'] = 'NEEDS FORWARD VALIDATION' if passed else 'REJECT'
        meta['simplest_research_candidate'] = 'rank' if 'rank' in passed else ('combined' if 'combined' in passed else None)
        (out / 'confirmation_predictions.json').write_text(json.dumps(pred, separators=(',', ':')))
    (out / 'summary.json').write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('augment'); a.add_argument('--db',required=True); a.add_argument('--data',required=True); a.add_argument('--out',required=True)
    r=sub.add_parser('run'); r.add_argument('--data',required=True); r.add_argument('--out',required=True); r.add_argument('--confirmation',action='store_true')
    args=p.parse_args()
    if args.action=='augment': augment(args.db,args.data,args.out)
    else: run(args.data,args.out,args.confirmation)

if __name__=='__main__': main()
