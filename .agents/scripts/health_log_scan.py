"""Read event times from scheduler text/JSON logs without dating replayed errors today."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

ERROR_RE = re.compile(r"traceback|fatal|Operation not permitted|unbound variable|❌ \[", re.I)
STAMP_RE = re.compile(r"\[?(20\d\d-\d\d-\d\d[T ][0-9:]+(?:[+-][0-9:]+|Z)?)")
TIME_KEYS = ("at", "completed_at", "generated_at", "started_at", "timestamp")


def _time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone().replace(tzinfo=None) if parsed.tzinfo else parsed
    except (ValueError, TypeError):
        return None


def _json_time(payload: dict, runs_root: Path):
    for key in TIME_KEYS:
        parsed = _time(payload.get(key))
        if parsed is not None:
            return parsed
    # Control output may replay old attempts with no timestamp on the JSON line.
    # Use the referenced durable attempt's completion time, never file mtime or
    # target_date (a recovery can execute on a different day).
    for artifact in payload.get("artifacts") or []:
        if not isinstance(artifact, str):
            continue
        path = Path(artifact)
        if not path.is_absolute() or path.suffix != ".json":
            continue
        try:
            if not path.resolve().is_relative_to(runs_root.resolve()):
                continue
            attempt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(attempt, dict):
            for key in TIME_KEYS:
                parsed = _time(attempt.get(key))
                if parsed is not None:
                    return parsed
    return None


def recent_errors(lines, cutoff: datetime, runs_root: Path) -> tuple[list[str], int]:
    current_time = None
    errors = []
    undated = 0
    for line in lines:
        try:
            payload = json.loads(line)
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            current_time = _json_time(payload, runs_root)
        else:
            match = STAMP_RE.search(line)
            if match:
                current_time = _time(match.group(1))
        if not ERROR_RE.search(line):
            continue
        if current_time is None:
            undated += 1
        elif current_time >= cutoff:
            errors.append(line)
    return errors, undated
