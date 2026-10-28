"""Prevent corpus loss, source writes and accidental reuse of old captures."""
import sqlite3

import pytest

from research.tennis_unified.warehouse import capture_database, digest, readonly, table_counts, write_new


def test_consistent_backup_includes_uncheckpointed_wal_and_all_tables(tmp_path):
    source, output = tmp_path / 'live.db', tmp_path / 'research.db'
    writer = sqlite3.connect(source)
    writer.execute('PRAGMA journal_mode=WAL')
    writer.execute('CREATE TABLE results(id INTEGER PRIMARY KEY, label TEXT)')
    writer.execute('CREATE TABLE unseen(id INTEGER PRIMARY KEY, x INTEGER)')
    writer.execute('CREATE INDEX result_label ON results(label)')
    writer.execute("INSERT INTO results VALUES(1,'lost')")
    writer.execute('INSERT INTO unseen VALUES(1,NULL)')
    writer.commit()
    report = capture_database(source, output)
    assert report['counts'] == {'results': 1, 'unseen': 1}
    assert report['sha256'] == digest(output)
    with readonly(output) as conn:
        assert table_counts(conn) == report['counts']
        assert conn.execute('SELECT label FROM results').fetchone()[0] == 'lost'
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchone()[0] == 'result_label'
        with pytest.raises(sqlite3.OperationalError):
            conn.execute('DELETE FROM results')
    writer.execute("INSERT INTO results VALUES(2,'won')")
    writer.commit()
    with readonly(output) as conn:
        assert table_counts(conn)['results'] == 1
    assert writer.execute('SELECT COUNT(*) FROM results').fetchone()[0] == 2
    writer.close()


def test_capture_never_overwrites_existing_evidence(tmp_path):
    source = tmp_path / 'source.db'
    sqlite3.connect(source).close()
    output = tmp_path / 'output.db'
    output.write_bytes(b'original evidence')
    with pytest.raises(FileExistsError):
        capture_database(source, output)
    assert output.read_bytes() == b'original evidence'
    with pytest.raises(ValueError, match='must differ'):
        capture_database(source, source)


def test_missing_source_cannot_create_a_fake_empty_database(tmp_path):
    source, output = tmp_path / 'missing.db', tmp_path / 'out.db'
    with pytest.raises(sqlite3.OperationalError):
        capture_database(source, output)
    assert not source.exists() and not output.exists()


def test_manifest_creation_is_exclusive(tmp_path):
    target = tmp_path / 'manifest.json'
    write_new(target, {'locked': True})
    original = target.read_bytes()
    with pytest.raises(FileExistsError):
        write_new(target, {'locked': False})
    assert target.read_bytes() == original
