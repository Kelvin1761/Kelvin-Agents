"""Conservative source-price joins; identity is selected before labels/scores.

No live database or ledger writes. Historical quote clocks remain unverified.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata

import openpyxl

from .book_inventory import event_date, paired_columns, valid_pair
from .history import parse_row
from .warehouse import digest, readonly, storage_guard, write_new

BOOKS = ('B365', 'PS')
ALIASES = {'rolandgarros': 'french', 'frenchopen': 'french', 'tourfinals': 'tourfinals',
           'masterscup': 'tourfinals', 'wtafinals': 'tourfinals', 'wtachampionships': 'tourfinals',
           'bnpparibaswtafinals': 'tourfinals', 'nittoatpfinals': 'tourfinals'}


def normal(text):
    text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode().lower()
    return re.sub('[^a-z0-9]', '', text)


def source_aliases(name):
    words = str(name).split()
    if len(words) < 2:
        return set()
    return {normal(''.join(words[i:])) + normal(words[0])[0] for i in range(1, len(words)) if normal(words[0])}


def book_alias(name):
    words = str(name).split()
    if len(words) < 2 or not normal(words[-1]):
        return None
    return normal(''.join(words[:-1])) + normal(words[-1])[0]


def event_signature(text):
    key = normal(text)
    if key in ALIASES:
        return ALIASES[key]
    words = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode().lower()
    words = re.findall('[a-z0-9]+', words)
    stop = {'atp', 'wta', 'tennis', 'open', 'international', 'internationals', 'masters',
            'championship', 'championships', '250', '500', '1000'}
    return ''.join(w for w in words if w not in stop)


def source_stage(stage, draw_size):
    if stage in ('F', 'SF', 'QF', 'RR'):
        return stage
    if not re.fullmatch(r'R\d+', stage):
        return None
    try:
        draw, remaining = int(draw_size), int(stage[1:])
        if draw <= 1 or remaining <= 1 or remaining & (remaining - 1):
            return None
        number = math.ceil(math.log2(draw)) - int(math.log2(remaining)) + 1
        return str(number) if number > 0 else None
    except (ValueError, TypeError):
        return None


def book_stage(stage):
    key = normal(stage)
    return {'thefinal': 'F', 'final': 'F', 'semifinals': 'SF', 'semifinal': 'SF',
            'quarterfinals': 'QF', 'quarterfinal': 'QF', 'roundrobin': 'RR',
            '1stround': '1', '2ndround': '2', '3rdround': '3', '4thround': '4'}.get(key)


def identity_candidates(row, day, winner_id, loser_id, records, metadata):
    """Winner/loser IDs are treated as an unordered pair until identity resolves."""
    pair = tuple(sorted((winner_id, loser_id)))
    stage = book_stage(row.get('Round'))
    event_names = {event_signature(row.get(k, '')) for k in ('Tournament', 'Location')}
    result = []
    for r in records:
        m = metadata[r['key']]
        delta = (day - date.fromisoformat(r['date'])).days
        event = event_signature(m.get('tourney_name', ''))
        if (pair == (r['a'], r['b']) and 0 <= delta < 21
                and r['surface'].casefold() == str(row.get('Surface')).casefold()
                and r['best_of'] == row.get('Best of') and stage is not None
                and stage == source_stage(r['round'], m.get('draw_size'))
                and event and event in event_names):
            result.append(r)
    return result


def validate_outcome(row, source, winner_id):
    if winner_id != (source['a'] if source['y'] else source['b']):
        return 'winner_conflict'
    sets = []
    for n in range(1, 6):
        w, l = row.get('W' + str(n)), row.get('L' + str(n))
        if w is None and l is None:
            continue
        if (isinstance(w, bool) or isinstance(l, bool) or not isinstance(w, (int, float))
                or not isinstance(l, (int, float)) or not float(w).is_integer() or not float(l).is_integer()):
            return 'invalid_set_score'
        sets.append([int(w), int(l)] if winner_id == source['a'] else [int(l), int(w)])
    return None if sets == source['sets'] else 'score_conflict'


def resolve_observations(observations, conflicted):
    """No last-row/price fallback when one canonical event has conflicting rows."""
    groups = defaultdict(list)
    for row in observations:
        groups[row['key']].append(row)
    result, held, collapsed = [], [], []
    for key, members in sorted(groups.items()):
        if key in conflicted:
            held.extend({'locator': m['locator'], 'key': key, 'reason': 'event_has_label_or_score_conflict'} for m in members)
            continue
        signatures = {json.dumps({k: m[k] for k in ('book_event_date', 'quotes')}, sort_keys=True) for m in members}
        if len(signatures) != 1:
            held.extend({'locator': m['locator'], 'key': key, 'reason': 'multiple_unclocked_price_observations'} for m in members)
            continue
        first = min(members, key=lambda r: (r['locator']['file'], r['locator']['row']))
        result.append(first)
        if len(members) > 1:
            collapsed.append({'key': key, 'selected': first['locator'], 'members': [r['locator'] for r in members]})
    return result, held, collapsed


def qualify(cohort_path, database, source_manifest, output):
    storage_guard(output)
    cohort = json.loads(cohort_path.read_text())
    source = json.loads(source_manifest.read_text())
    if {(r['tour'], r['year']) for r in source['files']} != {(t, y) for t in ('ATP', 'WTA') for y in range(2020, 2026)}:
        raise ValueError('incomplete fixed price source roster')
    raw, names, metadata = {}, defaultdict(set), {}
    with readonly(database) as db:
        for spec in cohort['sources']:
            body = db.execute('SELECT response_json FROM raw_api_responses WHERE id=?', (spec['raw_id'],)).fetchone()[0]
            if hashlib.sha256(body.encode()).hexdigest() != spec['response_sha256']:
                raise ValueError('raw source body changed')
            raw[spec['raw_id']] = json.loads(body)
            tour = spec['params']['tour']
            for item in raw[spec['raw_id']]:
                for side in ('winner', 'loser'):
                    try:
                        player = int(item[side + '_id'])
                    except (ValueError, TypeError, KeyError):
                        continue
                    for alias in source_aliases(item.get(side + '_name', '')):
                        names[(tour, alias)].add(player)
    index = defaultdict(list)
    for r in cohort['rows']:
        item = raw[r['raw_id']][r['ordinal']]
        parsed, reason = parse_row(item, r['tour'], r['raw_id'], r['ordinal'])
        if reason is not None or any(parsed[k] != r[k] for k in parsed):
            raise ValueError('immutable raw locator no longer matches cohort facts')
        metadata[r['key']] = item
        index[(r['tour'], r['a'], r['b'])].append(r)
    excluded, observations, conflicted, count, held_books = [], [], set(), Counter(), Counter()
    for spec in source['files']:
        path, tour = Path(spec['path']), spec['tour']
        if digest(path) != spec['sha256']:
            raise ValueError('price source changed')
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            iterator = book.active.iter_rows(values_only=True)
            header = [str(v).strip() if v is not None else '' for v in next(iterator)]
            for prefix in set(paired_columns(header)) - set(BOOKS):
                held_books[prefix + ':contract_not_qualified'] += 1
            for number, values in enumerate(iterator, start=2):
                if not any(v is not None for v in values):
                    continue
                count['raw_rows'] += 1
                row, locator = dict(zip(header, values)), {'file': str(path), 'row': number}
                reason, key = None, None
                day = event_date(row.get('Date'))
                if str(row.get('Comment')).casefold() != 'completed':
                    reason = 'not_completed'
                elif day is None or not date(2020, 1, 1) <= day < date(2026, 1, 1):
                    reason = 'invalid_or_out_of_scope_actual_date'
                else:
                    wid, lid = names[(tour, book_alias(row.get('Winner')))], names[(tour, book_alias(row.get('Loser')))]
                    if len(wid) != 1 or len(lid) != 1 or wid == lid:
                        reason = 'missing_or_ambiguous_player_identity'
                    else:
                        wi, li = next(iter(wid)), next(iter(lid))
                        candidates = identity_candidates(row, day, wi, li, index[(tour, *sorted((wi, li)))], metadata)
                        if len(candidates) != 1:
                            reason = 'no_unique_event_round_format_identity'
                        else:
                            selected = candidates[0]
                            key = selected['key']
                            reason = validate_outcome(row, selected, wi)
                            if reason:
                                conflicted.add(key)
                            else:
                                quotes = []
                                for prefix in BOOKS:
                                    ow, ol = row.get(prefix + 'W'), row.get(prefix + 'L')
                                    if not valid_pair(ow, ol):
                                        held_books[prefix + ':invalid_or_missing_pair'] += 1
                                        continue
                                    oa, ob = (float(ow), float(ol)) if wi == selected['a'] else (float(ol), float(ow))
                                    overround = 1 / oa + 1 / ob
                                    if not 1 - 1e-12 <= overround <= 1.30:
                                        held_books[prefix + ':outside_fixed_vig_domain'] += 1
                                        continue
                                    quotes.append({'book': prefix, 'odds_a': oa, 'odds_b': ob, 'overround': overround,
                                                   'quote_type': 'historical_unclocked', 'captured_at': None})
                                if not quotes:
                                    reason = 'no_qualified_same_book_pair'
                                else:
                                    for q in quotes:
                                        q['weight'] = 1 / len(quotes)
                                    observations.append({k: selected[k] for k in ('key', 'date', 'available', 'tour', 'surface', 'level', 'best_of', 'a', 'b', 'y')} |
                                                        {'book_event_date': day.isoformat(), 'locator': locator, 'quotes': quotes})
                if reason:
                    excluded.append({'locator': locator, 'key': key, 'reason': reason})
        finally:
            book.close()
    joined, held, collapsed = resolve_observations(observations, conflicted)
    excluded.extend(held)
    joined.sort(key=lambda r: (r['date'], r['key']))
    duplicate_n = sum(len(c['members']) - 1 for c in collapsed)
    if count['raw_rows'] != len(joined) + len(excluded) + duplicate_n:
        raise ValueError('price row-flow mismatch')
    report = {'schema': 'tennis-unified-price-cohort/v1', 'cohort_sha256': digest(cohort_path),
              'source_manifest_sha256': digest(source_manifest), 'source_files': source['files'],
              'raw_rows': count['raw_rows'], 'matches': len(joined), 'book_rows': sum(len(r['quotes']) for r in joined),
              'excluded_counts': dict(Counter(r['reason'] for r in excluded)), 'held_book_counts': dict(held_books),
              'excluded': excluded, 'collapsed': collapsed, 'conflicted_match_keys': sorted(conflicted),
              'split_status': 'SEEN_DEV', 'pit_verified': False, 'promotion_eligible': False,
              'estimand': 'Conditional on the published historical unclocked quote; not an earlier tournament-start forecast or executable ROI',
              'join_policy': 'Unique players+event name/location+round+format+surface+0<=book_day-source_start<21, THEN labels/scores; fixed B365/PS and1<=overround<=1.30; other price contracts held',
              'rows': joined}
    write_new(output, report)
    print(json.dumps({k: report[k] for k in ('raw_rows', 'matches', 'book_rows', 'excluded_counts', 'held_book_counts')}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cohort', type=Path, required=True)
    p.add_argument('--db', type=Path, required=True)
    p.add_argument('--source-manifest', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    qualify(a.cohort, a.db, a.source_manifest, a.output)


if __name__ == '__main__':
    main()
