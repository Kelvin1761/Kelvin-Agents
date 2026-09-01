#!/usr/bin/env python3
"""Fetch and validate the currently published dashboard projection."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_URL = "https://wongchoi-dashboard.pages.dev/dashboard-data.json"


def validate_snapshot(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("dashboard snapshot root must be an object")
    if not isinstance(payload.get("meetings"), list):
        raise ValueError("dashboard snapshot meetings must be an array")
    if not isinstance(payload.get("races"), dict):
        raise ValueError("dashboard snapshot races must be an object")
    if not isinstance(payload.get("consensus", {}), dict):
        raise ValueError("dashboard snapshot consensus must be an object")
    return payload


def fetch_snapshot(url: str, output: Path, *, timeout: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "WongChoi-Central-Activation/1.0",
            "Accept": "application/json",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = validate_snapshot(json.loads(response.read()))

    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    descriptor, raw_temp = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=str(output.parent)
    )
    temp = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, output)
    finally:
        temp.unlink(missing_ok=True)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    payload = fetch_snapshot(args.url, args.output, timeout=args.timeout)
    print(
        "✅ Live dashboard snapshot verified: "
        f"{len(payload['meetings'])} meetings → {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
