"""Storage conservation, corruption refusal and atomic rollback contracts."""
import gzip
import hashlib
import sqlite3

import pytest

from shared_wong_choi import sqlite_payload_archive as archive


def connection(factory=sqlite3.Connection):
    conn = sqlite3.connect(":memory:", factory=factory)
    conn.execute("CREATE TABLE raw_api_responses(id INTEGER PRIMARY KEY,response_json TEXT,provider TEXT,fetched_at TEXT)")
    conn.execute("CREATE TABLE feature_snapshots(id INTEGER PRIMARY KEY,features_json TEXT,provenance_json TEXT)")
    return conn


def insert(conn, identifier, text):
    conn.execute("INSERT INTO raw_api_responses VALUES (?,?,'provider','2020-01-01T00:00:00Z')", (identifier, text))


@pytest.mark.parametrize("text", ['{\n "名字": "鄭欽文", "n": 1.00\n}\n', 'not json\x00with\r\nbytes'])
def test_exact_text_and_metadata_survive_compaction(text):
    conn = connection()
    insert(conn, 1, text)
    before = conn.execute("SELECT * FROM raw_api_responses").fetchone()
    result = archive.compact_payloads(conn, "raw_response", "id=1")
    after = conn.execute("SELECT * FROM raw_api_responses").fetchone()
    assert after == (before[0], "", *before[2:])
    restored = archive.read_payload(conn, "raw_response", 1, after[1])
    assert restored.encode() == text.encode()
    assert result["bytes_freed"] == len(text.encode()) and result["lossless"]
    assert result["gzip_bytes_added"] > 0
    assert conn.execute("SELECT archived_at FROM retained_payload_refs").fetchone()[0] > before[3]


def test_identical_bytes_deduplicate_without_merging_record_namespaces():
    conn = connection()
    for identifier in (1, 2):
        insert(conn, identifier, "same original bytes")
    conn.execute("INSERT INTO feature_snapshots VALUES (1,'same original bytes','original provenance')")
    archive.compact_payloads(conn, "raw_response", "response_json!=''")
    result = archive.compact_payloads(conn, "feature_snapshot", "features_json!=''")
    assert result["gzip_bytes_added"] == 0
    assert conn.execute("SELECT COUNT(*) FROM retained_payload_blobs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM retained_payload_refs").fetchone()[0] == 3
    assert archive.read_payload(conn, "feature_snapshot", 1, "") == "same original bytes"
    assert conn.execute("SELECT provenance_json FROM feature_snapshots").fetchone()[0] == "original provenance"


def test_legacy_empty_cells_are_not_invented_or_given_a_receipt():
    conn = connection()
    insert(conn, 1, "")
    assert archive.read_payload(conn, "raw_response", 1, "") == ""
    with pytest.raises(archive.PayloadArchiveError, match="legacy loss"):
        archive.compact_payloads(conn, "raw_response", "id=1")
    assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='retained_payload_refs'").fetchall()


def test_dry_run_is_read_only_and_creates_no_schema():
    conn = connection()
    insert(conn, 1, "a body")
    conn.commit()
    conn.execute("PRAGMA query_only=ON")
    assert archive.compact_payloads(conn, "raw_response", "id=1", dry_run=True)["rows"] == 1
    assert conn.execute("SELECT response_json FROM raw_api_responses").fetchone()[0] == "a body"
    assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'retained_payload_%'").fetchall()


def test_second_body_failure_restores_first_and_preserves_callers_transaction(monkeypatch):
    conn = connection()
    insert(conn, 1, "first")
    insert(conn, 2, "second")
    conn.execute("CREATE TABLE unrelated(value TEXT)")
    conn.commit()
    conn.execute("INSERT INTO unrelated VALUES ('pending caller work')")
    compress = archive.gzip.compress
    calls = 0
    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated write/codec failure")
        return compress(*args, **kwargs)
    monkeypatch.setattr(archive.gzip, "compress", fail_second)
    with pytest.raises(RuntimeError, match="simulated"):
        archive.compact_payloads(conn, "raw_response", "id<=2")
    assert list(conn.execute("SELECT response_json FROM raw_api_responses ORDER BY id")) == [("first",), ("second",)]
    assert conn.in_transaction and conn.execute("SELECT COUNT(*) FROM unrelated").fetchone()[0] == 1
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM unrelated").fetchone()[0] == 0


