"""Quarantine newly disputed source events from BOTH targets and histories."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from .features import make_features
from .warehouse import digest, storage_guard, write_new


def isolate(data, prices):
    held = set(prices['conflicted_match_keys'])
    by_key = {r['key']: r for r in data['rows']}
    if not held <= by_key.keys() or any(r['key'] in held for r in prices['rows']):
        raise ValueError('dispute quarantine is not consistent with accepted prices')
    clean = dict(data)
    clean['rows'] = [r for r in data['rows'] if r['key'] not in held]
    clean['accepted'] = len(clean['rows'])
    clean['excluded'] = data['excluded'] + [
        {'raw_id': by_key[k]['raw_id'], 'ordinal': by_key[k]['ordinal'], 'reason': 'new_cross_source_dispute'}
        for k in sorted(held)]
    clean['excluded_counts'] = dict(Counter(r['reason'] for r in clean['excluded']))
    clean['valid_current_box_scores'] = sum(r['a_points'] is not None and r['b_points'] is not None for r in clean['rows'])
    counts = Counter((r['tour'], r['date'][:4], r['surface'], r['level']) for r in clean['rows'])
    clean['coverage'] = [dict(tour=k[0], year=k[1], surface=k[2], level=k[3], n=n) for k, n in sorted(counts.items())]
    clean['quarantine'] = {'keys': sorted(held), 'applies_to': 'all labels and all historical inputs',
                           'reason': 'unresolved publisher vs frozen source facts; not a claim that one source is correct'}
    if clean['raw_rows'] != clean['accepted'] + len(clean['excluded']) + clean['duplicate_observations']:
        raise ValueError('clean source row flow not conserved')
    return clean


def prepare(cohort, prices, output):
    storage_guard(output)
    price_data = json.loads(prices.read_text())
    if digest(cohort) != price_data['cohort_sha256']:
        raise ValueError('identity qualification used another parent cohort')
    clean = isolate(json.loads(cohort.read_text()), price_data)
    output.mkdir(exist_ok=False)
    clean['parent_cohort_sha256'] = digest(cohort)
    clean['price_dispute_audit_sha256'] = digest(prices)
    write_new(output / 'cohort.json', clean)
    rows, priors = make_features(clean['rows'])
    data = {'schema': 'tennis-unified-features/v1', 'cohort_sha256': digest(output / 'cohort.json'),
            'split_status': 'SEEN_DEV', 'pit_verified': False, 'priors': priors, 'row_count': len(rows), 'rows': rows}
    write_new(output / 'features.json', data)
    # Accepted price facts are unchanged; only their parent feature/history cohort
    # is now explicitly purged of the newly discovered disputed input events.
    qualified = dict(price_data, identity_join_parent_cohort_sha256=digest(cohort),
                     parent_identity_qualification_sha256=digest(prices),
                     cohort_sha256=digest(output / 'cohort.json'),
                     feature_input_quarantine=clean['quarantine'])
    write_new(output / 'price-cohort.json', qualified)
    files = {p.name: digest(p) for p in output.iterdir() if p.is_file()}
    write_new(output / 'artifact_manifest.json', files)
    print(json.dumps({'quarantined': len(clean['quarantine']['keys']), 'source_matches': clean['accepted'],
                      'feature_rows': len(rows), 'price_matches': qualified['matches'], 'pit_verified': False}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('cohort', 'prices', 'output'):
        p.add_argument('--' + n, type=Path, required=True)
    a = p.parse_args()
    prepare(a.cohort, a.prices, a.output)


if __name__ == '__main__':
    main()
