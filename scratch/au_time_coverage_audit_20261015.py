#!/usr/bin/env python3
"""Paired diagnostics and replay controls; cannot choose or deploy a model."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import numpy as np

from au_neutral_speed_20261015 import diff, estimate, sha
from au_leaf_power import within_race_auc


def main():
    ap = argparse.ArgumentParser()
    for name in ('predictions', 'prior', 'tas_only', 'out'):
        ap.add_argument('--'+name.replace('_', '-'), type=Path, required=True)
    args = ap.parse_args()
    races = json.loads(args.predictions.read_text())['races']
    identity = lambda race: (race['meeting'], race['race'])
    prior = {identity(r): r for r in json.loads(args.prior.read_text())['races']}
    tas_only = {identity(r): r for r in json.loads(args.tas_only.read_text())['races']}
    maximum, matched, changed = 0., 0, 0
    for race in races:
        old = {r['n']: r for r in prior[identity(race)]['rows']}
        before_binding = {r['n']: r for r in tas_only[identity(race)]['rows']}
        for row in race['rows']:
            assert row['name'] == old[row['n']]['name']
            maximum = max(maximum, abs(row['Q']-old[row['n']]['deployed']))
            matched += 1
            for source in ('Q', 'QT'):
                audit = row[source+'_audit']
                if audit.get('previous_date'):
                    assert audit['previous_date'] < race['date']
            row['before_binding_data'] = before_binding[row['n']]['QT']
            row['before_binding_latest'] = before_binding[row['n']]['QTL']
            changed += row['QT'] != row['before_binding_data']
    report = {'input_hashes': {n: sha(getattr(args, n)) for n in ('predictions', 'prior', 'tas_only')},
        'baseline_replay_max_error': maximum, 'matched_runner_rows': matched,
        'binding_changed_scores': changed,
        'original_A_budget_context_only': diff(races, 'Q', 'ability'),
        'isolated_binding_data': diff(races, 'before_binding_data', 'QT'),
        'isolated_binding_with_latest': diff(races, 'before_binding_latest', 'QTL')}
    # The neutral score is just previous-run total residual: no other model leaves.
    # Compare both sources on exactly the same covered runners/pairs.
    daily = {k: defaultdict(lambda: np.zeros(2)) for k in ('old_time', 'new_time', 'baseline')}
    comparable = 0
    for race in races:
        rows = [r for r in race['rows'] if r['Q_raw'] is not None and r['QT_raw'] is not None]
        for key, field in [('old_time', 'Q_raw'), ('new_time', 'QT_raw'), ('baseline', 'Q')]:
            c, n = within_race_auc([(r[field], r['pos'] <= 3) for r in rows])
            daily[key][race['date']] += [c, n]
        comparable += n > 0
    days = sorted({r['date'] for r in races})
    report['neutral_common_cohort'] = {k: estimate([v[d] for d in days]) for k, v in daily.items()}
    report['neutral_common_cohort']['comparable_races'] = comparable
    report['neutral_common_cohort']['paired_time_delta'] = estimate([
        [daily['new_time'][d][0]-daily['old_time'][d][0], daily['old_time'][d][1]] for d in days], paired=True)
    # Newly covered rows are reported separately; they must not inflate a paired comparison.
    new_daily = defaultdict(lambda: np.zeros(2))
    for race in races:
        rows = [r for r in race['rows'] if r['QT_raw'] is not None]
        new_daily[race['date']] += within_race_auc([(r['QT_raw'], r['pos'] <= 3) for r in rows])
    report['neutral_new_source_all_covered_different_cohort'] = estimate([new_daily[d] for d in days])
    args.out.write_text(json.dumps(report, indent=2))
    print('replay', maximum, 'matched', matched, flush=True)


if __name__ == '__main__':
    main()
