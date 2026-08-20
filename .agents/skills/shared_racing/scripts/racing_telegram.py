#!/usr/bin/env python3
"""Reliable, best-effort Telegram notifications for racing automation.

Analysis jobs must never be marked successful merely because notification was
attempted.  This module returns a structured result so schedulers can expose a
Telegram failure in their run log without hiding an otherwise valid analysis.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
ENV_FILE = PROJECT_ROOT / ".agents" / ".env"
MAX_TELEGRAM_TEXT = 4096


def load_env(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
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


def send_message(message: str, *, dry_run: bool = False, timeout: float = 10.0) -> dict:
    parts = _chunks(message)
    if not parts:
        return {"ok": False, "status": "empty_message", "sent_parts": 0}
    if dry_run:
        return {"ok": True, "status": "dry_run", "sent_parts": len(parts), "parts": parts}
    if os.environ.get("WC_TELEGRAM_DISABLE", "").strip().lower() in {"1", "true", "yes"}:
        return {"ok": True, "status": "disabled", "sent_parts": 0}

    token, chat_id = telegram_credentials()
    if not token or not chat_id or token == "YOUR_BOT_TOKEN":
        return {"ok": False, "status": "not_configured", "sent_parts": 0}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    sent = 0
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
            return {
                "ok": False,
                "status": "request_failed",
                "sent_parts": sent,
                "error": f"{type(exc).__name__}: {exc}",
            }
        if not body.get("ok"):
            return {
                "ok": False,
                "status": "telegram_rejected",
                "sent_parts": sent,
                "error": str(body.get("description") or "unknown Telegram API error"),
            }
        sent += 1
    return {"ok": True, "status": "sent", "sent_parts": sent}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send a Wong Choi Telegram status message")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--message")
    group.add_argument("--message-file", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    message = args.message
    if args.message_file:
        message = args.message_file.read_text(encoding="utf-8")
    result = send_message(message or "", dry_run=args.dry_run)
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Telegram: {result['status']} ({result.get('sent_parts', 0)} part(s))")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
