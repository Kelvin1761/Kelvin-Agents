"""Bounded read-only capture of public model inputs from a mutable database.

The live transaction copies only allowlisted tables into memory. Disk I/O and
hashing happen after detaching the source. This is an unqualified research
artifact, not a wire receipt, prediction bundle, or permission to repair data.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from urllib.parse import quote
from uuid import uuid4

from tennis_wc.research_elo_generations import QUALIFICATION, _clock, _json, utc_now
from tennis_wc.research_indexed_generations import (
    PUBLIC_TABLES, _native_schema, _new_file, file_sha,
)

CAPTURE_ID = 0x54474331
INPUT_TABLES = (*PUBLIC_TABLES, 'rankings_history', 'player_elo_history', 'player_elo_history_v2')
OPTIONAL_TABLES = {'player_aliases', 'player_elo_history', 'player_elo_history_v2'}
RAW_HEADER_COLUMNS = ('id', 'provider_name', 'endpoint', 'fetched_at', 'created_at')


def _origin(path: Path) -> list[int]:
    stat = path.stat()
    return [stat.st_dev, stat.st_ino]


def _header_hash(*values) -> str:
    return hashlib.sha256(_json(list(values)).encode()).hexdigest()


def _check_destination_volume(path: Path) -> None:
    if len(path.parts) > 2 and path.parts[1] == 'Volumes':
        if not Path('/Volumes', path.parts[2]).is_mount():
            raise ValueError('external destination volume is not mounted')


def _schema_columns() -> dict[str, list[str]]:
    # Derive the allowlist from our code, never from the attached live schema.
    with closing(sqlite3.connect(':memory:')) as conn:
        conn.row_factory = sqlite3.Row
        _native_schema(conn)
        return {table: [r['name'] for r in conn.execute(f'PRAGMA table_info({table})')]
                for table in INPUT_TABLES}


def capture_public_inputs(destination: Path, *, source: Path, deadline_seconds: float = 5.0) -> dict:
    """One consistent public SQL snapshot; cooperative deadline never exceeds 5s.

    The deadline covers acquiring the source lock through commit, not writing
    the detached public memory database. An interrupted capture produces no
    destination. Raw body bytes, fixtures, odds and ledgers are never selected.
    """
    if not 0 < deadline_seconds <= 5:
        raise ValueError('source transaction deadline must be positive and at most five seconds')
    source, destination = source.resolve(), destination.resolve()
    _check_destination_volume(destination)
    if source == destination or destination.exists():
        raise ValueError('capture requires a new separate destination')
    columns = _schema_columns()
    origin = _origin(source)
    conn = sqlite3.connect(':memory:', uri=True)
    conn.create_function('capture_header_hash', len(RAW_HEADER_COLUMNS), _header_hash)
    conn.execute('PRAGMA temp_store=MEMORY')
    conn.execute('PRAGMA busy_timeout=100')
    started = _clock(utc_now())
    tick = time.monotonic()
    expires = tick + deadline_seconds
    read_done = False

    def check_deadline():
        if time.monotonic() >= expires:
            raise TimeoutError('public source capture exceeded transaction deadline')

    conn.set_progress_handler(lambda: int(time.monotonic() >= expires), 1000)
    try:
        conn.execute('ATTACH DATABASE ? AS live', ('file:' + quote(str(source)) + '?mode=ro',))
        conn.execute('BEGIN')
        available = {r[0] for r in conn.execute("SELECT name FROM live.sqlite_master WHERE type='table'")}
        counts, missing = {}, []
        for table in INPUT_TABLES:
            check_deadline()
            if table not in available:
                if table not in OPTIONAL_TABLES:
                    raise ValueError(f'missing required public table: {table}')
                missing.append(table)
                continue
            observed = [r[1] for r in conn.execute(f'PRAGMA live.table_info({table})')]
            if set(observed) != set(columns[table]):
                raise ValueError(f'unreviewed public columns in {table}')
            selection = ','.join('"' + col + '"' for col in observed)
            where = " WHERE entity_type='player'" if table == 'provider_entities' else ''
            conn.execute(f'CREATE TABLE main.{table} AS SELECT {selection} FROM live.{table}{where}')
            counts[table] = conn.execute(f'SELECT COUNT(*) FROM main.{table}').fetchone()[0]
        if 'raw_api_responses' not in available:
            raise ValueError('missing raw header source')
        conn.execute('''CREATE TABLE capture_raw_headers (
            raw_response_id INTEGER PRIMARY KEY,header_sha256 TEXT,missing INTEGER NOT NULL)''')
        header = ','.join('r.' + col for col in RAW_HEADER_COLUMNS)
        conn.execute(f'''INSERT INTO capture_raw_headers
            SELECT ref.id,CASE WHEN r.id IS NULL THEN NULL ELSE capture_header_hash({header}) END,
                CASE WHEN r.id IS NULL THEN 1 ELSE 0 END
            FROM (SELECT raw_response_id AS id FROM main.players
                  UNION SELECT raw_response_id FROM main.player_match_history
                  UNION SELECT raw_response_id FROM main.rankings_history) ref
            LEFT JOIN live.raw_api_responses r ON r.id=ref.id WHERE ref.id IS NOT NULL''')
        counts['capture_raw_headers'] = conn.execute('SELECT COUNT(*) FROM capture_raw_headers').fetchone()[0]
        missing_headers = conn.execute('SELECT COUNT(*) FROM capture_raw_headers WHERE missing=1').fetchone()[0]
        check_deadline()
        conn.commit()
        elapsed = time.monotonic() - tick
        check_deadline()
        conn.set_progress_handler(None, 0)
        conn.execute('DETACH DATABASE live')
        read_done = True
        if _origin(source) != origin:
            raise ValueError('source file replaced during capture')
        captured_at = _clock(utc_now())
        if captured_at < started:
            raise ValueError('capture clock moved backwards')
        metadata = dict(qualification=QUALIFICATION, source_path=str(source), source_origin=origin,
                        started_at=started, captured_at=captured_at, source_read_seconds=elapsed,
                        deadline_seconds=deadline_seconds, public_counts=counts,
                        missing_optional_tables=missing, missing_raw_headers=missing_headers,
                        raw_contract='header hashes only; original bodies not captured or verified')
        conn.execute('CREATE TABLE public_capture_manifest(metadata TEXT NOT NULL)')
        conn.execute('INSERT INTO public_capture_manifest VALUES (?)', (_json(metadata),))
        conn.execute(f'PRAGMA application_id={CAPTURE_ID}')
        conn.execute('PRAGMA user_version=1')
        conn.commit()
        assert [r[1] for r in conn.execute('PRAGMA database_list')] == ['main']
        _new_file(destination)
        try:
            with closing(sqlite3.connect(destination)) as output:
                conn.backup(output)  # Only the detached, public memory main database.
            os.chmod(destination, 0o400)
            digest = file_sha(destination)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        return dict(path=str(destination), sha256=digest, available_at=_clock(utc_now()), **metadata)
    except sqlite3.OperationalError as exc:
        if not read_done and time.monotonic() >= expires:
            raise TimeoutError('public source capture exceeded transaction deadline') from exc
        raise
    finally:
        conn.set_progress_handler(None, 0)
        if conn.in_transaction:
            conn.rollback()
        conn.close()


def prepare_public_shadow(directory: Path, *, source: Path) -> dict:
    """Opt-in pre-feature producer. Never activates a production generation."""
    from tennis_wc.research_indexed_generations import build_public_snapshot, ShadowGenerationRegistry
    directory = directory.resolve()
    _check_destination_volume(directory)
    if not directory.is_dir():
        raise ValueError('shadow parent directory must already exist')
    root = directory / ('public-' + utc_now().replace(':','-') + '-' + uuid4().hex[:8])
    root.mkdir(mode=0o700)
    receipt = capture_public_inputs(root/'public.sqlite', source=source)
    revision = build_public_snapshot(root/'revision.sqlite', source=root/'public.sqlite',
        source_receipts=[dict(sha256=receipt['sha256'],captured_at=receipt['available_at'])])
    registry = ShadowGenerationRegistry.create(root/'registry.sqlite')
    revision_id = registry.register(root/'revision.sqlite')
    registry.activate(revision_id, reason='pre-feature unqualified public input capture')
    result = dict(qualification=QUALIFICATION, capture=receipt, revision=revision,
                  registry_path=str(registry.path), revision_id=revision_id,
                  prepared_at=_clock(utc_now()), production_model_changed=False)
    with (root/'receipt.json').open('x') as stream:
        stream.write(_json(result)+'\n')
    os.chmod(root/'receipt.json', 0o400)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(capture_public_inputs(args.destination, source=args.source), ensure_ascii=False))


if __name__ == '__main__':
    main()
