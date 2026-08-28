"""Verified Cloudflare D1 ledger backup for Central Wong Choi.

The remote database is read only.  Every export is restored into a new local
SQLite database and compared with stable before/after remote row counts before
the immutable snapshot is copied to WARM storage.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .artifact_archive import (
    ArtifactArchiveError,
    archive_copy,
    artifact_digest,
    mirror_artifact,
)


BACKUP_SCHEMA = "wong-choi-d1-backup/v1"
BACKUP_STATUS_SCHEMA = "wong-choi-d1-backup-status/v1"
D1_TABLES = (
    "analysis_runs",
    "recommendations",
    "bets",
    "bet_legs",
    "settlements",
    "audit_log",
    "migration_state",
)


class DashboardBackupError(RuntimeError):
    """D1 export, restore or consistency verification failed."""


Runner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=600,
        check=False,
    )


def _read_dashboard_config(root: Path) -> tuple[str, str]:
    package_path = root / "package.json"
    wrangler_path = root / "wrangler.toml"
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
        version = str((package.get("devDependencies") or {}).get("wrangler") or "")
        version = version.lstrip("^~")
        config = wrangler_path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise DashboardBackupError(f"dashboard backup config unreadable: {exc}") from exc
    match = re.search(r'(?m)^database_name\s*=\s*"([^"]+)"\s*$', config)
    if not version or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise DashboardBackupError("package.json must pin an exact Wrangler version")
    if not match:
        raise DashboardBackupError("wrangler.toml has no D1 database_name")
    return version, match.group(1)


def _json_output(raw: str) -> Any:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except ValueError:
        starts = [index for index in (raw.find("["), raw.find("{")) if index >= 0]
        if not starts:
            raise DashboardBackupError("Wrangler returned no JSON payload")
        try:
            return json.loads(raw[min(starts):])
        except ValueError as exc:
            raise DashboardBackupError("Wrangler returned malformed JSON") from exc


def _parse_counts(raw: str) -> dict[str, int]:
    payload = _json_output(raw)
    envelopes = payload if isinstance(payload, list) else [payload]
    rows: list[dict[str, Any]] = []
    for envelope in envelopes:
        if not isinstance(envelope, dict):
            continue
        if envelope.get("success") is False:
            raise DashboardBackupError("D1 row-count query reported failure")
        result = envelope.get("results")
        if isinstance(result, list):
            rows.extend(item for item in result if isinstance(item, dict))
    counts: dict[str, int] = {}
    for row in rows:
        if set(D1_TABLES).issubset(row):
            try:
                return {table: int(row[table]) for table in D1_TABLES}
            except (TypeError, ValueError) as exc:
                raise DashboardBackupError("invalid D1 scalar row counts") from exc
        name = str(row.get("table_name") or "")
        if name not in D1_TABLES:
            continue
        try:
            counts[name] = int(row.get("row_count"))
        except (TypeError, ValueError) as exc:
            raise DashboardBackupError(f"invalid D1 row count for {name}") from exc
    missing = sorted(set(D1_TABLES) - set(counts))
    if missing:
        raise DashboardBackupError("D1 row-count response missing: " + ", ".join(missing))
    return counts


def _count_query() -> str:
    # D1 imposes a low compound-SELECT term limit.  One row of scalar
    # subqueries works on remote D1 and is still deterministic to parse.
    return "SELECT " + ", ".join(
        f"(SELECT COUNT(*) FROM {table}) AS {table}" for table in D1_TABLES
    ) + ";"


def _wrangler_base(version: str) -> list[str]:
    return ["npx", "--yes", f"wrangler@{version}", "d1"]


def _remote_counts(
    root: Path,
    database: str,
    version: str,
    runner: Runner,
) -> dict[str, int]:
    command = _wrangler_base(version) + [
        "execute",
        database,
        "--remote",
        "--command",
        _count_query(),
        "--json",
    ]
    result = runner(command, root)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown error").strip()[-1000:]
        raise DashboardBackupError(f"D1 row-count query failed: {detail}")
    return _parse_counts(result.stdout)


def _export_remote(
    root: Path,
    database: str,
    version: str,
    destination: Path,
    runner: Runner,
) -> None:
    command = _wrangler_base(version) + [
        "export",
        database,
        "--remote",
        "--skip-confirmation",
        "--output",
        str(destination),
    ]
    result = runner(command, root)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown error").strip()[-1000:]
        raise DashboardBackupError(f"D1 export failed: {detail}")
    if not destination.is_file() or destination.stat().st_size == 0:
        raise DashboardBackupError("D1 export produced no SQL file")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_d1_export(sql_path: Path, restore_path: Path) -> dict[str, Any]:
    """Restore an export into a new SQLite DB and return integrity evidence."""
    if restore_path.exists():
        raise DashboardBackupError("D1 restore destination already exists")
    restore_path.parent.mkdir(parents=True, exist_ok=True)
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(str(restore_path))
        connection.executescript(sql_path.read_text(encoding="utf-8"))
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in D1_TABLES
        }
    except (OSError, UnicodeError, sqlite3.Error) as exc:
        raise DashboardBackupError(f"D1 local restore failed: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()
    if integrity.lower() != "ok":
        raise DashboardBackupError(f"D1 restored integrity_check failed: {integrity}")
    if foreign_keys:
        raise DashboardBackupError(
            f"D1 restored foreign_key_check found {len(foreign_keys)} errors"
        )
    return {
        "status": "pass",
        "integrity_check": integrity,
        "foreign_key_errors": 0,
        "row_counts": counts,
    }


def _write_json_exclusive(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def backup_d1_ledger(
    dashboard_root: Path,
    state_root: Path,
    *,
    warm_root: Path | None,
    cold_root: Path | None = None,
    runner: Runner = _run,
    now: datetime | None = None,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Export, restore-verify and archive the live ledger without mutating D1."""
    dashboard_root = dashboard_root.expanduser().resolve()
    state_root = state_root.expanduser().resolve()
    version, database = _read_dashboard_config(dashboard_root)
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise DashboardBackupError("backup clock must be timezone-aware")
    snapshots = state_root / "dashboard_d1" / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    stamp = clock.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    final = snapshots / stamp
    if final.exists():
        raise DashboardBackupError(f"immutable D1 snapshot already exists: {final}")

    last_error = ""
    for attempt in range(1, max_attempts + 1):
        partial = snapshots / f".{stamp}.partial-{uuid.uuid4().hex}"
        partial.mkdir()
        sql_path = partial / "wongchoi-ledger.sql"
        restore_path = partial / "restore-verification.sqlite"
        try:
            before = _remote_counts(dashboard_root, database, version, runner)
            _export_remote(dashboard_root, database, version, sql_path, runner)
            after = _remote_counts(dashboard_root, database, version, runner)
            restored = verify_d1_export(sql_path, restore_path)
            if before != after:
                raise DashboardBackupError("D1 changed during export; retrying stable snapshot")
            if restored["row_counts"] != after:
                raise DashboardBackupError("D1 export row counts do not match remote snapshot")
            restore_path.unlink()
            manifest = {
                "schema_version": BACKUP_SCHEMA,
                "snapshot_at": clock.astimezone(timezone.utc).isoformat(),
                "database": database,
                "wrangler_version": version,
                "attempt": attempt,
                "remote_row_counts_before": before,
                "remote_row_counts_after": after,
                "restore": restored,
                "sql": {
                    "filename": sql_path.name,
                    "bytes": sql_path.stat().st_size,
                    "sha256": _sha256(sql_path),
                },
                "remote_mutated": False,
                "source_removed": False,
            }
            _write_json_exclusive(partial / "manifest.json", manifest)
            os.replace(partial, final)
            break
        except Exception as exc:
            last_error = str(exc)
            shutil.rmtree(partial, ignore_errors=True)
            if "changed during export" in last_error and attempt < max_attempts:
                continue
            if isinstance(exc, DashboardBackupError):
                raise
            raise DashboardBackupError(
                f"D1 backup attempt failed: {type(exc).__name__}: {exc}"
            ) from exc
    else:
        raise DashboardBackupError(last_error or "D1 backup attempts exhausted")

    result: dict[str, Any] = {
        "status": "pass",
        "snapshot": str(final),
        "manifest": str(final / "manifest.json"),
        "database": database,
        "row_counts": manifest["restore"]["row_counts"],
        "sql": manifest["sql"],
        "warm": {"status": "deferred", "reason": "warm root not configured"},
        "cold": {"status": "deferred", "reason": "cold root not configured"},
    }
    if warm_root is None:
        return result
    try:
        archived = archive_copy(
            final,
            warm_root=warm_root,
            catalog_root=state_root / "storage" / "catalog",
            domain="central",
            artifact_class="d1-ledger-backup",
            allowed_roots=[state_root],
            created_at=clock.astimezone(timezone.utc).isoformat(),
        )
        result["warm"] = archived
    except ArtifactArchiveError as exc:
        result["status"] = "deferred"
        result["warm"] = {"status": "deferred", "reason": str(exc)}
        return result
    if cold_root is not None:
        try:
            result["cold"] = mirror_artifact(
                Path(str(archived["manifest"])),
                cold_root=cold_root,
                mirrored_at=clock.astimezone(timezone.utc).isoformat(),
            )
        except ArtifactArchiveError as exc:
            result["status"] = "deferred"
            result["cold"] = {"status": "deferred", "reason": str(exc)}
    return result


