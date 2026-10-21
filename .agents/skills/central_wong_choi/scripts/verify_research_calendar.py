#!/usr/bin/env python3
"""Read-only calendar postcondition for the existing transactional installer."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import plistlib
import stat

LABEL = "com.antigravity.central-wong-choi.research-review"
MAX_BYTES = 65536


def _read(path: Path) -> dict:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
            raise ValueError("research plist type/size invalid")
        data = bytearray()
        while len(data) <= MAX_BYTES:
            chunk = os.read(descriptor, min(8192, MAX_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(descriptor)
        signature = lambda s: (s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if len(data) > MAX_BYTES or signature(before) != signature(after):
            raise ValueError("research plist changed while reading")
    finally:
        os.close(descriptor)
    payload = plistlib.loads(bytes(data))
    if not isinstance(payload, dict) or payload.get("Label") != LABEL:
        raise ValueError("unexpected research plist label")
    if "RunAtLoad" in payload:
        raise ValueError("unexpected research RunAtLoad")
    return payload


def _calendar(payload: dict) -> tuple:
    raw = payload.get("StartCalendarInterval")
    entries = [raw] if isinstance(raw, dict) else raw
    if not isinstance(entries, list) or not 0 < len(entries) <= 8:
        raise ValueError("research calendar missing or invalid")
    normalized = []
    for entry in entries:
        if (not isinstance(entry, dict) or not {"Hour", "Minute"} <= set(entry)
                or set(entry) - {"Hour", "Minute", "Weekday"}
                or any(type(value) is not int for value in entry.values())
                or not 0 <= entry["Hour"] <= 23 or not 0 <= entry["Minute"] <= 59
                or "Weekday" in entry and not 0 <= entry["Weekday"] <= 7):
            raise ValueError("invalid research calendar slot")
        slot = dict(entry)
        if slot.get("Weekday") == 7:
            slot["Weekday"] = 0
        normalized.append(tuple(sorted(slot.items())))
    if len(set(normalized)) != len(normalized):
        raise ValueError("duplicate research calendar slot")
    return tuple(sorted(normalized))


def verify_calendar(template: Path, installed: Path) -> dict:
    try:
        expected = _calendar(_read(Path(template)))
        actual = _calendar(_read(Path(installed)))
    except (OSError, plistlib.InvalidFileException) as exc:
        raise ValueError("cannot verify research calendar") from exc
    if actual != expected:
        raise ValueError("installed research calendar differs from source template")
    return {"status": "aligned", "label": LABEL, "calendar_slots": len(actual)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--installed", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify_calendar(args.template, args.installed)
    except ValueError as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
