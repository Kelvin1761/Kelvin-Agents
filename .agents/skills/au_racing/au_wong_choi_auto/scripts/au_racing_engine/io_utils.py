from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path


def write_json_atomic(
    path: Path,
    data: object,
    *,
    indent: int | None = 2,
    default=None,
) -> None:
    """Serialize and replace a JSON file without exposing partial content."""
    try:
        payload = json.dumps(
            data,
            ensure_ascii=False,
            indent=indent,
            default=default,
        )
    except TypeError as exc:
        raise ValueError(
            f"Failed to serialize Logic.json: {path}\n{exc}"
        ) from exc
    write_text_atomic(path, payload)


def write_text_atomic(path: Path, text: str) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def write_csv_atomic(
    path: Path,
    rows: list[dict],
    fieldnames: list[str],
) -> None:
    """Replace a CSV only after the complete payload has been flushed."""
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()
