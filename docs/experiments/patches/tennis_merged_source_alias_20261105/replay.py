"""Read live identity metadata with a deadline; write only to an in-memory projection."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sqlite3
import subprocess
import time
import types
from collections import Counter
from pathlib import Path

from tennis_wc.ingestion import entity_mapping as candidate

BASELINE = '64aacf58f96daa7ffb58e5c0ff2dc10925a516d2'
ARCHIVE = Path('/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101')


def digest(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()


def frozen_projection(connection_factory, actors):
    """Read only identity columns in bounded pages; keep the fixed DB untouched."""
    def read(sql, params=()):
        source, deadline = connection_factory()
        try:
            rows = source.execute(sql, params).fetchall()
            if time.monotonic() > deadline:
                raise TimeoutError("archived identity page deadline")
            assert source.total_changes == 0
            return rows
        finally:
            source.close()

    def chunks(values):
        values = list(values)
        for offset in range(0, len(values), 400):
            yield values[offset:offset+400]

    ids = set()
    for keys in chunks(actors):
        marks = ','.join('?' for _ in keys)
        ids.update(r[0] for r in read(f"SELECT internal_entity_id FROM provider_entities WHERE provider_name='composite' AND entity_type='player' AND provider_entity_id IN ({marks})", keys))
    players = {}
    for names in chunks({name for tour, name in actors.values()}):
        marks = ','.join('lower(?)' for _ in names)
        for row in read(f'SELECT * FROM players WHERE lower(trim(name)) IN ({marks})', names):
            players[row['id']] = dict(row)
    ids.update(players)
    missing = ids - players.keys()
    for _ in range(17):
        found = {}
        for batch in chunks(missing):
            marks = ','.join('?' for _ in batch)
            for row in read(f'SELECT * FROM players WHERE id IN ({marks})', batch):
                found[row['id']] = dict(row)
        players.update(found)
        parents = {r['canonical_player_id'] for r in players.values() if r['canonical_player_id'] is not None}
        new_ids = parents - ids
        ids.update(parents)
        if not new_ids:
            break
        missing = new_ids
    mem = sqlite3.connect(':memory:')
    mem.row_factory = sqlite3.Row
    for table in ['players', 'provider_entities', 'player_merge_log', 'player_aliases']:
        mem.execute(read("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,))[0][0])
        if table == 'players':
            rows = list(players.values())
            fields = ','.join(rows[0])
            marks = ','.join('?' for _ in rows[0])
            mem.executemany(f'INSERT INTO players ({fields}) VALUES ({marks})', (tuple(r.values()) for r in rows))
            continue
        column = {'provider_entities': 'internal_entity_id', 'player_merge_log': 'duplicate_id', 'player_aliases': 'canonical_player_id'}[table]
        for batch in chunks(ids):
            marks = ','.join('?' for _ in batch)
            rows = read(f'SELECT * FROM {table} WHERE {column} IN ({marks})', batch)
            if rows:
                fields = ','.join(rows[0].keys())
                values = ','.join('?' for _ in rows[0])
                mem.executemany(f'INSERT INTO {table} ({fields}) VALUES ({values})', (tuple(r) for r in rows))
    columns = {r['name'] for r in read('PRAGMA table_info(player_match_history)')}
    fields = 'id,player_id,opponent_id' + (',history_status' if 'history_status' in columns else '')
    mem.execute(f'CREATE TABLE player_match_history ({fields})')
    last_id = -1
    while True:
        rows = read(f'SELECT {fields} FROM player_match_history WHERE id>? ORDER BY id LIMIT 1000', (last_id,))
        if not rows:
            break
        values = ','.join('?' for _ in rows[0])
        mem.executemany(f'INSERT INTO player_match_history VALUES ({values})', (tuple(r) for r in rows if r['player_id'] in ids))
        last_id = rows[-1]['id']
    mem.execute('CREATE INDEX history_player ON player_match_history(player_id)')
    mem.commit()
    mem.execute('PRAGMA query_only=1')
    return mem


def main():
    args = argparse.ArgumentParser()
    args.add_argument('--sources', type=Path, default=ARCHIVE/'espn-draw-ingestion-replay-20261105')
    args.add_argument('--db', type=Path, default=None)
    args.add_argument('--immutable', action='store_true')
    options = args.parse_args()
    db = options.db or Path((Path.home()/'.wongchoi_tennis_db').read_text().strip()).expanduser()
    database_sha256 = None
    if options.immutable:
        frozen = ARCHIVE.parent/'ranking-date-contract/source.sqlite'
        assert db.resolve() == frozen.resolve(), 'immutable mode is restricted to the fixed archived DB'
        hasher = hashlib.sha256()
        with db.open('rb') as handle:
            for block in iter(lambda: handle.read(1024*1024), b''):
                hasher.update(block)
        database_sha256 = hasher.hexdigest()
        assert database_sha256 == 'fb5638c6ad30476ea0a4d5aceb5462f20c271d6c9ee0ebc0f8a00b273f90f9fe'
    code = subprocess.run(['git', 'show', f'{BASELINE}:tennis-wong-choi/src/tennis_wc/ingestion/entity_mapping.py'],
                          capture_output=True, text=True, check=True).stdout
    baseline = types.ModuleType('baseline_mapping')
    exec(compile(code, 'baseline_entity_mapping', 'exec'), baseline.__dict__)
    actors, fixtures, source_hashes = {}, {}, {}
    for path in sorted(options.sources.glob('tennis-espn-*-20260131.json')):
        payload = path.read_bytes()
        source_hashes[path.name] = hashlib.sha256(payload).hexdigest()
        for event in json.loads(payload)['events']:
            if event.get('id') != '154-2026':
                continue
            for group in event['groupings']:
                for match in group['competitions']:
                    tour = {'mens-singles': 'ATP', 'womens-singles': 'WTA'}.get(match.get('type', {}).get('slug'))
                    if tour is None:
                        continue
                    sides = []
                    for side in match['competitors']:
                        name = (side.get('athlete') or {}).get('displayName')
                        if not name:
                            continue
                        key = str(side['id'])
                        assert key not in actors or actors[key] == (tour, name)
                        actors[key] = (tour, name)
                        sides.append(key)
                    if len(sides) == 2:
                        fixtures[match['id']] = sides
    assert source_hashes == {
        'tennis-espn-atp-20260131.json': 'c9c278a5ec8b1d21d02109cb93ecb39418d2b84234586db4d5d037d79fe0a219',
        'tennis-espn-wta-20260131.json': '13f3c956ea9918d203b47eb44415aa32fe2b8dfade86a31e0d93754b3932e8a7',
    }
    assert len(fixtures) == 478
    archive_stat = db.stat() if options.immutable else None

    def metadata_connection():
        if archive_stat is not None:
            current = db.stat()
            assert (current.st_size, current.st_mtime_ns, current.st_ino) == (archive_stat.st_size, archive_stat.st_mtime_ns, archive_stat.st_ino)
        connection = sqlite3.connect(db.resolve().as_uri()+'?mode=ro'+('&immutable=1' if options.immutable else ''), uri=True, timeout=.1)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=1')
        connection.execute('BEGIN')
        cutoff = time.monotonic()+5
        connection.set_progress_handler(lambda: int(time.monotonic() > cutoff), 10000)
        return connection, cutoff

    if options.immutable:
        conn = frozen_projection(metadata_connection, actors)
        deadline = time.monotonic()+5
    else:
        conn, deadline = metadata_connection()
    initial_changes = conn.total_changes
    results, rejected = {}, {}
    try:
        for label, module in [('baseline', baseline), ('candidate', candidate)]:
            results[label], rejected[label] = {}, set()
            for key, (tour, name) in actors.items():
                if time.monotonic() > deadline:
                    raise TimeoutError('identity metadata read deadline')
                try:
                    results[label][key] = module.existing_player_id(conn, 'composite', key, name, tour)
                except module.PlayerIdentityConflict:
                    rejected[label].add(key)
        recovered = rejected['baseline'] - rejected['candidate']
        expected = (13, 9, 4) if options.immutable else (12, 9, 3)
        assert (len(rejected['baseline']), len(recovered), len(rejected['candidate'])) == expected
        assert not (rejected['candidate'] - rejected['baseline'])
        for key, value in results['baseline'].items():
            assert results['candidate'][key] == value
        ids = set()
        for key in recovered:
            ids.add(results['candidate'][key])
            ids.add(conn.execute("SELECT internal_entity_id FROM provider_entities WHERE provider_name='composite' AND entity_type='player' AND provider_entity_id=?", (key,)).fetchone()[0])
            ids.update(r[0] for r in conn.execute('SELECT id FROM players WHERE lower(trim(name))=lower(?)', (actors[key][1],)))
        for _ in range(16):
            slots = ','.join('?' for _ in ids)
            parents = {r[0] for r in conn.execute(f'SELECT canonical_player_id FROM players WHERE id IN ({slots}) AND canonical_player_id IS NOT NULL', tuple(ids))}
            if parents <= ids:
                break
            ids.update(parents)
        slots = ','.join('?' for _ in ids)
        mem = sqlite3.connect(':memory:')
        mem.row_factory = sqlite3.Row
        for table, where, params in [
            ('players', f'id IN ({slots})', tuple(ids)),
            ('provider_entities', f"entity_type='player' AND internal_entity_id IN ({slots})", tuple(ids)),
            ('player_merge_log', f'duplicate_id IN ({slots})', tuple(ids)),
            ('player_aliases', f'canonical_player_id IN ({slots})', tuple(ids)),
        ]:
            if time.monotonic() > deadline:
                raise TimeoutError('identity metadata projection deadline')
            schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0]
            mem.execute(schema)
            cursor = conn.execute(f'SELECT * FROM {table} WHERE {where}', params)
            columns = ','.join(x[0] for x in cursor.description)
            values = ','.join('?' for _ in cursor.description)
            mem.executemany(f'INSERT INTO {table} ({columns}) VALUES ({values})', (tuple(row) for row in cursor))
        mem.execute('CREATE TABLE player_match_history(id,player_id,opponent_id,history_status)')
        mem.executemany('INSERT INTO player_match_history VALUES (?,?,?,?)',
                        (tuple(r) for r in conn.execute(f'SELECT id,player_id,opponent_id,history_status FROM player_match_history WHERE player_id IN ({slots})', tuple(ids))))
        if time.monotonic() > deadline:
            raise TimeoutError('identity metadata read deadline')
        assert conn.total_changes == initial_changes
    finally:
        conn.close()

    def projection(table):
        return [dict(r) for r in mem.execute(f'SELECT * FROM {table} ORDER BY rowid')]

    tables = ['players', 'provider_entities', 'player_match_history', 'player_merge_log', 'player_aliases']
    mem.commit()
    before = {t: projection(t) for t in tables}
    old_bindings = {r['provider_entity_id']: r['internal_entity_id'] for r in before['provider_entities'] if r['provider_name'] == 'composite'}
    plan_sha256 = hashlib.sha256(json.dumps(sorted((k, (old_bindings[k], results['candidate'][k])) for k in recovered), separators=(',', ':')).encode()).hexdigest()
    assert plan_sha256 == '770911d8a98c27521b136059f4fdaa28216005a3ccc3a76cd68f8379d0122c1d'
    if options.immutable:
        for key in sorted(rejected['baseline']):
            direct, cutoff = metadata_connection()
            try:
                tour, name = actors[key]
                try:
                    baseline.existing_player_id(direct, 'composite', key, name, tour)
                except baseline.PlayerIdentityConflict:
                    pass
                else:
                    raise AssertionError('archived projection invented a baseline conflict')
                try:
                    actual = candidate.existing_player_id(direct, 'composite', key, name, tour)
                except candidate.PlayerIdentityConflict:
                    assert key in rejected['candidate']
                else:
                    assert actual == results['candidate'][key]
                assert time.monotonic() <= cutoff and direct.total_changes == 0
            finally:
                direct.close()
    for key in sorted(recovered):
        tour, name = actors[key]
        assert candidate.existing_player_id(mem, 'composite', key, name, tour) == results['candidate'][key]
        assert {t: projection(t) for t in tables} == before
    for key in sorted(recovered):
        tour, name = actors[key]
        assert candidate.get_or_create_player('composite', key, name, tour, 0, connection=mem) == results['candidate'][key]
    changed = Counter()
    old_players = {r['id']: r for r in before['players']}
    target_ids = {results['candidate'][k] for k in recovered}
    for row in projection('players'):
        old = old_players[row['id']]
        diff = {k for k in row if row[k] != old[k]}
        assert not diff or row['id'] in target_ids
        assert diff <= {'name', 'tour', 'raw_response_id', 'updated_at'}
        changed['target_player_metadata_updates'] += bool(diff)
    for table in ['player_match_history', 'player_merge_log', 'player_aliases']:
        assert projection(table) == before[table]
    for old, new in zip(before['provider_entities'], projection('provider_entities')):
        if old != new:
            key = new['provider_entity_id']
            assert key in recovered and new['internal_entity_id'] == results['candidate'][key]
            changed['alias_rebindings'] += 1
    assert changed['alias_rebindings'] == 9
    mem.rollback()
    assert {t: projection(t) for t in tables} == before
    mem.close()
    card = Path.home()/'wongchoi-scheduler/2026-11-05 Tennis Analysis/_prediction_snapshots/20261104T222916.029764+0000-05bfd5e3152f/Tennis_Research_Diagnostics_2026-11-05.json.gz'
    card_bytes = card.read_bytes()
    assert hashlib.sha256(card_bytes).hexdigest() == 'c52e10f46e2d0be6884b07aedf2f3a4178ea24168cdc062d581e4f0e2839a69d'
    observations = json.loads(gzip.decompress(card_bytes))['observations']
    observed_ids = {int(o['snapshot'][p]['id']['value']) for o in observations for p in ['player_a', 'player_b']}
    recovered_ids = target_ids | {old_bindings[k] for k in recovered}
    observed_names = {candidate.normalise_player_name(o['snapshot'][p]['name']) for o in observations for p in ['player_a', 'player_b']}
    result = dict(baseline_commit=BASELINE, source_sha256=source_hashes,
                  database_kind='archived_immutable' if options.immutable else 'live_readonly',
                  database_sha256=database_sha256, identity_projection_sha256=digest(before),
                  immutable_metadata_projection=bool(options.immutable),
                  alias_plan_sha256=plan_sha256,
                  source_actors=len(actors), source_fixtures=len(fixtures),
                  baseline_rejected_actors=len(rejected['baseline']), candidate_rejected_actors=len(rejected['candidate']),
                  recovered_actors=len(recovered), unchanged_nonconflicting_lookups=len(results['baseline']),
                  previously_resolved_actors=sum(v is not None for v in results['baseline'].values()),
                  baseline_blocked_fixtures=sum(bool(rejected['baseline'].intersection(keys)) for keys in fixtures.values()),
                  candidate_blocked_fixtures=sum(bool(rejected['candidate'].intersection(keys)) for keys in fixtures.values()),
                  readonly_resolution_no_mutations=True, isolated_write_changes=dict(changed),
                  all_history_and_receipts_unchanged=True, transaction_rollback_exact=True,
                  current_card_recovered_name_overlap=sum(candidate.normalise_player_name(actors[k][1]) in observed_names for k in recovered),
                  current_card_recovered_id_overlap=len(observed_ids & recovered_ids),
                  direct_archived_conflicts_verified=len(rejected['baseline']) if options.immutable else None,
                  production_updates=0)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
