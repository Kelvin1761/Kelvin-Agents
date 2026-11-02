"""Public, indexed, immutable revision files plus an append-only shadow registry.

No live ingestion hook or promotion exists. Inputs must be read-only frozen
SQLite files, including sealed public captures. Only public tables are copied; private
fixtures, quotes, predictions, ledgers and raw bodies are never copied.
"""
from __future__ import annotations

from contextlib import contextmanager, closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import quote

from tennis_wc.config import get_settings
from tennis_wc.database.db import readonly_history_scope
from tennis_wc.database.migrations import SCHEMA, _ensure_compat_columns
from tennis_wc.identity.player_identity import ensure_identity_schema
from tennis_wc.history import elo_history
from tennis_wc.modelling.elo_builder import read_elo_inputs
from tennis_wc.modelling.elo_replay import replay_elo
from tennis_wc.research_elo_generations import QUALIFICATION, _clock, _json, _model_hash, utc_now

REGISTRY_ID = 0x54475231
SNAPSHOT_ID = 0x54475331
PUBLIC_TABLES = ('players', 'player_match_history', 'provider_entities', 'player_aliases')
SOURCE_VIEWS = ('rankings_history', 'raw_api_responses', 'retained_payload_refs', 'retained_payload_blobs')


def _check_origin(info):
    source = Path(info['source_path'])
    if info.get('source_mode') == 'public_capture':
        if _source_identity(source)[:2] != info['source_identity']:
            raise ValueError('source file was replaced; raw IDs are not portable')
    else:
        if source.stat().st_mode & 0o222:
            raise ValueError('source is no longer frozen')
        if _source_identity(source) != info['source_identity']:
            raise ValueError('source file was replaced; raw IDs are not portable')


def _check_headers(conn):
    from tennis_wc.research_public_capture import RAW_HEADER_COLUMNS, _header_hash
    import time
    expires = time.monotonic() + 5
    conn.create_function('capture_header_hash', len(RAW_HEADER_COLUMNS), _header_hash)
    conn.set_progress_handler(lambda: int(time.monotonic() >= expires), 1000)
    try:
        header = ','.join('r.' + col for col in RAW_HEADER_COLUMNS)
        changed = conn.execute(f'''SELECT COUNT(*) FROM main.capture_raw_headers h
            LEFT JOIN original.raw_api_responses r ON r.id=h.raw_response_id
            WHERE (h.missing=1 AND r.id IS NOT NULL) OR
                (h.missing=0 AND (r.id IS NULL OR h.header_sha256!=capture_header_hash({header})))''').fetchone()[0]
        if time.monotonic() >= expires:
            raise TimeoutError('raw header verification deadline')
        if changed:
            raise ValueError('captured raw header changed')
    finally:
        conn.set_progress_handler(None, 0)


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _source_identity(path: Path):
    s = path.stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns]


def _readonly(path: Path, *, immutable=False):
    conn = sqlite3.connect('file:' + quote(str(path)) + '?mode=ro' +
                           ('&immutable=1' if immutable else ''), uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    return conn


def _new_file(path: Path):
    if path.resolve() == get_settings().sqlite_path:
        raise ValueError('configured tennis database cannot be a shadow artifact')
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)


def _native_schema(conn):
    conn.executescript(SCHEMA)
    _ensure_compat_columns(conn)
    elo_history.ensure_schema(conn)
    ensure_identity_schema(conn)
    # RankingReader's accessor checks main.sqlite_master, then reads these names.
    conn.execute('''CREATE TABLE IF NOT EXISTS retained_payload_refs (
        kind TEXT,row_id INTEGER,sha256 TEXT,archived_at TEXT,PRIMARY KEY(kind,row_id))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS retained_payload_blobs (
        sha256 TEXT PRIMARY KEY,byte_length INTEGER,gzip_sha256 TEXT,gzip_data BLOB)''')
    conn.commit()


