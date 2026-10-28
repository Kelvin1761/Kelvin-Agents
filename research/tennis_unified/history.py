"""Source-isolated SEEN_DEV history; never a verified historical PIT corpus.

Read frozen season raw responses, not mutable player-history ordinal joins.
Current-match box scores are labels for later history only, never row features.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re

from .warehouse import readonly, write_new

RAW_IDS = (1447, 1448, 1449, 1450, 1451, 1452, 1454, 1455, 1456, 1457, 1458, 1459)
SURFACES = {'Hard', 'Clay', 'Grass', 'Carpet'}
LEVELS = {'A', 'M', 'G', 'F', 'I', 'P', 'PM', 'W'}
KNOCKOUT = {'F', 'SF', 'QF', 'R16', 'R32', 'R64', 'R128', 'Q1', 'Q2', 'Q3'}


def positive_int(value):
    if value is None or isinstance(value, bool) or not re.fullmatch(r'\d+', str(value)):
        return None
    result = int(value)
    return result if result > 0 else None


def score_sets(score, best_of):
    """Completed conventional sets only, matching EXP-20261027-07 eligibility."""
    if best_of not in (3, 5) or not isinstance(score, str) or not score.strip():
        return None
    wins = losses = 0
    result = []
    for token in score.split():
        if max(wins, losses) == best_of // 2 + 1:
            return None
        match = re.fullmatch(r'(\d+)-(\d+)(?:\(\d+\))?', token)
        if not match:
            return None
        a, b = map(int, match.groups())
        hi, lo = max(a, b), min(a, b)
        if not ((hi == 6 and lo <= 4) or (hi == 7 and lo in (5, 6))
                or (hi >= 8 and hi - lo == 2)):
            return None
        wins += a > b
        losses += b > a
        result.append([a, b])
    if wins != best_of // 2 + 1 or losses >= best_of // 2 + 1:
        return None
    return result


def points(item, prefix):
    names = ('svpt', '1stIn', '1stWon', '2ndWon')
    raw = [item.get(prefix + '_' + name) for name in names]
    if any(v is None or not re.fullmatch(r'\d+', str(v)) for v in raw):
        return None
    total, first_in, first_won, second_won = map(int, raw)
    if total <= 0 or not 0 <= first_won <= first_in <= total or not 0 <= second_won <= total - first_in:
        return None
    return [first_won + second_won, total]


def parse_row(item, tour, raw_id, ordinal):
    if item.get('surface') not in SURFACES or item.get('tourney_level') not in LEVELS:
        return None, 'out_of_scope'
    try:
        text = str(item['tourney_date'])
        if not re.fullmatch(r'\d{8}', text):
            raise ValueError('date')
        day = date(int(text[:4]), int(text[4:6]), int(text[6:]))
        winner, loser = positive_int(item.get('winner_id')), positive_int(item.get('loser_id'))
        best_of = positive_int(item.get('best_of'))
        event, number = str(item.get('tourney_id') or '').strip(), str(item.get('match_num') or '').strip()
        stage = str(item.get('round') or '').strip()
        if not date(2020, 1, 1) <= day < date(2026, 1, 1) or not winner or not loser or winner == loser:
            raise ValueError('identity')
        if not event or not re.fullmatch(r'\d+', number) or not stage:
            raise ValueError('anchor')
    except (KeyError, ValueError, TypeError):
        return None, 'invalid_identity_date'
    sets = score_sets(item.get('score'), best_of)
    if sets is None:
        return None, 'incomplete_or_unsupported_score'
    a, b = min(winner, loser), max(winner, loser)
    w_points, l_points = points(item, 'w'), points(item, 'l')
    return {
        'tour': tour, 'date': day.isoformat(), 'available': (day + timedelta(days=21)).isoformat(),
        'event': event, 'round': stage, 'number': number, 'best_of': best_of,
        'a': a, 'b': b, 'y': int(a == winner), 'surface': item['surface'], 'level': item['tourney_level'],
        'sets': sets if a == winner else [list(reversed(s)) for s in sets],
        'a_points': w_points if a == winner else l_points, 'b_points': l_points if a == winner else w_points,
        'a_rank': positive_int(item.get('winner_rank' if a == winner else 'loser_rank')),
        'b_rank': positive_int(item.get('loser_rank' if a == winner else 'winner_rank')),
        'raw_id': raw_id, 'ordinal': ordinal,
    }, None


def canonicalise(rows):
    """Collapse known event anchors, holding unknown repeats and conflicts.

    Ordinals are source locators, never sole cross-observation event identities.
    Missing measurements are not contradictions; unequal non-missing facts are.
    """
    groups = defaultdict(list)
    for row in rows:
        groups[(row['tour'], row['event'], row['round'], row['best_of'], row['a'], row['b'])].append(row)
    selected, held, collapsed = [], [], []
    facts = ('date', 'y', 'surface', 'level', 'sets', 'a_points', 'b_points', 'a_rank', 'b_rank')
    for anchor, members in sorted(groups.items()):
        reason = None
        if len(members) > 1 and anchor[2] not in KNOCKOUT:
            # Even identical RR scores cannot prove two source ordinals are one match.
            if len({r['number'] for r in members}) != 1:
                reason = 'unverified_repeat_event_identity'
        if any(len({json.dumps(r[k], sort_keys=True) for r in members if r[k] is not None}) > 1 for k in facts):
            reason = 'source_facts_conflict'
        if reason:
            held.extend({'raw_id': r['raw_id'], 'ordinal': r['ordinal'], 'reason': reason} for r in members)
            continue
        first = min(members, key=lambda r: (r['raw_id'], r['ordinal']))
        # Select one immutable observation; never merge fields into a synthetic row.
        row = dict(first, key='|'.join(map(str, anchor)))
        selected.append(row)
        if len(members) > 1:
            collapsed.append({'key': row['key'], 'selected': [first['raw_id'], first['ordinal']],
                              'members': [[r['raw_id'], r['ordinal']] for r in members]})
    selected.sort(key=lambda r: (r['date'], r['key']))
    return selected, held, collapsed


def extract(database: Path):
    parsed, rejected, sources, year_boundaries = [], [], [], []
    with readonly(database) as conn:
        for raw_id in RAW_IDS:
            r = conn.execute('SELECT provider_name,endpoint,request_params_json,fetched_at,response_json '
                             'FROM raw_api_responses WHERE id=?', (raw_id,)).fetchone()
            if r is None or r['provider_name'] != 'jeff_sackmann':
                raise ValueError('missing or wrong raw source: ' + str(raw_id))
            params = json.loads(r['request_params_json'])
            tour, year = params['tour'], params['year']
            expected = ('https://raw.githubusercontent.com/JeffSackmann/tennis_' + tour.lower()
                        + '/master/' + tour.lower() + '_matches_' + str(year) + '.csv')
            if tour not in ('ATP', 'WTA') or year not in range(2020, 2026) or r['endpoint'] != expected:
                raise ValueError('source identity mismatch')
            body = r['response_json']
            items = json.loads(body)
            sources.append({'raw_id': raw_id, 'provider': r['provider_name'], 'url': expected,
                            'params': params, 'fetched_at': r['fetched_at'], 'rows': len(items),
                            'response_sha256': hashlib.sha256(body.encode()).hexdigest()})
            for ordinal, item in enumerate(items):
                row, reason = parse_row(item, tour, raw_id, ordinal)
                if row is None:
                    rejected.append({'raw_id': raw_id, 'ordinal': ordinal, 'reason': reason})
                else:
                    parsed.append(row)
                    if int(row['date'][:4]) != year:
                        year_boundaries.append({'raw_id': raw_id, 'ordinal': ordinal, 'date': row['date'],
                                                'season': year, 'disposition': 'retained_calendar_boundary'})
    if {(r['params']['tour'], r['params']['year']) for r in sources} != {
            (t, y) for t in ('ATP', 'WTA') for y in range(2020, 2026)}:
        raise ValueError('incomplete fixed season roster')
    rows, held, collapsed = canonicalise(parsed)
    rejected.extend(held)
    raw_n = sum(s['rows'] for s in sources)
    duplicate_n = sum(len(c['members']) - 1 for c in collapsed)
    if raw_n != len(rows) + len(rejected) + duplicate_n:
        raise ValueError('row-flow does not conserve observations')
    coverage = Counter((r['tour'], r['date'][:4], r['surface'], r['level']) for r in rows)
    return {'schema': 'tennis-unified-source-cohort/v1', 'split_status': 'SEEN_DEV',
            'eligibility_scope': 'single-source synthetic-availability development only',
            'pit_verified': False, 'promotion_eligible': False, 'source_database': str(database),
            'sources': sources, 'raw_rows': raw_n, 'accepted': len(rows), 'duplicate_observations': duplicate_n,
            'season_calendar_boundaries': year_boundaries,
            'excluded_counts': dict(Counter(r['reason'] for r in rejected)),
            'valid_current_box_scores': sum(r['a_points'] is not None and r['b_points'] is not None for r in rows),
            'coverage': [{'tour': k[0], 'year': k[1], 'surface': k[2], 'level': k[3], 'n': n}
                         for k, n in sorted(coverage.items())],
            'excluded': rejected, 'collapsed': collapsed, 'rows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = extract(args.db)
    write_new(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('rows', 'sources', 'excluded', 'collapsed', 'coverage')}))


if __name__ == '__main__':
    main()