def collect_d1_backup_status(
    state_root: Path,
    *,
    now: datetime | None = None,
    stale_after_hours: int = 36,
) -> dict[str, Any]:
    """Read the latest immutable backup and derive WARM/COLD verification."""
    state_root = state_root.expanduser().resolve()
    clock = now or datetime.now(timezone.utc)
    manifests = sorted((state_root / "dashboard_d1" / "snapshots").glob("*/manifest.json"))
    if not manifests:
        return {
            "schema_version": BACKUP_STATUS_SCHEMA,
            "status": "no_data",
            "attention": ["dashboard_d1_backup_missing"],
            "stale_after_hours": stale_after_hours,
        }
    manifest_path = manifests[-1]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        snapshot_at = datetime.fromisoformat(str(manifest["snapshot_at"]).replace("Z", "+00:00"))
    except (OSError, ValueError, KeyError) as exc:
        return {
            "schema_version": BACKUP_STATUS_SCHEMA,
            "status": "invalid",
            "attention": ["dashboard_d1_backup_manifest_invalid"],
            "error": str(exc),
        }
    age_hours = max(0.0, (clock.astimezone(timezone.utc) - snapshot_at).total_seconds() / 3600)
    snapshot = manifest_path.parent.resolve()
    archive_record: dict[str, Any] | None = None
    records = state_root / "storage" / "catalog" / "records"
    for path in records.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if Path(str(item.get("source") or "")).resolve() == snapshot:
            archive_record = {**item, "manifest": str(path)}
            break
    warm_destination = Path(str((archive_record or {}).get("destination") or ""))
    try:
        warm_verified = bool(
            archive_record
            and warm_destination.exists()
            and archive_record.get("source_digest") == archive_record.get("destination_digest")
            and artifact_digest(warm_destination) == archive_record.get("destination_digest")
        )
    except OSError:
        warm_verified = False
    artifact_id = str((archive_record or {}).get("artifact_id") or "")
    cold_verified = False
    if artifact_id:
        for path in (state_root / "storage" / "catalog" / "events").glob("*.json"):
            try:
                event = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            destination = Path(str(event.get("destination") or ""))
            if (
                event.get("schema_version") == "wong-choi-artifact-mirror/v1"
                and event.get("artifact_id") == artifact_id
                and destination.exists()
            ):
                try:
                    cold_verified = artifact_digest(destination) == event.get("digest")
                except OSError:
                    cold_verified = False
                break
    attention: list[str] = []
    if age_hours > stale_after_hours:
        attention.append("dashboard_d1_backup_stale")
    if not warm_verified:
        attention.append("dashboard_d1_backup_warm_pending")
    status = "ok" if not attention else "attention"
    return {
        "schema_version": BACKUP_STATUS_SCHEMA,
        "status": status,
        "attention": attention,
        "snapshot_at": snapshot_at.astimezone(timezone.utc).isoformat(),
        "age_hours": round(age_hours, 2),
        "stale_after_hours": stale_after_hours,
        "snapshot": str(snapshot),
        "manifest": str(manifest_path),
        "database": manifest.get("database"),
        "sql": manifest.get("sql"),
        "row_counts": (manifest.get("restore") or {}).get("row_counts"),
        "restore_verified": (manifest.get("restore") or {}).get("status") == "pass",
        "warm_verified": warm_verified,
        "cold_verified": cold_verified,
        "artifact_id": artifact_id or None,
    }