def build_public_snapshot(destination: Path, *, source: Path, source_receipts: list[dict],
                          amend=None) -> dict:
    """amend is an explicit counterfactual experiment, never a live repair API."""
    destination, source = destination.resolve(), source.resolve()
    if source.stat().st_mode & 0o222:
        raise ValueError('source must be a frozen read-only file, not a live database')
    if source == destination or not source_receipts:
        raise ValueError('separate destination and source receipts required')
    source_identity = _source_identity(source)
    started = _clock(utc_now())
    for receipt in source_receipts:
        if len(receipt['sha256']) != 64 or any(c not in '0123456789abcdef' for c in receipt['sha256']):
            raise ValueError('invalid source receipt hash')
        if _clock(receipt['captured_at']) > started:
            raise ValueError('future source receipt')
    _new_file(destination)
    # A failed build remains an unsealed file. Registration rejects it.
    with closing(_readonly(source, immutable=True)) as original:
        from tennis_wc.research_public_capture import CAPTURE_ID
        captured = None
        if original.execute('PRAGMA application_id').fetchone()[0] == CAPTURE_ID:
            captured = json.loads(original.execute('SELECT metadata FROM public_capture_manifest').fetchone()[0])
            if captured['qualification'] != QUALIFICATION or _clock(captured['captured_at']) > started:
                raise ValueError('invalid public capture qualification or clock')
            _check_origin(dict(source_path=captured['source_path'], source_mode='public_capture',
                               source_identity=captured['source_origin']))
        public = {}
        source_tables = {r[0] for r in original.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing_optional = []
        for table in PUBLIC_TABLES:
            if table == 'player_aliases' and table not in source_tables:
                public[table] = []
                missing_optional.append(table)
                continue
            where = " WHERE entity_type='player'" if table == 'provider_entities' else ''
            public[table] = [dict(r) for r in original.execute(f'SELECT * FROM {table}{where} ORDER BY 1')]
    if amend is not None:
        amend(public)
    input_digest = hashlib.sha256()
    counts = {}
    conn = sqlite3.connect(destination)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA cache_size=-131072')
    conn.execute('PRAGMA temp_store=MEMORY')
    try:
        _native_schema(conn)
        for table in PUBLIC_TABLES:
            columns = {r['name'] for r in conn.execute(f'PRAGMA table_info({table})')}
            input_digest.update(table.encode())
            for row in public[table]:
                if set(row) - columns:
                    raise ValueError(f'unsupported input columns in {table}')
                input_digest.update((_json(row)+'\n').encode())
                keys = list(row)
                conn.execute(f'INSERT INTO {table} (' + ','.join(keys) + ') VALUES (' +
                             ','.join('?' for _ in keys) + ')', list(row.values()))
            counts[table] = len(public[table])
        extras = set()
        if captured is not None:
            # Pin rankings too. Old live caches are evidence only, never builder inputs.
            with closing(_readonly(source, immutable=True)) as original:
                for table, target in [('rankings_history','rankings_history'),
                                      ('capture_raw_headers','capture_raw_headers'),
                                      ('player_elo_history','generation_input_legacy_elo'),
                                      ('player_elo_history_v2','generation_input_shadow_elo')]:
                    if table not in source_tables:
                        continue
                    cols = [r['name'] for r in original.execute(f'PRAGMA table_info({table})')]
                    expected = ({'raw_response_id','header_sha256','missing'} if table == 'capture_raw_headers'
                                else {r['name'] for r in conn.execute(f'PRAGMA table_info({table})')})
                    if set(cols) != expected:
                        raise ValueError(f'unreviewed capture columns in {table}')
                    if target != 'rankings_history':
                        schema = ','.join('"'+c+'"' for c in cols)
                        conn.execute(f'CREATE TABLE {target} ({schema})')
                    placeholders = ','.join('?' for _ in cols)
                    names = ','.join('"'+c+'"' for c in cols)
                    input_digest.update(table.encode())
                    count = 0
                    for row in original.execute(f'SELECT * FROM {table} ORDER BY {names}'):
                        input_digest.update((_json(dict(row))+'\n').encode())
                        conn.execute(f'INSERT INTO {target} ({names}) VALUES ({placeholders})', tuple(row))
                        count += 1
                    counts[target] = count
                    extras.add(target)
        # Preserve original mutable cache fields separately for exact input provenance.
        conn.execute('''CREATE TABLE generation_input_player_elo AS
            SELECT id,overall_elo,surface_elo_json FROM players''')
        conn.execute('''CREATE TABLE generation_input_opponent_elo AS
            SELECT id,opponent_elo FROM player_match_history''')
        conn.commit()
        del public
        calculated = replay_elo(read_elo_inputs(conn))
        conn.execute('UPDATE players SET overall_elo=NULL,surface_elo_json=NULL')
        for pid, rating in calculated.overall.items():
            surfaces = calculated.surface_ratings[pid]
            conn.execute('UPDATE players SET overall_elo=?,surface_elo_json=? WHERE id=?',
                         (round(rating, 3), json.dumps({k: round(v, 3) for k, v in sorted(surfaces.items())},
                                                     sort_keys=True), pid))
        legacy, shadow = {}, {}
        for row in calculated.history_rows:
            legacy.setdefault(tuple(row[:3]), row)
        for row in calculated.post_rows:
            shadow[tuple(row[:3])] = row
        # Sorted unique keys avoid external-disk random writes; first/last policy is unchanged.
        elo_history.record(conn, [legacy[k] for k in sorted(legacy)])
        elo_history.replace_post_match(conn, [shadow[k] for k in sorted(shadow)])
        updates = {(p, ref): value for p, ref, value in calculated.opponent_updates}
        conn.execute('''CREATE TEMP TABLE opponent_updates (
            provider TEXT,ref TEXT,rating REAL,PRIMARY KEY(provider,ref)) WITHOUT ROWID''')
        conn.executemany('INSERT INTO opponent_updates VALUES (?,?,?)',
                         [(p, ref, updates[p, ref]) for p, ref in sorted(updates)])
        conn.execute('''UPDATE player_match_history SET opponent_elo=(
            SELECT rating FROM opponent_updates s WHERE s.provider=source_provider
                AND s.ref=provider_match_id) WHERE EXISTS (
            SELECT 1 FROM opponent_updates s WHERE s.provider=source_provider
                AND s.ref=provider_match_id)''')
        conn.execute('DROP TABLE opponent_updates')
        metadata = dict(qualification=QUALIFICATION, source_path=str(source),
                        source_identity=source_identity,
                        source_receipts=source_receipts, input_hash=input_digest.hexdigest(),
                        model_hash=_model_hash(), started_at=started, available_at=_clock(utc_now()),
                        public_counts=counts, missing_optional_tables=missing_optional,
                        counterfactual=amend is not None,
                        cold_cache_policy='first pre-match legacy; last post-match shadow; no mutable fallback')
        if captured is not None:
            metadata.update(source_mode='public_capture', capture_path=str(source),
                            capture_identity=source_identity, capture=captured,
                            source_path=captured['source_path'], source_identity=captured['source_origin'])
        if _source_identity(source) != source_identity:
            raise ValueError('frozen source changed during build')
        if metadata['available_at'] < started:
            raise ValueError('clock moved backwards')
        conn.execute('CREATE TABLE history_generation_manifest (metadata TEXT NOT NULL)')
        conn.execute('INSERT INTO history_generation_manifest VALUES (?)', (_json(metadata),))
        conn.execute(f'PRAGMA application_id={SNAPSHOT_ID}')
        conn.execute('PRAGMA user_version=1')
        # No copied private table or retained raw payload may have data.
        allowed = set(PUBLIC_TABLES) | {'player_elo_history','player_elo_history_v2',
            'generation_input_player_elo','generation_input_opponent_elo','history_generation_manifest'} | extras
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            if row[0] not in allowed and conn.execute(f'SELECT 1 FROM "{row[0]}" LIMIT 1').fetchone():
                raise ValueError('non-public table in snapshot')
        conn.commit()
    finally:
        conn.close()
    os.chmod(destination, 0o400)
    return dict(path=str(destination), sha256=file_sha(destination), **metadata)


class ShadowGenerationRegistry:
    def __init__(self, path: Path):
        self.path = path.resolve()
        with closing(_readonly(self.path)) as conn:
            if conn.execute('PRAGMA application_id').fetchone()[0] != REGISTRY_ID:
                raise ValueError('not a shadow generation registry')

    @classmethod
    def create(cls, path: Path):
        _new_file(path)
        with closing(sqlite3.connect(path)) as conn:
            conn.executescript('''CREATE TABLE revisions (
                id INTEGER PRIMARY KEY,path TEXT NOT NULL UNIQUE,sha256 TEXT NOT NULL,
                metadata TEXT NOT NULL,metadata_sha256 TEXT NOT NULL,registered_at TEXT NOT NULL);
                CREATE TABLE activations (
                id INTEGER PRIMARY KEY,revision_id INTEGER NOT NULL,observed_at TEXT NOT NULL,
                reason TEXT NOT NULL);''')
            for table in ('revisions','activations'):
                for action in ('UPDATE','DELETE'):
                    conn.execute(f'''CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action}
                        ON {table} BEGIN SELECT RAISE(ABORT,'registry is append-only'); END''')
            conn.execute(f'PRAGMA application_id={REGISTRY_ID}')
            conn.commit()
        return cls(path)

    @contextmanager
    def _write(self):
        conn = sqlite3.connect('file:'+quote(str(self.path))+'?mode=rw', uri=True)
        try:
            if conn.execute('PRAGMA application_id').fetchone()[0] != REGISTRY_ID:
                raise ValueError('registry file changed or was replaced')
            with conn:
                yield conn
        finally:
            conn.close()

    def register(self, snapshot: Path) -> int:
        snapshot = snapshot.resolve()
        if snapshot.stat().st_mode & 0o222:
            raise ValueError('revision file must be sealed read-only')
        with closing(_readonly(snapshot, immutable=True)) as conn:
            if conn.execute('PRAGMA application_id').fetchone()[0] != SNAPSHOT_ID:
                raise ValueError('unsealed or foreign revision')
            rows = conn.execute('SELECT metadata FROM history_generation_manifest').fetchall()
            if len(rows) != 1:
                raise ValueError('invalid revision metadata')
            metadata = rows[0][0]
        info = json.loads(metadata)
        now = _clock(utc_now())
        if info['qualification'] != QUALIFICATION or _clock(info['available_at']) > now:
            raise ValueError('invalid revision qualification or clock')
        digest = file_sha(snapshot)
        with self._write() as conn:
            existing = conn.execute('SELECT id,sha256 FROM revisions WHERE path=?', (str(snapshot),)).fetchone()
            if existing:
                if existing[1] != digest:
                    raise ValueError('registered revision changed')
                return existing[0]
            return conn.execute('INSERT INTO revisions(path,sha256,metadata,metadata_sha256,registered_at) VALUES (?,?,?,?,?)',
                                (str(snapshot), digest, metadata, hashlib.sha256(metadata.encode()).hexdigest(), now)).lastrowid

    def _revision(self, conn, revision_id):
        row = conn.execute('SELECT * FROM revisions WHERE id=?', (revision_id,)).fetchone()
        if row is None:
            raise ValueError('unknown revision')
        row = dict(row)
        if hashlib.sha256(row['metadata'].encode()).hexdigest() != row['metadata_sha256']:
            raise ValueError('registry metadata digest mismatch')
        if Path(row['path']).stat().st_mode & 0o222:
            raise ValueError('registered revision is no longer sealed')
        if file_sha(Path(row['path'])) != row['sha256']:
            raise ValueError('revision file digest mismatch')
        return row, json.loads(row['metadata'])

    def activate(self, revision_id: int, *, reason: str):
        with self._write() as conn:
            conn.row_factory = sqlite3.Row
            row, info = self._revision(conn, revision_id)
            now = _clock(utc_now())
            last = conn.execute('SELECT MAX(observed_at) FROM activations').fetchone()[0]
            if not reason.strip() or now < max(row['registered_at'], info['available_at'], last or ''):
                raise ValueError('activation clock or reason invalid')
            conn.execute('INSERT INTO activations(revision_id,observed_at,reason) VALUES (?,?,?)',
                         (revision_id, now, reason))

    @contextmanager
    def native_scope(self, *, knowledge_at: str):
        stamp = _clock(knowledge_at)
        if stamp > _clock(utc_now()):
            raise ValueError('cannot assert future knowledge')
        with closing(_readonly(self.path)) as registry:
            chosen = registry.execute('''SELECT revision_id,observed_at FROM activations
                WHERE observed_at<=? ORDER BY observed_at DESC,id DESC LIMIT 1''', (stamp,)).fetchone()
            if chosen is None:
                raise ValueError('no history generation available at decision time')
            row, info = self._revision(registry, chosen[0])
            if max(row['registered_at'], info['available_at']) > chosen[1]:
                raise ValueError('activation precedes durable availability')
        source = Path(info['source_path'])
        _check_origin(info)
        conn = sqlite3.connect('file:' + quote(row['path']) + '?mode=ro&immutable=1', uri=True)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('ATTACH DATABASE ? AS original', ('file:'+quote(str(source))+'?mode=ro',))
            names = {r[0] for r in conn.execute("SELECT name FROM original.sqlite_master WHERE type='table'")}
            for table in SOURCE_VIEWS:
                if table == 'rankings_history' and info.get('source_mode') == 'public_capture':
                    continue
                if table in names:
                    conn.execute(f'CREATE TEMP VIEW {table} AS SELECT * FROM original.{table}')
            conn.commit()
            conn.execute('PRAGMA query_only=ON')
            if info.get('source_mode') == 'public_capture':
                _check_headers(conn)
            prov = dict(source_provider='unqualified_history_generation',
                        source_endpoint=f'shadow-generation:{chosen[0]}',
                        source_timestamp=chosen[1], raw_response_id=None,
                        warnings=['unqualified_history_generation'], qualification=QUALIFICATION,
                        revision_id=chosen[0], input_hash=info['input_hash'],
                        artifact_sha256=row['sha256'], available_at=info['available_at'],
                        knowledge_at=stamp)
            with readonly_history_scope(conn, source_path=source, provenance=prov):
                yield prov
                if info.get('source_mode') == 'public_capture':
                    _check_headers(conn)
                _check_origin(info)
        finally:
            conn.close()
