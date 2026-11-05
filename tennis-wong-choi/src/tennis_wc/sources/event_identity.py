"""Compare event identities only where the source URL defines a direct ID."""
from __future__ import annotations

import re
from urllib.parse import urlparse


def sportsbet_url_event_id(provider_name: str, event_ref: str | None) -> str | None:
    if provider_name != "sportsbet":
        return None
    parsed = urlparse(str(event_ref or ""))
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"sportsbet.com.au", "www.sportsbet.com.au"}:
        return None
    match = re.search(r"-(\d+)$", parsed.path.rstrip("/"))
    return match.group(1) if match else None


def direct_event_response_issue(provider_name: str, event_ref: str | None, row) -> str | None:
    requested = sportsbet_url_event_id(provider_name, event_ref)
    if requested is None:
        return None
    received = str(row.get("event_id") or "").strip() if isinstance(row, dict) else ""
    if received != requested:
        return f"sportsbet_event_response_mismatch: requested={requested} received={received or 'missing'}"
    return None
