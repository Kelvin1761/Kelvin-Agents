"""Strict dated-source CSV repair. Post-race metadata is never PIT certification."""
from collections import Counter
from copy import deepcopy
import math
import re

FILLABLE = ('Barrier', 'Weight', 'Jockey', 'Distance', 'Condition', 'Margin')
BLANK = {'', '—', '-'}


def track_key(value):
    # Keep course layout tokens: never collapse Hillside/Lakeside/Heath.
    return re.sub(r'[^a-z0-9]', '', str(value or '').casefold())


def horse_key(value):
    text = re.sub(r'\([^)]*\)', '', str(value or '').casefold())
    return re.sub(r'[^a-z0-9]', '', text)


def key(row):
    return (str(row.get('Date') or '').strip(), track_key(row.get('Track')),
            str(row.get('Race') or '').strip(), horse_key(row.get('Horse')))


def blank(value):
    return str(value if value is not None else '').strip() in BLANK


def comparable(column, value):
    value = str(value).strip()
    if column in ('Barrier', 'Weight', 'Distance', 'Margin', 'Pos'):
        if column == 'Margin':
            value = value.removesuffix('L').strip()
        number = float(value)
        if not math.isfinite(number) or number < 0:
            raise ValueError('invalid numeric result metadata')
        if column in ('Barrier', 'Distance', 'Pos') and (number <= 0 or not number.is_integer()):
            raise ValueError('invalid integer result metadata')
        if column == 'Weight' and number <= 0:
            raise ValueError('invalid runner weight')
        return number
    return value.casefold()


def canonical(column, value):
    """Written form. Margin follows the corpus convention `au_results_ingest.load_sb_csv`
    already uses (`1.25` -> `1.25L`): readers that need the unit parse `<n>L`, and a
    bare number silently reads as "no margin" (2026-10-13: 22,575 repaired cells and
    ~3,400 April-June cells were invisible to the `MARGIN_L` harness regex)."""
    value = str(value).strip()
    if column == 'Margin' and not value.endswith('L'):
        return f'{value}L'
    return value


def repair_rows(original, sources, lineage):
    """Fill verified same-identity blanks, preserve all originals and conflicts."""
    links = {}
    for link in lineage:
        raw = link.get('key')
        if not isinstance(raw, (list, tuple)) or len(raw) != 4:
            raise ValueError('missing lineage identity')
        identity = (str(raw[0]), track_key(raw[1]), str(raw[2]), horse_key(raw[3]))
        if identity in links:
            raise ValueError('duplicate lineage identity')
        links[identity] = link
    if set(links) != {key(row) for row in sources}:
        raise ValueError('lineage identity set mismatch')
    original = deepcopy(original)
    counts = Counter(key(r) for r in original)
    if any(n > 1 for n in counts.values()):
        raise ValueError('duplicate canonical identities')
    source_counts = Counter(key(r) for r in sources)
    lookup = {}
    quarantined, conflicts, filled = [], [], []
    for row in sources:
        identity = key(row)
        link = links[identity]
        reason = None
        if source_counts[identity] != 1:
            reason = 'duplicate_source_identity'
        elif not identity[1] or track_key(link.get('dated_run_track')) != identity[1]:
            reason = 'track_alias_unverified'
        elif str(link.get('dated_run_date')) != identity[0] or str(link.get('dated_run_race')) != identity[2]:
            reason = 'dated_run_identity_mismatch'
        elif not re.fullmatch('[0-9a-f]{64}', str(link.get('source_sha256') or '')):
            reason = 'missing_source_hash'
        if reason:
            quarantined.append({'key': identity, 'reason': reason})
            continue
        lookup[identity] = (row, link)
    for row in original:
        identity = key(row)
        if identity not in lookup:
            continue
        source, link = lookup[identity]
        try:
            same_pos = comparable('Pos', row.get('Pos')) == comparable('Pos', source.get('Pos'))
        except (ValueError, TypeError):
            same_pos = False
        if not same_pos:
            conflicts.append({'key': identity, 'column': 'Pos', 'existing': row.get('Pos'), 'source': source.get('Pos'), 'action': 'entire_row_quarantined'})
            continue
        for column in FILLABLE:
            incoming = source.get(column)
            if blank(incoming):
                continue
            try:
                value = comparable(column, incoming)
            except (ValueError, TypeError):
                conflicts.append({'key': identity, 'column': column, 'source': incoming, 'action': 'invalid_source_value_skipped'})
                continue
            if not blank(row.get(column)):
                try:
                    equal = comparable(column, row[column]) == value
                except (ValueError, TypeError):
                    equal = False
                if not equal:
                    conflicts.append({'key': identity, 'column': column, 'existing': row[column], 'source': incoming, 'action': 'existing_value_preserved'})
                continue
            before = row.get(column)
            row[column] = canonical(column, incoming)
            filled.append({'key': identity, 'column': column, 'before': before, 'after': row[column], 'source_sha256': link['source_sha256'], 'source_path': link.get('source_path'), 'usage': 'post_race_metadata_only'})
    return original, {'filled': filled, 'conflicts': conflicts, 'quarantined_sources': quarantined, 'source_rows': len(sources), 'verified_source_rows': len(lookup)}
