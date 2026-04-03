#!/usr/bin/env python3
"""
Safe File Writer — Anti-Streaming-Lock Pipeline
================================================
Bypasses IDE streaming deadlock caused by alphabetical JSON key ordering
in write_to_file / replace_file_content tools.

Usage:
    # Write Base64-encoded content to a file:
    python safe_file_writer.py --target "/path/to/file.md" --mode overwrite --content "BASE64_STRING"

    # Read Base64 content from stdin (for very large payloads):
    echo "BASE64_STRING" | python safe_file_writer.py --target "/path/to/file.md" --mode overwrite --stdin

    # Dry-run mode (validate only, no write):
    python safe_file_writer.py --target "/path/to/file.md" --mode create --content "BASE64_STRING" --dry-run

    # Append mode:
    python safe_file_writer.py --target "/path/to/file.md" --mode append --content "BASE64_STRING"

Exit Codes:
    0 = Success
    1 = Argument error
    2 = Decode error
    3 = File system error
    4 = Target file already exists (in create mode)

Output:
    JSON object on stdout with status, line count, byte count, and target path.
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path


def make_result(success: bool, message: str, target: str = "", lines: int = 0, bytes_written: int = 0) -> dict:
    return {
        "success": success,
        "message": message,
        "target": target,
        "lines": lines,
        "bytes": bytes_written,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Safe File Writer — bypass IDE streaming deadlock."
    )
    parser.add_argument(
        "--target", "-t",
        required=True,
        help="Absolute path to the target file."
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["create", "overwrite", "append"],
        default="overwrite",
        help="Write mode: create (fail if exists), overwrite, or append."
    )
    parser.add_argument(
        "--content", "-c",
        default=None,
        help="Base64-encoded content string."
    )
    parser.add_argument(
        "--stdin", "-s",
        action="store_true",
        help="Read Base64 content from stdin instead of --content."
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Validate and decode only; do not write to disk."
    )
    parser.add_argument(
        "--encoding", "-e",
        default="utf-8",
        help="Text encoding for the decoded content (default: utf-8)."
    )

    args = parser.parse_args()

    # ── 1. Resolve target path ──────────────────────────────────────
    target_path = Path(args.target).resolve()

    # ── 2. Get Base64 content ───────────────────────────────────────
    if args.stdin:
        b64_content = sys.stdin.read().strip()
    elif args.content is not None:
        b64_content = args.content.strip()
    else:
        print(json.dumps(make_result(False, "Error: either --content or --stdin is required.")))
        sys.exit(1)

    if not b64_content:
        print(json.dumps(make_result(False, "Error: empty content provided.")))
        sys.exit(1)

    # ── 3. Decode Base64 ────────────────────────────────────────────
    try:
        decoded_bytes = base64.b64decode(b64_content)
        decoded_text = decoded_bytes.decode(args.encoding)
    except Exception as e:
        print(json.dumps(make_result(False, f"Base64 decode error: {e}")))
        sys.exit(2)

    # ── 4. Pre-flight checks ────────────────────────────────────────
    line_count = decoded_text.count("\n") + (1 if decoded_text and not decoded_text.endswith("\n") else 0)
    byte_count = len(decoded_bytes)

    if args.mode == "create" and target_path.exists():
        print(json.dumps(make_result(
            False,
            f"Target file already exists (mode=create): {target_path}",
            str(target_path), line_count, byte_count
        )))
        sys.exit(4)

    # ── 5. Dry-run exit ─────────────────────────────────────────────
    if args.dry_run:
        print(json.dumps(make_result(
            True,
            f"Dry-run OK: {line_count} lines, {byte_count} bytes would be written.",
            str(target_path), line_count, byte_count
        )))
        sys.exit(0)

    # ── 6. Ensure parent directories exist ──────────────────────────
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(json.dumps(make_result(False, f"Cannot create parent directories: {e}")))
        sys.exit(3)

    # ── 7. Write file ───────────────────────────────────────────────
    try:
        write_mode = "a" if args.mode == "append" else "w"
        with open(target_path, write_mode, encoding=args.encoding) as f:
            f.write(decoded_text)
    except Exception as e:
        print(json.dumps(make_result(False, f"File write error: {e}")))
        sys.exit(3)

    # ── 8. Success ──────────────────────────────────────────────────
    print(json.dumps(make_result(
        True,
        f"OK: {line_count} lines ({byte_count} bytes) written to {target_path}",
        str(target_path), line_count, byte_count
    )))
    sys.exit(0)


if __name__ == "__main__":
    main()
