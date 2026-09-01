"""Deterministic create-only prediction snapshots for domains without one."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_immutable_snapshot(
    source_dir: Path,
    *,
    domain: str,
    event_id: str,
    patterns: Iterable[str],
    recommendations: Iterable[Mapping[str, Any]] = (),
    root_name: str = "_prediction_snapshots",
    at: datetime | None = None,
) -> Path:
    source_dir = source_dir.resolve()
    files = sorted(
        {
            path
            for pattern in patterns
            for path in source_dir.glob(pattern)
            if path.is_file() and path.stat().st_size > 0
        }
    )
    if not files:
        raise RuntimeError(f"no prediction artifacts in {source_dir}")
    selected = [dict(item) for item in recommendations]
    file_manifest = [
        {
            "name": path.name,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in files
    ]
    signature = hashlib.sha256(
        json.dumps(
            {"files": file_manifest, "recommendations": selected},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    root = source_dir / root_name
    if root.exists():
        for manifest_path in sorted(root.glob("*/manifest.json"), reverse=True):
            try:
                existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if existing.get("signature") == signature:
                return manifest_path.parent

    clock = at or datetime.now(timezone.utc)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("snapshot timestamp must be timezone-aware")
    root.mkdir(parents=True, exist_ok=True)
    name = clock.strftime("%Y%m%dT%H%M%S.%f%z") + f"-{signature[:12]}"
    temporary = root / f".{name}.tmp"
    final = root / name
    if final.exists() or temporary.exists():
        raise RuntimeError(f"snapshot destination already exists: {final}")
    temporary.mkdir()
    try:
        for source in files:
            shutil.copy2(source, temporary / source.name)
        manifest = {
            "schema_version": "wong-choi-prediction-snapshot/v1",
            "domain": domain,
            "event_id": event_id,
            "created_at": clock.isoformat(),
            "signature": signature,
            "append_only": True,
            "recommendations": selected,
            "files": file_manifest,
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(final)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return final
