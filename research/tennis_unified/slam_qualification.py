"""Audit every pinned singles match/point row; no model training or live writes."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from .mcp_qualification import raw_universe
from .prices import event_signature, normal
from .slam_points import RULE_PATH, replay
from .sources import csv_rows
from .warehouse import digest, storage_guard, write_new

EVENTS = {'ausopen': 'Australian Open', 'frenchopen': 'Roland Garros', 'wimbledon': 'Wimbledon', 'usopen': 'US Open'}
ROUNDS = {'1': 'R128', '2': 'R64', '3': 'R32', '4': 'R16', '5': 'QF', '6': 'SF', '7': 'F'}


def format_code(row):
    code = row.get('match_num', '')
    match = re.fullmatch(r'([12])([1-7])\d{2}', code)
    if not match:
        match = re.fullmatch(r'(MS|WS)([1-7])\d{2}', code)
    if not match:
        raise ValueError('unknown_match_number_schema')
    tour = 'ATP' if match[1] in ('1', 'MS') else 'WTA'
    best = 5 if tour == 'ATP' else 3
    declared = row.get('event_name', '').casefold()
    allowed = {"men's singles", 'event_ms'} if tour == 'ATP' else {"women's singles", 'event_ws'}
    if declared and declared not in allowed:
        raise ValueError('event_name_vs_match_code_conflict')
    declared_round = normal(row.get('round', ''))
    aliases = {**{'round' + str(i): str(i) for i in range(1, 8)},
               'quarterfinals': '5', 'quarters': '5', 'semifinals': '6', 'semis': '6', 'final': '7'}
    if declared_round and aliases.get(declared_round) != match[2]:
        raise ValueError('round_name_vs_match_code_conflict')
    return tour, best, ROUNDS[match[2]], bool(declared)


def canonical_identity(metadata, event, year, tour, best, stage, names, index):
    # No terminal/winner/point fields are consulted to select identity.
    players = [names.get((tour, normal(metadata[k])), set()) for k in ('player1', 'player2')]
    if any(len(p) != 1 for p in players) or players[0] == players[1]:
        return None, None, 'missing_or_ambiguous_full_player_name'
    first, second = [next(iter(p)) for p in players]
    a, b = sorted((first, second))
    candidates = [r for r in index.get((tour, a, b), []) if r['date'].startswith(str(year))
                  and event_signature(r['event_name']) == event_signature(EVENTS[event])
                  and r['best_of'] == best and r['round'] == stage]
    if len(candidates) != 1:
        return None, None, 'no_unique_canonical_event_round_format'
    return candidates[0], first, None


def audit(manifest_path, cohort_path, database, output):
    storage_guard(output)
    manifest = json.loads(manifest_path.read_text())
    if len(manifest['files']) != 98 or manifest['expected_files'] != 98:
        raise ValueError('full pinned 49-event singles corpus required')
    paths = {}
    for spec in manifest['files']:
        p = Path(spec['local_path'])
        if digest(p) != spec['sha256'] or p.stat().st_size != spec['bytes']:
            raise ValueError('captured singles source changed')
        paths[spec['path']] = p
    cohort = json.loads(cohort_path.read_text())
    names, universe = raw_universe(cohort, database)
    index = defaultdict(list)
    for r in universe:
        index[(r['tour'], r['a'], r['b'])].append(r)
    accepted = {r['key']: r for r in cohort['rows']}
    output.mkdir(exist_ok=False)
    events, aggregate, joined_keys = [], Counter(), set()
    with (output / 'matches.jsonl').open('x') as stream:
        for path in sorted(paths):
            if not path.endswith('-matches.csv'):
                continue
            match = re.fullmatch(r'slam_pointbypoint/(\d{4})-([a-z]+)-matches.csv', path)
            year, event = int(match[1]), match[2]
            if event not in EVENTS:
                raise ValueError('unknown event rules')
            metadata = csv_rows(paths[path])
            points_path = path.replace('-matches.csv', '-points.csv')
            points = csv_rows(paths[points_path])
            by_id, meta_counts = defaultdict(list), Counter(r.get('match_id') for r in metadata)
            for row in points:
                by_id[row.get('match_id')].append(row)
            reasons, parse_errors, held, numeric = Counter(), Counter(), 0, 0
            event_counts = Counter()
            orphan_points = set(by_id) - set(meta_counts)
            for key in sorted(orphan_points, key=str):
                stream.write(json.dumps({'event': event, 'year': year, 'match_id': key,
                    'reason': 'points_without_metadata', 'point_rows': len(by_id[key]),
                    'training_eligible': False}) + '\n')
            for csv_line, row in enumerate(metadata, start=2):
                key, reason, result = row.get('match_id'), None, None
                selected, first = None, None
                try:
                    if meta_counts[key] != 1:
                        raise ValueError('duplicate_metadata_match_id')
                    if None in row or any(v is None for v in row.values()):
                        raise ValueError('metadata_column_count_mismatch')
                    if row['year'] != str(year) or row['slam'] != event or key != f'{year}-{event}-{row["match_num"]}':
                        raise ValueError('metadata_event_identity_conflict')
                    if not row.get('player1') or not row.get('player2') or normal(row['player1']) == normal(row['player2']):
                        raise ValueError('invalid_participants')
                    tour, best, stage, explicit = format_code(row)
                    event_counts['format_explicit_metadata' if explicit else 'format_code_only'] += 1
                    if year >= 2020:
                        selected, first, reason = canonical_identity(row, event, year, tour, best, stage, names, index)
                    else:
                        reason = 'outside_frozen_canonical_year_scope'
                    if not by_id[key]:
                        raise ValueError('metadata_without_points')
                    result = replay(by_id[key], event, year, best)
                    numeric += result['numeric_points_replayed']
                    parse_errors.update(result['errors'])
                    if any(None in p or any(v is None for v in p.values()) for p in by_id[key]):
                        reason = 'point_column_count_mismatch'
                    elif not result['state_machine_pass']:
                        reason = 'point_state_machine_held'
                    elif row.get('status') and row['status'].casefold() not in ('complete', 'completed'):
                        reason = 'metadata_noncompleted_contract'
                    elif row.get('winner') and row['winner'] != str(result['terminal_winner']):
                        reason = 'metadata_terminal_winner_conflict'
                    elif selected is not None:
                        source = accepted.get(selected['key'])
                        if source is None:
                            reason = 'canonical_label_or_contract_held'
                        else:
                            source_first = first == source['a']
                            expected = source['sets'] if source_first else [list(reversed(s)) for s in source['sets']]
                            expected_winner = 1 if bool(source['y']) == source_first else 2
                            if result['sets'] != expected or result['terminal_winner'] != expected_winner:
                                reason = 'canonical_terminal_score_or_winner_conflict'
                            else:
                                for i, side in enumerate(('a', 'b') if source_first else ('b', 'a')):
                                    actual = [result['service_won'][i], result['service_points'][i]]
                                    if source[side + '_points'] is None:
                                        reason = 'canonical_box_missing_for_independent_check'
                                    elif source[side + '_points'] != actual:
                                        reason = 'canonical_service_points_conflict'
                                if reason is None:
                                    joined_keys.add(selected['key'])
                                    event_counts['canonical_identity_terminal_and_points_agree'] += 1
                except (ValueError, KeyError, TypeError) as e:
                    reason = str(e)
                reasons[reason or 'canonical_identity_terminal_and_points_agree'] += 1
                held += reason is not None
                stream.write(json.dumps({'event': event, 'year': year, 'match_id': key,
                    'metadata_locator': {'file': str(paths[path]), 'csv_line': csv_line},
                    'canonical_key': selected['key'] if selected else None, 'reason': reason,
                    'replay': result, 'training_eligible': False, 'publication_clock_verified': False}) + '\n')
            event_report = {'event': event, 'year': year, 'metadata_rows': len(metadata), 'point_rows': len(points),
                'metadata_columns': list(metadata[0]) if metadata else [], 'point_columns': list(points[0]) if points else [],
                'orphan_point_match_ids': sorted(orphan_points, key=str),
                'duplicate_metadata_keys': sum(n - 1 for n in meta_counts.values()), 'reasons': dict(reasons),
                'point_error_counts': dict(parse_errors), 'numeric_points_replayed': numeric, 'held_metadata': held,
                'counts': dict(event_counts),
                'optional_field_domains': {field: dict(Counter('MISSING' if not r.get(field) else ('ZERO_SENTINEL' if r[field] in ('0', '0.000') else 'NONZERO') for r in points))
                    for field in ('Speed_KMH', 'RallyCount', 'P1FirstSrvIn', 'P2FirstSrvIn', 'ElapsedTime')}}
            events.append(event_report)
            aggregate.update(metadata_rows=len(metadata), point_rows=len(points), held_metadata=held,
                             numeric_points_replayed=numeric, orphan_point_match_ids=len(orphan_points))
            print(json.dumps({'event': f'{year}-{event}', 'matches': len(metadata), 'held': held,
                              'canonical_points_agree': event_counts['canonical_identity_terminal_and_points_agree']}), flush=True)
    methods = [Path(__file__), Path(__file__).with_name('slam_points.py'), Path(__file__).with_name('mcp_qualification.py'), RULE_PATH]
    report = {'schema': 'tennis-slam-qualification/v1', 'source_manifest_sha256': digest(manifest_path),
        'cohort_sha256': digest(cohort_path), 'methods': {p.name: digest(p) for p in methods},
        'events': events, 'aggregate': dict(aggregate), 'unique_canonical_points_agree': len(joined_keys),
        'training_eligible_matches': 0, 'publication_clock_verified': False, 'promotion_eligible': False,
        'decision': 'NOT_QUALIFIED_FOR_SOURCE_AUGMENTATION',
        'limitations': ['Strict postpoint-score schema; incompatible feeds held, not silently repaired',
            'Missing status/winner is not filled from a successful point parser',
            'Old matches outside fixed canonical years lack independent result validation',
            'Format code-only evidence remains conditional until canonical corroboration',
            'Elapsed time does not establish actual event day/start/end wall clock or chart publication',
            '49 archive events are selected/missing first rounds; doubles/mixed excluded before transfer',
            'No historical publication clocks or commercial clearance; no model fitting']}
    write_new(output / 'qualification.json', report)
    write_new(output / 'artifact_manifest.json', {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('manifest', 'cohort', 'database', 'output'):
        p.add_argument('--' + n, type=Path, required=True)
    a = p.parse_args()
    audit(a.manifest, a.cohort, a.database, a.output)


if __name__ == '__main__':
    main()
