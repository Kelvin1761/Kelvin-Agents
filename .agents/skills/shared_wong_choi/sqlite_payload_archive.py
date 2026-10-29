"""Lossless SQLite payload compaction; metadata and source clocks stay in place.

This is storage, not source qualification. Legacy empty cells without a
retention receipt remain empty. No external lookup or historical reconstruction.
"""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import hashlib
import sqlite3
import zlib


MAX_PAYLOAD_BYTES = 128 * 1024 * 1024
PAYLOAD_COLUMNS = {
    "raw_response": ("raw_api_responses", "response_json"),
    "feature_snapshot": ("feature_snapshots", "features_json"),
}


class PayloadArchiveError(ValueError):
    """A retained body cannot be verified; never substitute another version."""


class PayloadArchiveLimit(PayloadArchiveError):
    pass


def _schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS retained_payload_blobs (
        sha256 TEXT PRIMARY KEY, byte_length INTEGER NOT NULL,
        gzip_sha256 TEXT NOT NULL, gzip_data BLOB NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS retained_payload_refs (
        kind TEXT NOT NULL, row_id INTEGER NOT NULL, sha256 TEXT NOT NULL,
        archived_at TEXT NOT NULL, PRIMARY KEY(kind,row_id),
        FOREIGN KEY(sha256) REFERENCES retained_payload_blobs(sha256))""")
    for table in ("retained_payload_blobs", "retained_payload_refs"):
        for action in ("UPDATE", "DELETE"):
            conn.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()}
                BEFORE {action} ON {table} BEGIN
                SELECT RAISE(ABORT,'retained payloads are append-only'); END""")


def _has_refs(conn):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='retained_payload_refs'").fetchone() is not None


def _decode(blob, digest, byte_length, compressed_digest, max_bytes):
    if (type(byte_length) is not int or byte_length < 0 or byte_length > max_bytes
            or not isinstance(blob, bytes) or len(blob) > max_bytes + 65536):
        raise PayloadArchiveLimit("retained payload exceeds byte budget")
    if hashlib.sha256(blob).hexdigest() != compressed_digest:
        raise PayloadArchiveError("retained gzip hash mismatch")
    try:
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        body = decoder.decompress(blob, max_bytes + 1)
        if len(body) > max_bytes or decoder.unconsumed_tail:
            raise PayloadArchiveLimit("retained payload exceeds byte budget")
        if not decoder.eof or decoder.unused_data:
            raise PayloadArchiveError("retained gzip is truncated or has trailing data")
        if len(body) != byte_length or hashlib.sha256(body).hexdigest() != digest:
            raise PayloadArchiveError("retained original body hash/length mismatch")
        return body.decode("utf-8")
    except (zlib.error, UnicodeError) as exc:
        raise PayloadArchiveError("invalid retained payload encoding") from exc


def retained_byte_length(conn, kind, row_id):
    if kind not in PAYLOAD_COLUMNS:
        raise ValueError("unsupported retained payload kind")
    if not _has_refs(conn):
        return None
    row = conn.execute("""SELECT b.byte_length FROM retained_payload_refs r
        LEFT JOIN retained_payload_blobs b ON b.sha256=r.sha256
        WHERE r.kind=? AND r.row_id=?""", (kind, row_id)).fetchone()
    if row is None:
        return None
    if type(row[0]) is not int or row[0] < 0:
        raise PayloadArchiveError("retained payload blob missing or invalid")
    return row[0]


def read_payload(conn, kind, row_id, stored, *, max_bytes=MAX_PAYLOAD_BYTES):
    """Return original UTF-8 text, verifying any compressed representation."""
    if kind not in PAYLOAD_COLUMNS or not isinstance(stored, str):
        raise PayloadArchiveError("invalid retained payload reference/type")
    if type(max_bytes) is not int or not 0 < max_bytes <= MAX_PAYLOAD_BYTES:
        raise ValueError("invalid payload byte budget")
    ref = None
    if _has_refs(conn):
        ref = conn.execute("SELECT sha256 FROM retained_payload_refs WHERE kind=? AND row_id=?",
                           (kind, row_id)).fetchone()
    if ref is None:
        # An old destructive prune has no receipt; do not invent its body.
        return stored
    meta = conn.execute("""SELECT byte_length,gzip_sha256,length(gzip_data)
        FROM retained_payload_blobs WHERE sha256=?""", (ref[0],)).fetchone()
    if meta is None:
        raise PayloadArchiveError("retained payload blob missing")
    if (type(meta[0]) is not int or not 0 <= meta[0] <= max_bytes
            or type(meta[2]) is not int or not 0 <= meta[2] <= max_bytes + 65536):
        raise PayloadArchiveLimit("retained payload exceeds byte budget")
    blob = conn.execute("SELECT gzip_data FROM retained_payload_blobs WHERE sha256=?", (ref[0],)).fetchone()[0]
    body = _decode(blob, ref[0], meta[0], meta[1], max_bytes)
    if stored and stored != body:
        raise PayloadArchiveError("inline body differs from immutable retention receipt")
    return body


