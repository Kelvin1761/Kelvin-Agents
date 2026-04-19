#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
"""
Safe File Writer — Anti-Streaming-Lock Pipeline (WLTM Edition)
==============================================================
Bypasses IDE streaming deadlock AND Google Drive FileProvider lock
by writing to /tmp first, then atomically moving to the target.

WLTM = Write-Local-Then-Move

Usage:
    # Write Base64-encoded content to a file (WLTM mode, default):
    python safe_file_writer.py --target "/path/to/file.md" --mode overwrite --content "BASE64_STRING"

    # Read Base64 content from stdin (for very large payloads):
    echo "BASE64_STRING" | python safe_file_writer.py --target "/path/to/file.md" --mode overwrite --stdin

    # Disable WLTM (direct write, legacy mode):
    python safe_file_writer.py --target "/path/to/file.md" --mode overwrite --content "BASE64_STRING" --no-wltm

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
    5 = Move/timeout error (WLTM specific)

Output:
    JSON object on stdout with status, line count, byte count, target path, and method used.
"""

import argparse
import base64
import hashlib
import json
import os
import shutil
import signal
import sys
import tempfile
import threading
import uuid
from pathlib import Path


# ── Constants ───────────────────────────────────────────────────────
STAGING_DIR = os.path.join(tempfile.gettempdir(), "antigravity_staging")
DEFAULT_TIMEOUT = 15  # seconds for move operation


def make_result(success: bool, message: str, target: str = "", lines: int = 0,
                bytes_written: int = 0, method: str = "direct") -> dict:
    return {
        "success": success,
        "message": message,
        "target": target,
        "lines": lines,
        "bytes": bytes_written,
        "method": method,
    }


class TimeoutError(Exception):
    """Raised when a file operation times out."""
    pass


def _timeout_handler(signum, frame):
    raise TimeoutError("File operation timed out — possible Google Drive FileProvider deadlock.")


