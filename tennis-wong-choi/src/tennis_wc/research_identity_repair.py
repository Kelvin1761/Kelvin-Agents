"""Memory-only identity-generation experiments; never a live DB repair API.

Source label agreement is not independent person identity or historical PIT
proof. No pricing/ingestion caller imports this module. Persistent connections
(including attached databases) are rejected before any read or write.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
import hashlib
import json

from tennis_wc.database.history_observations import (
    PUBLIC, _observe, ensure_history_schema, upsert_history_observation,
)
from tennis_wc.database.payload_archive import read_payload
from tennis_wc.ingestion.entity_mapping import _identity_agrees, valid_player_identity
from tennis_wc.ingestion.raw_response_store import utc_now

POLICY = 'memory-identity-split-v1'


class RepairConflict(ValueError):
    pass


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _memory_only(conn):
    databases = list(conn.execute('PRAGMA database_list'))
    if any(row[2] for row in databases):
        raise RepairConflict('identity split experiments require memory-only databases')
    names = [row[1].replace('"', '""') for row in databases]
    if any(conn.execute(f'PRAGMA "{name}".journal_mode').fetchone()[0] != 'memory'
           for name in names):
        raise RepairConflict('temporary on-disk databases are not memory-only')


def _row(conn, table, row_id):
    # Table names are internal constants, never supplied in a proposal.
    row = conn.execute(f'SELECT * FROM {table} WHERE id=?', (row_id,)).fetchone()
    if row is None:
        raise RepairConflict(f'missing {table} row {row_id}')
    return dict(row)


def _reference(row):
    return row['source_match_ref'] or row['provider_match_id']


def _source(conn, rows):
    raw = _row(conn, 'raw_api_responses', rows[0]['raw_response_id'])
    if raw['provider_name'] != rows[0]['source_provider'] or raw['status_code'] != 200:
        raise RepairConflict('raw provider/status disagrees')
    body = read_payload(conn, 'raw_response', raw['id'], raw['response_json'])
    records = json.loads(body)
    if not isinstance(records, list):
        raise RepairConflict('expected a public season-file list')
    base = _reference(rows[0]).rsplit('-', 1)[0]
    matches = [r for r in records if isinstance(r, dict)
               and f"{rows[0]['tour']}-{r.get('tourney_id')}-{r.get('match_num')}" == base]
    if len(matches) != 1:
        raise RepairConflict('source event is missing or ambiguous within the raw response')
    return matches[0], hashlib.sha256(body.encode()).hexdigest()


def _collisions(conn, rows, target_ids):
    old_ids = {r['id'] for r in rows}
    day = date.fromisoformat(rows[0]['match_date'])
    found = []
    for item in conn.execute("SELECT * FROM player_match_history WHERE history_status='ACTIVE' AND player_id IN (?,?)", target_ids):
        r = dict(item)
        if r['id'] in old_ids or {r['player_id'], r['opponent_id']} != set(target_ids):
            continue
        near = abs((date.fromisoformat(r['match_date'])-day).days) <= 1
        same_event = (r['tournament_external_id'] == rows[0]['tournament_external_id']
                      and r['match_date'][:4] == rows[0]['match_date'][:4])
        if near or same_event:
            found.append(r['id'])
    return sorted(found)


def propose_split(conn, history_ids, target_ids):
    """Build a deterministic, source-label-qualified *research* proposal.

    target_ids is winner then loser. Unknown tours/aliases are held rather
    than inferred. The proposal is not authority for any production mutation.
    """
    _memory_only(conn)
    if len(history_ids) != 2 or len(set(history_ids)) != 2 or len(target_ids) != 2:
        raise RepairConflict('exactly two distinct source perspectives required')
    rows = sorted((_row(conn, 'player_match_history', i) for i in history_ids), key=lambda r: -r['won'])
    a, b = rows
    shared = ('raw_response_id', 'source_provider', 'tour', 'match_date',
              'surface', 'tournament_external_id', 'tournament_level', 'round', 'format')
    if (a['source_provider'] not in PUBLIC or any(a[k] != b[k] for k in shared)
            or [a['won'], b['won']] != [1, 0]
            or a['history_status'] != 'ACTIVE' or b['history_status'] != 'ACTIVE'
            or a['player_id'] != b['opponent_id'] or b['player_id'] != a['opponent_id']
            or a['player_id'] == b['player_id']):
        raise RepairConflict('source perspectives are not an active reciprocal pair')
    base = _reference(a).removesuffix('-winner')
    if _reference(a) != base+'-winner' or _reference(b) != base+'-loser':
        raise RepairConflict('source role/reference disagrees')
    closure = [r['id'] for r in conn.execute(
        "SELECT * FROM player_match_history WHERE raw_response_id=? AND source_provider=? AND history_status='ACTIVE'",
        (a['raw_response_id'], a['source_provider']))
        if _reference(dict(r)) in {base+'-winner', base+'-loser'}]
    if set(closure) != {a['id'], b['id']}:
        raise RepairConflict('additional source perspectives require adjudication')
    if target_ids[0] == target_ids[1] or list(target_ids) == [a['player_id'], b['player_id']]:
        raise RepairConflict('self-pair or no-op target')
    source, body_hash = _source(conn, rows)
    targets = [_row(conn, 'players', i) for i in target_ids]
    for target, role in zip(targets, ('winner', 'loser')):
        if (not valid_player_identity(source.get(role+'_id'), source.get(role+'_name'))
                or target.get('canonical_player_id') is not None or target['tour'] != a['tour']
                or not _identity_agrees(target, source[role+'_name'], a['tour'])):
            raise RepairConflict('target is not an explicit-tour source-label-compatible leaf')
    if _collisions(conn, rows, target_ids):
        raise RepairConflict('target has a possible existing event; do not auto-deduplicate')
    payload = dict(policy=POLICY, rows=rows, targets=targets, raw_body_sha256=body_hash,
                   source_roles={role: {k: source.get(role+'_'+k) for k in ('id','name')}
                                 for role in ('winner','loser')},
                   qualification='SOURCE_LABEL_POLICY_ONLY_NOT_LIVE_AUTHORITY')
    return {**payload, 'proposal_id': _hash(payload)}


@contextmanager
def _atomic(conn):
    conn.execute('SAVEPOINT identity_split_research')
    try:
        yield
    except BaseException:
        conn.execute('ROLLBACK TO identity_split_research')
        conn.execute('RELEASE identity_split_research')
        raise
    else:
        conn.execute('RELEASE identity_split_research')


def _receipt(conn, proposal_id, kind):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='history_observations'").fetchone() is None:
        return None
    found = []
    for r in conn.execute('SELECT payload_json FROM history_observations WHERE observation_kind=?', (kind,)):
        payload = json.loads(r[0])
        if payload.get('proposal_id') == proposal_id:
            found.append(payload)
    if len(found) > 1:
        raise RepairConflict('duplicate repair receipts')
    return found[0] if found else None


def _check_images(conn, rows):
    if any(_row(conn, 'player_match_history', r['id']) != r for r in rows):
        raise RepairConflict('history before/after-image changed')


def _check_evidence(conn, proposal):
    if any(_row(conn, 'players', p['id']) != p for p in proposal['targets']):
        raise RepairConflict('target evidence changed')
    if _source(conn, proposal['rows'])[1] != proposal['raw_body_sha256']:
        raise RepairConflict('raw evidence changed')


def _write_receipt(conn, proposal_id, kind, payload, now):
    conn.execute('INSERT INTO history_observations(history_id,observation_kind,observed_at,raw_response_id,payload_json) VALUES (?,?,?,?,?)',
                 (payload['old'][0]['id'], kind, now, payload['old'][0]['raw_response_id'],
                  _json({**payload, 'proposal_id': proposal_id})))


def apply_split(conn, proposal):
    """Atomically exercise a proposal on memory SQLite; repeat is idempotent."""
    _memory_only(conn)
    payload = {k: v for k, v in proposal.items() if k != 'proposal_id'}
    if proposal.get('proposal_id') != _hash(payload):
        raise RepairConflict('proposal digest changed')
    pid = proposal['proposal_id']
    if _receipt(conn, pid, 'IDENTITY_SPLIT_ROLLED_BACK'):
        raise RepairConflict('rolled-back proposal cannot be reapplied')
    prior = _receipt(conn, pid, 'IDENTITY_SPLIT_APPLIED')
    if prior:
        _check_images(conn, prior['retired']+prior['new'])
        _check_evidence(conn, proposal)
        return prior
    with _atomic(conn):
        fresh = propose_split(conn, [r['id'] for r in proposal['rows']], [p['id'] for p in proposal['targets']])
        if fresh != proposal:
            raise RepairConflict('proposal inputs changed')
        ensure_history_schema(conn)
        now = utc_now()
        retired, inserted = [], []
        for old in proposal['rows']:
            _observe(conn, old, 'IDENTITY_SPLIT_BEFORE', now)
            conn.execute("UPDATE player_match_history SET history_status='SUPERSEDED',provider_match_id=? WHERE id=?",
                         (f"{old['provider_match_id']}::identity::{pid}::{old['id']}", old['id']))
            retired.append(_row(conn, 'player_match_history', old['id']))
        for index, old in enumerate(proposal['rows']):
            candidate = {**old, 'player_id': proposal['targets'][index]['id'],
                         'opponent_id': proposal['targets'][1-index]['id'],
                         'provider_match_id': _reference(old)}
            new_id = upsert_history_observation(conn, candidate, observed_at=now)
            conn.execute('UPDATE player_match_history SET supersedes_history_id=? WHERE id=?', (old['id'], new_id))
            new = _row(conn, 'player_match_history', new_id)
            _observe(conn, new, 'IDENTITY_SPLIT_LINKED', now)
            inserted.append(new)
        receipt = dict(old=proposal['rows'], retired=retired, new=inserted, observed_at=now,
                       proposal=proposal,
                       qualification=proposal['qualification'])
        _write_receipt(conn, pid, 'IDENTITY_SPLIT_APPLIED', receipt, now)
    return {**receipt, 'proposal_id': pid}


def rollback_split(conn, proposal_id):
    """Restore exact old rows; retain new generations and append-only evidence."""
    _memory_only(conn)
    rolled = _receipt(conn, proposal_id, 'IDENTITY_SPLIT_ROLLED_BACK')
    if rolled:
        _check_images(conn, rolled['restored']+rolled['new_retired'])
        _check_evidence(conn, rolled['proposal'])
        return rolled
    receipt = _receipt(conn, proposal_id, 'IDENTITY_SPLIT_APPLIED')
    if receipt is None:
        raise RepairConflict('no applied split receipt')
    with _atomic(conn):
        _check_images(conn, receipt['retired']+receipt['new'])
        _check_evidence(conn, receipt['proposal'])
        now = utc_now()
        for new in receipt['new']:
            _observe(conn, new, 'IDENTITY_SPLIT_ROLLBACK_BEFORE', now)
            conn.execute("UPDATE player_match_history SET history_status='SUPERSEDED',provider_match_id=? WHERE id=?",
                         (f"{new['provider_match_id']}::rollback::{proposal_id}::{new['id']}", new['id']))
        for old in receipt['old']:
            fields = [k for k in old if k != 'id']
            conn.execute('UPDATE player_match_history SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',
                         [old[k] for k in fields]+[old['id']])
            _observe(conn, old, 'IDENTITY_SPLIT_RESTORED', now)
        result = dict(old=receipt['old'], restored=receipt['old'], proposal=receipt['proposal'],
                      new_retired=[_row(conn, 'player_match_history', r['id']) for r in receipt['new']],
                      observed_at=now)
        _write_receipt(conn, proposal_id, 'IDENTITY_SPLIT_ROLLED_BACK', result, now)
    return {**result, 'proposal_id': proposal_id}