@pytest.mark.parametrize("table", ["retained_payload_refs", "retained_payload_blobs"])
@pytest.mark.parametrize("action", ["UPDATE", "DELETE"])
def test_retention_receipts_and_blobs_are_append_only(table, action):
    conn = connection()
    insert(conn, 1, "original")
    archive.compact_payloads(conn, "raw_response", "id=1")
    sql = f"DELETE FROM {table}" if action == "DELETE" else f"UPDATE {table} SET sha256=sha256"
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute(sql)


@pytest.mark.parametrize("fault", ["gzip_hash", "body_hash", "length", "trailing", "truncated", "zipbomb", "missing_blob"])
def test_corrupt_or_oversized_archives_never_return_another_body(fault):
    conn = connection()
    archive._schema(conn)
    text = b"original" * 100
    blob = gzip.compress(text, mtime=0)
    digest = hashlib.sha256(text).hexdigest()
    length = len(text)
    if fault == "body_hash": digest = "0" * 64
    if fault == "length": length += 1
    if fault == "trailing": blob += gzip.compress(b"second member", mtime=0)
    if fault == "truncated": blob = blob[:-4]
    if fault == "zipbomb": length = 1  # a lying length must not bypass expansion limits
    compressed_digest = "0" * 64 if fault == "gzip_hash" else hashlib.sha256(blob).hexdigest()
    if fault != "missing_blob":
        conn.execute("INSERT INTO retained_payload_blobs VALUES (?,?,?,?)", (digest, length, compressed_digest, blob))
    conn.execute("INSERT INTO retained_payload_refs VALUES ('raw_response',1,?,'2026-10-29T00:00:00Z')", (digest,))
    with pytest.raises(archive.PayloadArchiveError):
        archive.read_payload(conn, "raw_response", 1, "", max_bytes=100 if fault == "zipbomb" else 1024)


def test_plaintext_mutation_cannot_replace_a_retained_original():
    conn = connection()
    insert(conn, 1, "original")
    archive.compact_payloads(conn, "raw_response", "id=1")
    conn.execute("UPDATE raw_api_responses SET response_json='different' WHERE id=1")
    with pytest.raises(archive.PayloadArchiveError, match="differs"):
        archive.read_payload(conn, "raw_response", 1, "different")
    with pytest.raises(archive.PayloadArchiveError, match="changed after"):
        archive.compact_payloads(conn, "raw_response", "id=1")
    assert conn.execute("SELECT response_json FROM raw_api_responses").fetchone()[0] == "different"


def test_compaction_limit_aborts_without_clearing_source(monkeypatch):
    conn = connection()
    insert(conn, 1, "too big")
    monkeypatch.setattr(archive, "MAX_PAYLOAD_BYTES", 3)
    with pytest.raises(archive.PayloadArchiveLimit):
        archive.compact_payloads(conn, "raw_response", "id=1")
    assert conn.execute("SELECT response_json FROM raw_api_responses").fetchone()[0] == "too big"


def test_stored_blob_is_read_back_before_inline_source_is_cleared():
    class DamagedWrite(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql.startswith("INSERT INTO retained_payload_blobs"):
                parameters = (*parameters[:3], parameters[3] + b"damage")
            return super().execute(sql, parameters)
    conn = connection(DamagedWrite)
    insert(conn, 1, "must remain available")
    with pytest.raises(archive.PayloadArchiveError, match="gzip hash"):
        archive.compact_payloads(conn, "raw_response", "id=1")
    assert conn.execute("SELECT response_json FROM raw_api_responses").fetchone()[0] == "must remain available"


def test_sqlite_backup_and_vacuum_preserve_read_only_originals(tmp_path):
    conn = connection()
    original = '{"名字":"原樣保存", "n":1.00}\r\n' * 100
    insert(conn, 1, original)
    archive.compact_payloads(conn, "raw_response", "id=1")
    conn.commit()
    destination = tmp_path / "restored.sqlite"
    with sqlite3.connect(destination) as restored:
        conn.backup(restored)
        restored.execute("VACUUM")
        assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    before = hashlib.sha256(destination.read_bytes()).hexdigest()
    with sqlite3.connect(destination.as_uri() + "?mode=ro", uri=True) as restored:
        restored.execute("PRAGMA query_only=ON")
        assert archive.read_payload(restored, "raw_response", 1, "") == original
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == before
    with sqlite3.connect(destination) as restored:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            restored.execute("DELETE FROM retained_payload_blobs")
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == before