def compact_payloads(conn: sqlite3.Connection, kind: str, predicate: str, params=(), *, dry_run=False):
    """Atomically retain exact bodies before clearing redundant inline text.

    Caller predicates are internal SQL, not user input. A failed batch rolls
    back its receipts and all its inline changes, without committing a caller's
    existing transaction. Compression handles one body at a time.
    """
    if kind not in PAYLOAD_COLUMNS:
        raise ValueError("unsupported retained payload kind")
    table, column = PAYLOAD_COLUMNS[kind]
    measured = conn.execute(f"""SELECT COUNT(*),IFNULL(SUM(length(CAST({column} AS BLOB))),0)
        FROM {table} WHERE {predicate}""", params).fetchone()
    result = {"rows": int(measured[0]), "bytes_freed": int(measured[1]),
              "dry_run": bool(dry_run), "lossless": True, "gzip_bytes_added": 0,
              "bytes_freed_scope": "inline UTF-8 bytes, not net filesystem space"}
    if dry_run or not result["rows"]:
        return result
    conn.execute("SAVEPOINT retained_payload_compaction")
    try:
        _schema(conn)
        identifiers = [r[0] for r in conn.execute(f"SELECT id FROM {table} WHERE {predicate} ORDER BY id", params)]
        result["rows"], result["bytes_freed"] = len(identifiers), 0
        verified = set()
        at = datetime.now(timezone.utc).isoformat()
        for row_id in identifiers:
            row = conn.execute(f"SELECT {column} FROM {table} WHERE id=?", (row_id,)).fetchone()
            text = row[0]
            if not isinstance(text, str) or not text:
                raise PayloadArchiveError("payload must be nonempty UTF-8 text; legacy loss is not recoverable")
            body = text.encode("utf-8")
            if len(body) > MAX_PAYLOAD_BYTES:
                raise PayloadArchiveLimit("payload exceeds compaction byte budget")
            digest = hashlib.sha256(body).hexdigest()
            prior = conn.execute("SELECT sha256 FROM retained_payload_refs WHERE kind=? AND row_id=?",
                                 (kind, row_id)).fetchone()
            if prior is not None and prior[0] != digest:
                raise PayloadArchiveError("payload changed after immutable retention receipt")
            if digest not in verified:
                blob = conn.execute("SELECT byte_length,gzip_sha256,gzip_data FROM retained_payload_blobs WHERE sha256=?",
                                    (digest,)).fetchone()
                if blob is None:
                    compressed = gzip.compress(body, mtime=0)
                    compressed_digest = hashlib.sha256(compressed).hexdigest()
                    if _decode(compressed, digest, len(body), compressed_digest, MAX_PAYLOAD_BYTES) != text:
                        raise PayloadArchiveError("compaction roundtrip mismatch")
                    conn.execute("INSERT INTO retained_payload_blobs VALUES (?,?,?,?)",
                                 (digest, len(body), compressed_digest, compressed))
                    saved = conn.execute("SELECT byte_length,gzip_sha256,gzip_data FROM retained_payload_blobs WHERE sha256=?",
                                         (digest,)).fetchone()
                    if saved is None or _decode(saved[2], digest, saved[0], saved[1], MAX_PAYLOAD_BYTES) != text:
                        raise PayloadArchiveError("stored compaction roundtrip mismatch")
                    result["gzip_bytes_added"] += len(compressed)
                else:
                    _decode(blob[2], digest, blob[0], blob[1], MAX_PAYLOAD_BYTES)
                verified.add(digest)
            if prior is None:
                conn.execute("INSERT INTO retained_payload_refs VALUES (?,?,?,?)", (kind, row_id, digest, at))
            saved_ref = conn.execute("SELECT sha256 FROM retained_payload_refs WHERE kind=? AND row_id=?",
                                     (kind, row_id)).fetchone()
            if saved_ref is None or saved_ref[0] != digest:
                raise PayloadArchiveError("retention receipt was not stored")
            changed = conn.execute(f"UPDATE {table} SET {column}='' WHERE id=? AND CAST({column} AS BLOB)=?",
                                   (row_id, body)).rowcount
            if changed != 1:
                raise PayloadArchiveError("payload changed during compaction")
            result["bytes_freed"] += len(body)
        conn.execute("RELEASE retained_payload_compaction")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK TO retained_payload_compaction")
            conn.execute("RELEASE retained_payload_compaction")
        raise
    return result
