#!/usr/bin/env python3
"""Fixed PQ diagnostics; never writes production data or tunes weights."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--engine-root', required=True)
    p.add_argument('--data', required=True)
    p.add_argument('--out', required=True)
    a = p.parse_args()
    sys.path.insert(0, str(Path(a.engine_root) / '.agents/skills/au_racing/au_wong_choi_auto/scripts'))
    import au_eval as ev
    races = json.loads(Path(a.data).read_text())['races']
    assert len(races) == 1822
    bs = ev.default_scorer
    archived = lambda row: row['ability']
    dev, term = ev.date_partitions(races)
    identity = [(r['meeting'], r['race'], [(x['n'], x['pos']) for x in r['rows']]) for r in races]
    out = {'data_sha256': hashlib.sha256(Path(a.data).read_bytes()).hexdigest(),
           'sample_hash': hashlib.sha256(json.dumps(identity).encode()).hexdigest(),
           'races': len(races), 'diagnostics': {}}
    for label, ids in [('dev', dev), ('terminal', term)]:
        rs = [races[i] for i in ids]
        x, y = ev._stage4_metric_rows(rs, bs), ev._stage4_metric_rows(rs, archived)
        out[label + '_replay_primary_changed'] = {
            k: sum(q[k] != z[k] for q, z in zip(x, y)) for k in ('gold', 'good_positional')}
        assert not any(out[label + '_replay_primary_changed'].values())
    out['max_replay_error'] = max(abs(bs(x) - archived(x)) for r in races for x in r['rows'])
    out['pq_equals_consistency_rows'] = sum(
        x['features']['performance_quality_score'] == x['features']['consistency_score']
        for r in races for x in r['rows'])
    for mode in ('neutral', 'half', 'consistency'):
        def scorer(row):
            fs = dict(row['features'])
            fs['performance_quality_score'] = (
                60.0 if mode == 'neutral' else
                60 + .5 * (fs['performance_quality_score'] - 60) if mode == 'half' else
                fs['consistency_score'])
            return bs({**row, 'features': fs})
        item = {}
        for label, ids in [('dev', dev), ('terminal', term)]:
            rs = [races[i] for i in ids]
            base, cand = ev._counts(rs, bs), ev._counts(rs, scorer)
            item[label] = {'baseline': base, 'candidate': cand,
                           'delta': {k: cand[k] - base[k] for k in base}}
        item['evaluation'] = ev.verdict_dict(ev.compare(
            races, bs, scorer, label='PQ diagnostic ' + mode, leakage_audit_passed=True))
        out['diagnostics'][mode] = item
        Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
        print(mode, item['dev']['delta'], item['terminal']['delta'], flush=True)


if __name__ == '__main__':
    main()
