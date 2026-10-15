#!/usr/bin/env python3
"""Locked, read-only GPS runner-time research. No production model edits."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import statistics
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / '.agents/skills/au_racing/au_wong_choi_auto/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / '.agents/skills/shared_racing/scripts'))
from au_result_identity import normalize_venue_name  # noqa: E402
from au_unused_field_power import RE_RUNNER, RE_HDR_DIST, norm  # noqa: E402
from au_speed_venue_audit import parse_run, build_asof_standards, _zs  # noqa: E402
from corpus_paths import meeting_dirs  # noqa: E402

BASE = 'https://www.racingqueensland.com.au'
INDEX = BASE + '/industry/thoroughbred/thoroughbred-sectionals'
ARMS = ('measured', 'winner_only', 'margin_estimate')


def condition_key(value):
    value = str(value).lower().strip()
    for label in ('good', 'soft', 'heavy', 'firm', 'synthetic'):
        if value.startswith(label):
            return label
    return {'1': 'firm', '2': 'firm', '3': 'good', '4': 'good',
            '5': 'soft', '6': 'soft', '7': 'soft', '8': 'heavy',
            '9': 'heavy', '10': 'heavy'}.get(value, value)


def get(url):
    with urlopen(Request(url, headers={'User-Agent': 'WongChoi-Research/1.0'}), timeout=30) as response:
        return response.read()


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get('href', '')
        match = re.search(r'/([0-9]{8})_', href)
        if tag == 'a' and href.endswith('.csv') and match and '20260101' <= match[1] <= '20261014':
            self.links.append(href)


def fetch(cache):
    cache.mkdir(parents=True, exist_ok=True)
    index = cache / 'index.html'
    if not index.exists():
        index.write_bytes(get(INDEX))
    parser = Links()
    parser.feed(index.read_text())

    def download(link):
        name = link.split('/')[-1]
        path = cache / name
        if not path.exists():
            path.write_bytes(get(BASE + link))
            time.sleep(.2)
        data = path.read_bytes()
        if not data.lstrip().startswith(b'Date,RaceNumber,'):
            raise ValueError('unexpected official CSV format: ' + name)
        return {'url': BASE + link, 'file': name, 'bytes': len(data),
                'sha256': hashlib.sha256(data).hexdigest()}

    records = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for record in pool.map(download, sorted(set(parser.links))):
            records.append(record)
            if len(records) % 25 == 0:
                print('downloaded', len(records), flush=True)
    (cache / 'manifest.json').write_text(json.dumps(records, indent=2))
    print('complete', len(records), sum(r['bytes'] for r in records), flush=True)


def seconds(value):
    parts = value.strip().split(':')
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    if len(parts) != 3:
        raise ValueError('expected H:M:S')
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])


def parse_csv(text, source):
    """Whole-race GPS CSV. Never consume header time or use rank as a feature."""
    import csv
    context = None
    records, counts = [], Counter()
    for columns in csv.reader(text.splitlines()):
        if len(columns) < 3:
            continue
        payload = ','.join(columns[2:]).split(';')
        if columns[0] == 'Date':
            match = re.search(r'([0-9]+)m(?:_TRACK)?$', payload[-1])
            date = re.search(r'\d{4}-\d{2}-\d{2}', payload[1])
            venue = re.sub(r'^\d{4}-\d{2}-\d{2}\s+|\s+QLD\s*-.*$', '', payload[1])
            context = (date[0], normalize_venue_name(venue), int(match[1]) if match else None) if date else None
            continue
        if context is None:
            counts['missing_header'] += 1
            continue
        counts['rows'] += 1
        if len(payload) < 5 or (len(payload) - 2) % 3:
            counts['bad_shape'] += 1
            continue
        date = datetime.strptime(columns[0], '%d/%m/%Y').date().isoformat()
        points = [float(payload[i]) for i in range(2, len(payload), 3)]
        speeds = [float(payload[i]) for i in range(3, len(payload), 3)]
        splits = [seconds(payload[i]) for i in range(4, len(payload), 3)]
        if points[-1] != context[2]:
            counts['template_distance_mismatch'] += 1
        if (date != context[0] or points != sorted(set(points)) or not 0 < points[0] <= 400 or
                any(b-a != 200 for a, b in zip(points, points[1:])) or
                any(s <= 0 for s in splits) or any(s <= 0 for s in speeds)):
            counts['invalid_or_untracked'] += 1
            continue
        total = round(sum(splits), 3)
        # Some track-template labels disagree with actual endpoints (e.g.
        # ROCK_1100m_TRACK while complete sections end at 1050). The endpoint
        # must independently match the historical formguide distance at join.
        distance = int(points[-1])
        if not 8 < distance / total < 22:
            counts['invalid_average_speed'] += 1
            continue
        records.append({'date': date, 'track': context[1], 'distance': distance,
                        'race': int(columns[1]), 'horse': norm(payload[0]),
                        'time': total, 'tab': int(payload[1]), 'source': source})
    return records, counts


def archive(root):
    blocks = {}
    conditions = defaultdict(set)
    winner_names = defaultdict(set)
    counts = Counter()
    manifests = []
    for meeting in meeting_dirs(root):
        for path in sorted(meeting.glob('*Formguide.md')):
            raw = path.read_bytes()
            text = raw.decode('utf-8', errors='replace')
            manifests.append((str(path), hashlib.sha256(raw).hexdigest()))
            counts['formguides'] += 1
            counts['winning_time_tokens'] += text.count('WinningTime:')
            counts['runner_time_tokens'] += text.count('Runner Time:')
            header = RE_HDR_DIST.search(text)
            matches = list(RE_RUNNER.finditer(text))
            for i, match in enumerate(matches):
                block = text[match.start():matches[i+1].start() if i+1 < len(matches) else len(text)]
                runs = []
                lines = block.splitlines()
                for line_i, line in enumerate(lines):
                    run = parse_run(line)
                    if run is not None:
                        run['track'] = normalize_venue_name(run['track'])
                        # Missing beaten margin is missing, never default zero.
                        run['margin'] = float(m[1]) if (m := re.search(r'\bmargin:([-\d.]+)', line)) else None
                        runs.append(run)
                        key = (run['track'], run['date'], run['race'], run['distance'])
                        run['condition'] = condition_key(run['condition'])
                        conditions[key].add(run['condition'])
                        # Historical result line belongs to this completed run,
                        # not the target race. Require a named tracked winner.
                        following = lines[line_i+1] if line_i+1 < len(lines) else ''
                        winner = re.match(r'^1-(.+?)\s*\(', following)
                        if winner:
                            winner_names[key].add(norm(winner[1]))
                if header:
                    blocks[(meeting.name, int(header[1]), norm(match[2]))] = runs
    return blocks, conditions, winner_names, counts, manifests


def features(runs, date, standards, official, winners):
    base, going, _ = standards
    figures = {arm: [] for arm in ARMS}
    seen = set()
    for run in runs:
        key = (run['track'], run['date'], run['race'], run['distance'])
        if run['date'] >= date or key in seen or run['margin'] is None:
            continue
        seen.add(key)
        own, winner = official.get(key), winners.get(key)
        standard = base.get((run['track'], run['distance']))
        if own is None or winner is None or standard is None:
            continue
        times = {'measured': own, 'winner_only': winner,
                 'margin_estimate': winner + run['margin'] * 2.4 / (run['distance'] / winner)}
        for arm, elapsed in times.items():
            figures[arm].append(-(elapsed - standard - going.get(run['condition'], 0)) / (run['distance'] / 1000))
    return {arm: statistics.mean(sorted(values)[-3:]) if len(values) >= 3 else None
            for arm, values in figures.items()}


def evaluate(args):
    import numpy as np
    from au_eval import _counts, _counts_by_field, _stage4_metric_rows, default_scorer
    from au_leaf_power import within_race_auc
    from model_evaluation_decision import evaluate_full_record, holm_adjust

    blocks, conditions, winner_names, counts, manifest = archive(args.root)
    official, conflict_keys = {}, set()
    source_manifest = json.loads((args.cache / 'manifest.json').read_text())
    for record in source_manifest:
        path = args.cache / record['file']
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == record['sha256']
        parsed, quality = parse_csv(raw.decode('utf-8-sig'), record['url'])
        counts.update({'official_' + key: value for key, value in quality.items()})
        for row in parsed:
            key = (row['track'], row['date'], row['race'], row['distance'])
            pair = (key, row['horse'])
            if pair in official and official[pair] != row['time']:
                conflict_keys.add(pair)
            official[pair] = row['time']
    for pair in conflict_keys:
        official.pop(pair, None)
    by_horse = defaultdict(dict)
    for (key, name), elapsed in official.items():
        by_horse[name][key] = elapsed
    counts['official_unique_measured'] = len(official)
    counts['official_conflicts'] = len(conflict_keys)
    winners, references = {}, []
    for key, names in winner_names.items():
        if len(names) != 1 or len(conditions[key]) != 1:
            continue
        value = official.get((key, next(iter(names))))
        if value is None:
            continue
        winners[key] = value
        references.append({'track': key[0], 'date': key[1], 'race': key[2],
                           'distance': key[3], 'condition': next(iter(conditions[key])),
                           'winning_time': value})
    references.sort(key=lambda row: row['date'])
    counts['reference_races'] = len(references)
    races = json.loads(args.baseline.read_text())['races']
    races = [r for r in races if '2026-08-05' <= r['date'] <= '2026-10-14'
             and sum(row['pos'] <= 3 for row in r['rows']) >= 3
             and any(row['pos'] == 1 for row in r['rows'])]
    dates = sorted({r['date'] for r in races})
    standards = build_asof_standards(references, dates)
    covered, auc, matched_differences = [], [], []
    for race in races:
        race['rows'].sort(key=lambda row: row['n'])
        values = {arm: [] for arm in ARMS}
        for row in race['rows']:
            assert abs(default_scorer(row) - row['ability']) < .00011
            runs = blocks.get((race['meeting'], race['race'], norm(row['name'])), [])
            lookup = by_horse.get(norm(row['name']), {})
            own_values = features(runs, race['date'], standards[race['date']], lookup, winners)
            row['time_features'] = own_values
            for arm in ARMS:
                values[arm].append(own_values[arm])
            if own_values['measured'] is not None:
                matched_differences.append(own_values['measured'] - own_values['margin_estimate'])
        for arm in ARMS:
            for row, z in zip(race['rows'], _zs(values[arm])):
                row[arm] = round(row['ability'] + .5 * z, 4)
        covered.append(sum(value is not None for value in values['measured']))
        pairs = [(row['time_features']['measured'], row['pos'] <= 3)
                 for row in race['rows'] if row['time_features']['measured'] is not None]
        if any(p[1] for p in pairs) and any(not p[1] for p in pairs):
            concordant, comparable = within_race_auc(pairs)
            auc.append(concordant/comparable)
    print('features complete', len(races), 'races', sum(covered), 'covered runners', flush=True)

    def compare(base_key, candidate_key, subset):
        baseline_rows = _stage4_metric_rows(subset, lambda row: row[base_key])
        candidate_rows = _stage4_metric_rows(subset, lambda row: row[candidate_key])
        decision = evaluate_full_record(
            domain='au', mode='walk_forward_oos', dates=[r['date'] for r in subset],
            baseline_rows=baseline_rows, candidate_rows=candidate_rows,
            leakage_audit_passed=False,
            ranking_metrics=('top3_capture_at5', 'ndcg_at5', 'top5_pairwise_auc'))
        # Separate descriptive effects from a promotion decision which must FLAG.
        b = np.array([[float(m[k]) for k in ('gold', 'good_positional')] for m in baseline_rows])
        c = np.array([[float(m[k]) for k in ('gold', 'good_positional')] for m in candidate_rows])
        ids = {d: [i for i, r in enumerate(subset) if r['date'] == d] for d in sorted({r['date'] for r in subset})}
        delta = c-b
        sums = np.array([delta[idx].sum(axis=0) for idx in ids.values()])
        sizes = np.array([len(idx) for idx in ids.values()])
        rng = np.random.default_rng(7)
        boot = []
        for _ in range(2000):
            chosen = rng.integers(0, len(ids), len(ids))
            boot.append(sums[chosen].sum(axis=0) / sizes[chosen].sum())
        boot = np.array(boot)
        ranking = ('top3_capture_at5', 'mean_top3_model_rank', 'competitive_recall_at5',
                   'ndcg_at5', 'top5_pairwise_auc')
        rank_deltas = {}
        for metric in ranking:
            paired = [(b[metric], c[metric]) for b, c in zip(baseline_rows, candidate_rows)
                      if b.get(metric) is not None and c.get(metric) is not None]
            rank_deltas[metric] = statistics.mean(c-b for b, c in paired) if paired else None
        return {'baseline': _counts(subset, lambda row: row[base_key]),
                'candidate': _counts(subset, lambda row: row[candidate_key]),
                'ranking_mean_deltas': rank_deltas,
                'primary_delta_pp': (100*delta.mean(axis=0)).tolist(),
                'primary_ci95_pp': (100*np.quantile(boot, [.025, .975], axis=0)).T.tolist(),
                'primary_bootstrap_p': [float(min(1, 2*min(np.mean(boot[:,j] <= 0), np.mean(boot[:,j] >= 0)))) for j in range(2)],
                'field_buckets': {'baseline': _counts_by_field(subset, lambda row: row[base_key]),
                                  'candidate': _counts_by_field(subset, lambda row: row[candidate_key])},
                'six_date_blocks': [{'dates': list(chunk), 'baseline': _counts([r for r in subset if r['date'] in chunk], lambda row: row[base_key]),
                                     'candidate': _counts([r for r in subset if r['date'] in chunk], lambda row: row[candidate_key])}
                                    for chunk in np.array_split(sorted(ids), 6)],
                'decision': decision}

    output = {'baseline_commit': '7a962be562ecb0af461daa71114b1dddf66ec8cd',
              'baseline_sha256': hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
              'source_index': INDEX, 'source_csvs': len(source_manifest),
              'archive_manifest_sha256': hashlib.sha256(json.dumps(manifest).encode()).hexdigest(),
              'counts': counts, 'races': len(races), 'dates': len(dates), 'first': dates[0], 'last': dates[-1],
              'runner_appearances': sum(len(r['rows']) for r in races),
              'measured_feature_covered': sum(covered), 'races_with_coverage': sum(n > 0 for n in covered),
              'races_with_2plus_coverage': sum(n >= 2 for n in covered),
              'feature_auc_race_mean': statistics.mean(auc) if auc else None,
              'measured_minus_estimated_feature_mean': statistics.mean(matched_differences) if matched_differences else None,
              'source_availability': 'FLAG: historical publication/capture timestamp not certified',
              'promotion_authorized': False,
              'comparisons': {arm: compare('ability', arm, races) for arm in ARMS},
              'matched_controls': {arm: compare(arm, 'measured', races) for arm in ARMS[1:]}}
    output['a_a'] = compare('ability', 'ability', races)
    assert output['a_a']['baseline'] == output['a_a']['candidate']
    assert output['a_a']['primary_delta_pp'] == [0.0, 0.0]
    assert all(value == 0 for value in output['a_a']['ranking_mean_deltas'].values())
    ps = {arm + ':' + metric: output['comparisons'][arm]['primary_bootstrap_p'][j]
          for arm in ARMS for j, metric in enumerate(('gold', 'good_positional'))}
    output['family_holm_primary_p'] = holm_adjust(ps)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    args.out.with_suffix('.predictions.json').write_text(json.dumps({'races': races}))
    print(json.dumps({k: output[k] for k in ('counts', 'races', 'dates', 'runner_appearances',
                     'measured_feature_covered', 'races_with_coverage', 'feature_auc_race_mean')}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('fetch', 'evaluate'))
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.command == 'fetch':
        fetch(args.cache)
        return
    evaluate(args)


if __name__ == '__main__':
    main()