def _compute_checksum(file_path: str) -> str:
    """Compute SHA256 checksum of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_via_wltm(decoded_text: str, target_path: Path, write_mode: str,
                     encoding: str, timeout: int) -> dict:
    """
    Write-Local-Then-Move strategy:
    1. Write content to /tmp/antigravity_staging/{uuid}
    2. Verify the staging file
    3. Move atomically to the target path
    4. Verify the final file via checksum
    """
    # Ensure staging directory exists
    staging_dir = Path(STAGING_DIR)
    staging_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique staging file
    staging_name = f"{uuid.uuid4().hex}_{target_path.name}"
    staging_path = staging_dir / staging_name

    try:
        # ── Step 1: Handle append mode (need existing content first) ──
        if write_mode == "a" and target_path.exists():
            # For append, we need to read existing content and prepend it
            try:
                existing_content = target_path.read_text(encoding=encoding)
                full_content = existing_content + decoded_text
            except Exception as e:
                return make_result(False, f"WLTM: Cannot read existing file for append: {e}",
                                   str(target_path), method="wltm-failed")
        else:
            full_content = decoded_text

        # ── Step 2: Write to staging (local /tmp, instant) ──
        with open(staging_path, "w", encoding=encoding) as f:
            f.write(full_content)

        # ── Step 3: Verify staging file ──
        staging_content = staging_path.read_text(encoding=encoding)
        if staging_content != full_content:
            return make_result(False, "WLTM: Staging file verification failed (content mismatch).",
                               str(target_path), method="wltm-failed")

        staging_checksum = _compute_checksum(str(staging_path))

        # ── Step 4: Ensure parent directories exist ──
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # ── Step 5: Move to target with timeout protection ──
        # Cross-platform timeout: SIGALRM on Unix, threading.Timer on Windows
        _move_timed_out = False

        if hasattr(signal, 'SIGALRM'):
            # Unix: use SIGALRM (precise, reliable)
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(timeout)
            try:
                shutil.move(str(staging_path), str(target_path))
            except TimeoutError:
                _move_timed_out = True
            finally:
                signal.alarm(0)
                if old_handler is not None:
                    signal.signal(signal.SIGALRM, old_handler)
        else:
            # Windows: use threading.Timer fallback
            _timer_fired = threading.Event()

            def _timer_abort():
                _timer_fired.set()

            timer = threading.Timer(timeout, _timer_abort)
            timer.start()
            try:
                shutil.move(str(staging_path), str(target_path))
            except Exception:
                pass
            finally:
                timer.cancel()
            if _timer_fired.is_set():
                _move_timed_out = True

        if _move_timed_out:
            if staging_path.exists():
                staging_path.unlink()
            return make_result(False,
                               f"WLTM: Move operation timed out after {timeout}s. "
                               "Google Drive FileProvider may be deadlocked. "
                               "Try pausing Google Drive sync or using a local path as target.",
                               str(target_path), method="wltm-timeout")

        # ── Step 6: Verify final file via checksum ──
        try:
            final_checksum = _compute_checksum(str(target_path))
            if final_checksum != staging_checksum:
                return make_result(False,
                                   "WLTM: Post-move checksum mismatch. File may be corrupted.",
                                   str(target_path), method="wltm-failed")
        except Exception as e:
            # Checksum verification failure is non-fatal — file was moved successfully
            pass

        line_count = full_content.count("\n") + (1 if full_content and not full_content.endswith("\n") else 0)
        byte_count = len(full_content.encode(encoding))

        return make_result(True,
                           f"OK [WLTM]: {line_count} lines ({byte_count} bytes) written to {target_path}",
                           str(target_path), line_count, byte_count, method="wltm")

    except Exception as e:
        # Clean up staging file on any error
        if staging_path.exists():
            try:
                staging_path.unlink()
            except Exception:
                pass
        return make_result(False, f"WLTM error: {e}", str(target_path), method="wltm-failed")


def _write_direct(decoded_text: str, target_path: Path, write_mode: str, encoding: str) -> dict:
    """Legacy direct write (fallback when WLTM fails or is disabled)."""
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return make_result(False, f"Cannot create parent directories: {e}", method="direct")

    try:
        with open(target_path, write_mode, encoding=encoding) as f:
            f.write(decoded_text)
    except Exception as e:
        return make_result(False, f"File write error: {e}", method="direct")

    line_count = decoded_text.count("\n") + (1 if decoded_text and not decoded_text.endswith("\n") else 0)
    byte_count = len(decoded_text.encode(encoding))

    return make_result(True,
                       f"OK [Direct]: {line_count} lines ({byte_count} bytes) written to {target_path}",
                       str(target_path), line_count, byte_count, method="direct")


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="Safe File Writer — bypass IDE streaming deadlock & Google Drive FileProvider lock."
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
    parser.add_argument(
        "--no-wltm",
        action="store_true",
        help="Disable WLTM (Write-Local-Then-Move). Use legacy direct write."
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout in seconds for the move operation (default: {DEFAULT_TIMEOUT})."
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

    # ── 6. Determine write mode string ──────────────────────────────
    write_mode = "a" if args.mode == "append" else "w"

    # ── 7. Write using WLTM or Direct ───────────────────────────────
    use_wltm = not args.no_wltm

    if use_wltm:
        result = _write_via_wltm(decoded_text, target_path, write_mode, args.encoding, args.timeout)

        # If WLTM failed (but not timeout), fallback to direct write
        if not result["success"] and result["method"] == "wltm-failed":
            fallback_msg = result["message"]
            result = _write_direct(decoded_text, target_path, write_mode, args.encoding)
            if result["success"]:
                result["message"] += f" (WLTM fallback — original error: {fallback_msg})"
                result["method"] = "direct-fallback"
    else:
        result = _write_direct(decoded_text, target_path, write_mode, args.encoding)

    # ── 8. Output and exit ──────────────────────────────────────────
    print(json.dumps(result))
    sys.exit(0 if result["success"] else (5 if "timeout" in result.get("method", "") else 3))


if __name__ == "__main__":
    main()
