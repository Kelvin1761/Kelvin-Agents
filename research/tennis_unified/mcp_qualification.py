"""MCP identity/point conservation and selection coverage; no candidate fitting."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
import hashlib
import json
from pathlib import Path

from .prices import event_signature, normal
from .sources import csv_rows, qualify_metadata
from .warehouse import digest, readonly, storage_guard, write_new


def raw_universe(cohort, database):
    names, grouped = defaultdict(set), defaultdict(list)
    with readonly(database) as db:
        for spec in cohort['sources']:
            body = db.execute('SELECT response_json FROM raw_api_responses WHERE id=?', (spec['raw_id'],)).fetchone()[0]
            if hashlib.sha256(body.encode()).hexdigest() != spec['response_sha256']:
                raise ValueError('immutable raw body changed')
            tour = spec['params']['tour']
            for ordinal, r in enumerate(json.loads(body)):
                try:
                    w, l = int(r['winner_id']), int(r['loser_id'])
                    day = datetime.strptime(str(r['tourney_date']), '%Y%m%d').date().isoformat()
                    best = int(r['best_of'])
                    if w == l or best not in (3, 5) or not r['round']:
                        raise ValueError('invalid identity')
                except (KeyError, ValueError, TypeError) as e:
                    raise ValueError('cannot qualify full raw identity universe') from e
                for side, player in (('winner', w), ('loser', l)):
                    names[(tour, normal(r[side + '_name']))].add(player)
                a, b = sorted((w, l))
                key = '|'.join((tour, str(r['tourney_id']), r['round'], str(best), str(a), str(b)))
                grouped[key].append({'key': key, 'tour': tour, 'date': day, 'a': a, 'b': b,
                    'best_of': best, 'surface': r['surface'], 'round': r['round'],
                    'event_name': r['tourney_name'], 'raw_id': spec['raw_id'], 'ordinal': ordinal})
    records, conflicts = [], []
    for key, members in grouped.items():
        signatures = {tuple(r[k] for k in ('tour', 'date', 'a', 'b', 'best_of', 'surface', 'round', 'event_name')) for r in members}
        if len(signatures) != 1:
            conflicts.append(key)
        else:
            records.append(members[0])
    # Conflicting raw identity facts cannot be silently removed from candidates.
    if conflicts:
        raise ValueError('raw identity conflicts require separate resolution: ' + str(conflicts))
    return names, records


def identity(row, tour, names, records):
    players = [names.get((tour, normal(row[k])), set()) for k in ('Player 1', 'Player 2')]
    if any(len(p) != 1 for p in players) or players[0] == players[1]:
        return None, 'missing_or_ambiguous_full_player_name'
    a, b = sorted(next(iter(p)) for p in players)
    day = datetime.strptime(row['Date'], '%Y%m%d').date()
    candidates = [r for r in records if r['a'] == a and r['b'] == b
        and 0 <= (day - date.fromisoformat(r['date'])).days < 21
        and (not r['surface'] or r['surface'] == row['Surface']) and r['best_of'] == int(row['Best of'])
        and r['round'] == row['Round'].strip()
        and event_signature(r['event_name']) == event_signature(row['Tournament'])]
    if len(candidates) != 1:
        return None, 'no_unique_event_round_format_identity'
    if not candidates[0]['surface']:
        return None, 'source_surface_unknown'
    return candidates[0], None


def total_pair(metadata, rows):
    totals = [r for r in rows if r.get('set') == 'Total']
    if len(totals) != 2:
        return None, 'missing_or_duplicate_Total_rows'
    if Counter(normal(r.get('player', '')) for r in totals) != Counter(normal(metadata[k]) for k in ('Player 1', 'Player 2')):
        return None, 'Total_participant_conflict'
    values = {}
    fields = ('serve_pts', 'first_in', 'first_won', 'second_in', 'second_won', 'return_pts', 'return_pts_won', 'aces', 'dfs')
    for r in totals:
        try:
            v = {k: int(r[k]) for k in fields}
            if any(str(v[k]) != r[k] or v[k] < 0 for k in fields):
                raise ValueError('invalid count')
        except (KeyError, ValueError, TypeError):
            return None, 'invalid_Total_point_count'
        if (v['serve_pts'] <= 0 or v['first_in'] + v['second_in'] != v['serve_pts']
                or v['first_won'] > v['first_in'] or v['second_won'] > v['second_in']
                or v['aces'] > v['first_won'] + v['second_won'] or v['dfs'] > v['second_in']
                or v['return_pts_won'] > v['return_pts']):
            return None, 'invalid_Total_point_domain'
        values[normal(r['player'])] = v
    x, y = [values[normal(metadata[k])] for k in ('Player 1', 'Player 2')]
    if (x['serve_pts'] != y['return_pts'] or y['serve_pts'] != x['return_pts']
            or x['first_won'] + x['second_won'] + y['return_pts_won'] != x['serve_pts']
            or y['first_won'] + y['second_won'] + x['return_pts_won'] != y['serve_pts']):
        return None, 'opponent_point_conservation_conflict'
    return values, None


def audit(manifest_path, cohort_path, database, output):
    storage_guard(output)
    manifest = json.loads(manifest_path.read_text())
    cohort = json.loads(cohort_path.read_text())
    paths = {}
    for r in manifest['files']:
        p = Path(r['local_path'])
        if digest(p) != r['sha256']:
            raise ValueError('MCP source changed')
        paths[r['path']] = p
    names, universe = raw_universe(cohort, database)
    index = defaultdict(list)
    for r in universe:
        index[r['tour']].append(r)
    accepted = {r['key']: r for r in cohort['rows']}
    results, flow, all_qualified = [], {}, set()
    for tour, prefix in (('ATP', 'm'), ('WTA', 'w')):
        raw = csv_rows(paths[f'charting-{prefix}-matches.csv'])
        metadata, malformed = qualify_metadata(raw)
        counts = Counter(r['match_id'] for r in metadata)
        stats = defaultdict(list)
        for r in csv_rows(paths[f'charting-{prefix}-stats-Overview.csv']):
            stats[r['match_id']].append(r)
        reasons, identity_keys, point_keys = Counter(), set(), set()
        resolved = []
        for row in metadata:
            reason, selected, points = None, None, None
            if not '20200101' <= row['Date'] < '20260101':
                reason = 'outside_frozen_2020_2025_calendar_scope'
            elif counts[row['match_id']] != 1:
                reason = 'duplicate_MCP_match_id'
            else:
                selected, reason = identity(row, tour, names, index[tour])
            resolved.append((row, selected, reason))
        canonical_counts = Counter(selected['key'] for _, selected, _ in resolved if selected)
        for row, selected, reason in resolved:
            points = None
            if selected is not None:
                identity_keys.add(selected['key'])
                if selected['key'] not in accepted:
                    reason = 'canonical_source_label_or_contract_held'
                elif canonical_counts[selected['key']] != 1:
                    reason = 'duplicate_chart_for_canonical_match'
                else:
                    points, reason = total_pair(row, stats[row['match_id']])
                    if points is not None:
                        source = accepted[selected['key']]
                        for field in ('Player 1', 'Player 2'):
                            player = next(iter(names[(tour, normal(row[field]))]))
                            side = 'a' if player == source['a'] else 'b'
                            v = points[normal(row[field])]
                            expected = [v['first_won'] + v['second_won'], v['serve_pts']]
                            if source[side + '_points'] is None:
                                reason = 'source_box_unavailable_for_independent_check'
                            elif source[side + '_points'] != expected:
                                reason = 'MCP_vs_source_box_conflict'
                    if reason is None:
                        point_keys.add(selected['key'])
            reasons[reason or 'identity_and_points_agree'] += 1
            results.append({'tour': tour, 'match_id': row['match_id'], 'date': row['Date'],
                'canonical_key': selected['key'] if selected else None, 'reason': reason,
                'point_qualified': reason is None, 'training_eligible': False,
                'publication_clock_verified': False})
        all_qualified.update(point_keys)
        denominator = [r for r in cohort['rows'] if r['tour'] == tour and r['date'] < '2026-01-01']
        coverage = {}
        for field in ('surface', 'level', 'round'):
            for v in sorted({r[field] for r in denominator}):
                group = [r for r in denominator if r[field] == v]
                n = sum(r['key'] in point_keys for r in group)
                coverage[field + ':' + str(v)] = {'population': len(group), 'qualified': n, 'coverage': n / len(group)}
        flow[tour] = {'raw_metadata': len(raw), 'typed': len(metadata), 'malformed_held': malformed,
            'reasons': dict(reasons), 'unique_identity_matches': len(identity_keys),
            'point_and_source_box_agreement_matches': len(point_keys), 'population': len(denominator),
            'coverage': len(point_keys) / len(denominator), 'subgroups': coverage,
            'overview_without_typed_metadata': len(set(stats) - set(counts))}
    output.mkdir(exist_ok=False)
    report = {'scope': 'Full captured MCP metadata/Overview vs frozen 2020-25 source cohort; no new independent match samples',
        'sources_sha256': digest(manifest_path), 'cohort_sha256': digest(cohort_path), 'method_sha256': digest(Path(__file__)),
        'raw_identity_records': len(universe), 'raw_identity_missing_surface': sum(not r['surface'] for r in universe),
        'tours': flow, 'unique_point_qualified_matches': len(all_qualified), 'rows': results,
        'publication_clock_verified': False, 'training_eligible_matches': 0, 'promotion_eligible': False,
        'decision': 'NOT_QUALIFIED_FOR_SOURCE_AUGMENTATION',
        'limitations': ['Capture/commit time is not chart publication time',
            'Exact full-name join is conservative; held aliases are not fuzzy-resolved',
            'Charted subset coverage is not representative sampling or selection-bias correction',
            'Per-set Overview rows never added to Total; conflicting charts/source counts held',
            'NC-SA research source does not establish commercial clearance']}
    write_new(output / 'qualification.json', report)
    write_new(output / 'artifact_manifest.json', {'qualification.json': digest(output / 'qualification.json')})
    print(json.dumps({k: report[k] for k in ('unique_point_qualified_matches', 'training_eligible_matches', 'decision')}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('manifest', 'cohort', 'database', 'output'):
        p.add_argument('--' + n, type=Path, required=True)
    a = p.parse_args()
    audit(a.manifest, a.cohort, a.database, a.output)


if __name__ == '__main__':
    main()
