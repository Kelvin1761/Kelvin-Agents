#!/usr/bin/env python3
"""Reliable, best-effort Telegram notifications for racing automation.

Analysis jobs must never be marked successful merely because notification was
attempted.  This module returns a structured result so schedulers can expose a
Telegram failure in their run log without hiding an otherwise valid analysis.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
ENV_FILE = PROJECT_ROOT / ".agents" / ".env"
USER_NOTIFY_ENV = Path.home() / ".wongchoi_notify.env"
MAX_TELEGRAM_TEXT = 4096
MAX_TELEGRAM_DOCUMENT = 50 * 1024 * 1024


def load_env(path: Path | None = None) -> None:
    """Load repo and shared scheduler credentials without overwriting env vars."""
    paths = (Path(path),) if path is not None else (ENV_FILE, USER_NOTIFY_ENV)
    for candidate in paths:
        if not candidate.exists():
            continue
        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key.startswith("export "):
                key = key[7:].strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


def _chunks(text: str, limit: int = MAX_TELEGRAM_TEXT) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit + 1)
        if cut < limit // 2:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks


def telegram_credentials() -> tuple[str, str]:
    """Resolve the shared bot, including AU automation's existing env names."""
    load_env()
    token = (
        os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        or os.environ.get("WC_NOTIFY_TELEGRAM_TOKEN", "").strip()
    )
    chat_id = (
        os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        or os.environ.get("WC_NOTIFY_TELEGRAM_CHAT", "").strip()
    )
    return token, chat_id


def telegram_targets(audience: str = "primary") -> list[str]:
    """Resolve recipients without widening operational alerts to extra readers."""
    _, primary = telegram_credentials()
    targets = [primary] if primary else []
    if audience == "content":
        extra = os.environ.get("WC_NOTIFY_TELEGRAM_EXTRA", "")
        for chat_id in extra.replace(";", ",").split(","):
            chat_id = chat_id.strip()
            if chat_id and chat_id not in targets:
                targets.append(chat_id)
    return targets


def send_message(
    message: str,
    *,
    audience: str = "primary",
    dry_run: bool = False,
    timeout: float = 10.0,
) -> dict:
    parts = _chunks(message)
    if not parts:
        return {"ok": False, "status": "empty_message", "sent_parts": 0}
    if dry_run:
        return {"ok": True, "status": "dry_run", "sent_parts": len(parts), "parts": parts}
    if os.environ.get("WC_TELEGRAM_DISABLE", "").strip().lower() in {"1", "true", "yes"}:
        return {"ok": True, "status": "disabled", "sent_parts": 0}

    token, _ = telegram_credentials()
    targets = telegram_targets(audience)
    if not token or not targets or token == "YOUR_BOT_TOKEN":
        return {"ok": False, "status": "not_configured", "sent_parts": 0}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    sent = 0
    failures: list[str] = []
    sent_targets = 0
    for chat_id in targets:
        target_ok = True
        for part in parts:
            payload = json.dumps({"chat_id": chat_id, "text": part}, ensure_ascii=False).encode("utf-8")
            request = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    body = json.loads(response.read().decode("utf-8"))
            except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
                failures.append(f"{type(exc).__name__}: {exc}")
                target_ok = False
                break
            if not body.get("ok"):
                failures.append(str(body.get("description") or "unknown Telegram API error"))
                target_ok = False
                break
            sent += 1
        if target_ok:
            sent_targets += 1
    if failures:
        return {
            "ok": False,
            "status": "partial_failure" if sent_targets else "request_failed",
            "sent_parts": sent,
            "sent_targets": sent_targets,
            "failed_targets": len(failures),
            "error": failures[0],
        }
    return {
        "ok": True,
        "status": "sent",
        "sent_parts": sent,
        "sent_targets": sent_targets,
    }


def _multipart_document(
    chat_id: str,
    document: Path,
    caption: str,
) -> tuple[bytes, str]:
    """Build Telegram's multipart payload without adding a third-party dependency."""
    boundary = f"----WongChoi{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(document.name)[0] or "application/octet-stream"
    fields = {"chat_id": chat_id}
    if caption.strip():
        fields["caption"] = caption.strip()[:1024]
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        )
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        (
            'Content-Disposition: form-data; name="document"; '
            f'filename="{document.name}"\r\n'
        ).encode("utf-8")
    )
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
    body.extend(document.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def send_document(
    document: Path,
    *,
    caption: str = "",
    audience: str = "primary",
    dry_run: bool = False,
    timeout: float = 30.0,
) -> dict:
    """Send one locally generated report to Telegram recipients.

    Monthly governance reports default to the primary owner.  Passing
    ``audience='content'`` retains the established primary + extra-recipient
    behaviour used for race-day analysis.
    """
    document = Path(document)
    try:
        size = document.stat().st_size
    except OSError as exc:
        return {"ok": False, "status": "missing_document", "error": str(exc)}
    if not document.is_file() or size <= 0:
        return {"ok": False, "status": "empty_document", "size": size}
    if size > MAX_TELEGRAM_DOCUMENT:
        return {"ok": False, "status": "document_too_large", "size": size}
    if dry_run:
        return {
            "ok": True,
            "status": "dry_run",
            "document": str(document),
            "size": size,
            "caption": caption.strip()[:1024],
        }
    if os.environ.get("WC_TELEGRAM_DISABLE", "").strip().lower() in {"1", "true", "yes"}:
        return {"ok": True, "status": "disabled", "sent_targets": 0}

    token, _ = telegram_credentials()
    targets = telegram_targets(audience)
    if not token or not targets or token == "YOUR_BOT_TOKEN":
        return {"ok": False, "status": "not_configured", "sent_targets": 0}

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    sent_targets = 0
    failures: list[str] = []
    for chat_id in targets:
        try:
            payload, content_type = _multipart_document(chat_id, document, caption)
            request = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": content_type},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            failures.append(f"{type(exc).__name__}: {exc}")
            continue
        if not body.get("ok"):
            failures.append(str(body.get("description") or "unknown Telegram API error"))
            continue
        sent_targets += 1
    if failures:
        return {
            "ok": False,
            "status": "partial_failure" if sent_targets else "request_failed",
            "sent_targets": sent_targets,
            "failed_targets": len(failures),
            "error": failures[0],
        }
    return {"ok": True, "status": "sent", "sent_targets": sent_targets}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send a Wong Choi Telegram status message")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--message")
    group.add_argument("--message-file", type=Path)
    group.add_argument("--document", type=Path)
    parser.add_argument("--caption", default="")
    parser.add_argument("--audience", choices=("primary", "content"), default="primary")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    if args.document:
        result = send_document(
            args.document,
            caption=args.caption,
            audience=args.audience,
            dry_run=args.dry_run,
        )
    else:
        message = args.message
        if args.message_file:
            message = args.message_file.read_text(encoding="utf-8")
        result = send_message(
            message or "", audience=args.audience, dry_run=args.dry_run
        )
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        count = result.get("sent_parts", result.get("sent_targets", 0))
        print(f"Telegram: {result['status']} ({count} sent)")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
