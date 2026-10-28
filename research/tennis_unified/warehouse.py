"""Create-only consistent SQLite captures and reproducible source inventory.

Run from the repository root with python -m research.tennis_unified.warehouse.
This module never ingests, reprices, settles, or changes a production database.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess


ARCHIVE_MOUNT = Path('/Volumes/Kelvin Hardisk 1')
ARCHIVE_SCRATCH = ARCHIVE_MOUNT / 'WongChoi-Archive/scratch'
MIN_FREE_BYTES = 10 * 1024**3


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def write_new(path: Path, payload: dict) -> None:
    with path.open('x', encoding='utf-8') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    return conn


def table_counts(conn: sqlite3.Connection) -> dict:
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )]
    return {name: conn.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
            for name in names}


def capture_database(source: Path, destination: Path) -> dict:
    """Backup one read transaction, retaining every table/row/index and WAL data."""
    if source.resolve() == destination.resolve():
        raise ValueError('source and destination must differ')
    # Reserve exclusively; never connect to an existing output or clobber it.
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    started = datetime.now(timezone.utc).isoformat()
    try:
        with closing(readonly(source)) as original:
            original.execute('BEGIN')
            before = table_counts(original)  # Pins the SQLite snapshot.
            with closing(sqlite3.connect(destination)) as captured:
                original.backup(captured)
                if captured.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('snapshot integrity check failed')
                after = table_counts(captured)
                if before != after:
                    raise ValueError('snapshot row count mismatch')
    except BaseException:
        # A failed partial capture is never usable evidence.
        destination.unlink(missing_ok=True)
        raise
    destination.chmod(0o400)
    return {'source': str(source.resolve()), 'path': str(destination.resolve()),
            'started_at': started, 'completed_at': datetime.now(timezone.utc).isoformat(),
            'method': 'SQLite backup of one pinned read transaction; all tables and rows',
            'counts': after, 'bytes': destination.stat().st_size, 'sha256': digest(destination)}


def storage_guard(output: Path) -> None:
    if not os.path.ismount(ARCHIVE_MOUNT):
        raise ValueError('required external archive volume is not mounted')
    resolved = output.resolve()
    if ARCHIVE_SCRATCH.resolve() not in resolved.parents:
        raise ValueError('research output must be below external archive scratch')
    if shutil.disk_usage('/System/Volumes/Data').free < MIN_FREE_BYTES:
        raise ValueError('internal disk has less than 10GiB free')
    if shutil.disk_usage(ARCHIVE_MOUNT).free < MIN_FREE_BYTES:
        raise ValueError('external archive has less than 10GiB free')


def capture(source: Path, output: Path, repo: Path) -> dict:
    storage_guard(output)
    if not source.is_file():
        raise ValueError('source database missing')
    output.mkdir(parents=False, exist_ok=False)
    snapshot = capture_database(source, output / 'warehouse.db')
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()
    ruler = repo / '.agents/skills/shared_wong_choi/resources/evaluation_rulers/tennis-v1.json'
    protocol = repo / 'docs/plans/tennis-research-protocol-20261028.md'
    payload = {'schema': 'tennis-unified-run/v1', 'captured_at': datetime.now(timezone.utc).isoformat(),
               'repo': str(repo.resolve()), 'code_commit': git('rev-parse', 'HEAD'),
               'branch': git('branch', '--show-current'),
               'working_tree_status': git('status', '--porcelain'),
               'implementation_sha256': digest(Path(__file__)),
               'ruler_sha256': digest(ruler), 'protocol_sha256': digest(protocol),
               'snapshot': snapshot, 'split_status': 'SEEN_DEV',
               'promotion_eligible': False, 'live_database_written': False}
    write_new(output / 'run_manifest.json', payload)
    return payload


def inventory(database: Path) -> dict:
    with closing(readonly(database)) as conn:
        conn.execute('BEGIN')
        result = {'counts': table_counts(conn)}
        result['history_sources'] = [dict(r) for r in conn.execute(
            'SELECT source_provider,tour,history_status,COUNT(*) n,MIN(match_date) earliest,'
            'MAX(match_date) latest,SUM(surface IS NOT NULL) surface_n,'
            'SUM(hold_rate IS NOT NULL) hold_n,SUM(canonical_event_key IS NOT NULL) canonical_key_n '
            'FROM player_match_history GROUP BY source_provider,tour,history_status')]
        result['quote_sources'] = [dict(r) for r in conn.execute(
            'SELECT bookmaker,source_provider,market,COUNT(*) n,MIN(created_at) earliest,'
            'MAX(created_at) latest FROM odds_snapshots GROUP BY bookmaker,source_provider,market')]
        result['source_responses'] = [dict(r) for r in conn.execute(
            'SELECT provider_name,entity_type,COUNT(*) n,MIN(fetched_at) earliest,'
            'MAX(fetched_at) latest FROM raw_api_responses GROUP BY provider_name,entity_type')]
        result['prediction_versions'] = [dict(r) for r in conn.execute(
            'SELECT feature_set_version,COUNT(*) n,MIN(created_at) earliest,MAX(created_at) latest '
            'FROM predictions GROUP BY feature_set_version')]
    return {'database': str(database.resolve()), 'dataset_sha256': digest(database), **result,
            'qualification': 'Inventory only; dates/counts do not prove point-in-time or promotion.'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    snap = commands.add_parser('capture')
    snap.add_argument('--source', type=Path, required=True)
    snap.add_argument('--output', type=Path, required=True)
    snap.add_argument('--repo', type=Path, default=Path.cwd())
    inv = commands.add_parser('inventory')
    inv.add_argument('--db', type=Path, required=True)
    inv.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'capture':
        result = capture(args.source, args.output, args.repo)
        print(json.dumps({'snapshot': result['snapshot'], 'promotion_eligible': False}))
    else:
        result = inventory(args.db)
        write_new(args.output, result)
        print(json.dumps({'counts': result['counts'], 'output': str(args.output)}))


if __name__ == '__main__':
    main()
