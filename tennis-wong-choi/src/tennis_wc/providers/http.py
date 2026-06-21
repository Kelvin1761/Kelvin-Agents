from __future__ import annotations

import gzip
import json
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Transient network failures (DNS not yet resolvable on wake, brief connectivity
# gaps) should not abort a whole daily run on the first try. Retry a few times
# with exponential backoff before giving up. HTTPError (a real server response)
# is NOT retried here — it is re-raised immediately as a RuntimeError.
_MAX_ATTEMPTS = 4
_BACKOFF_BASE_SECONDS = 1.5


def _is_transient(exc: Exception) -> bool:
    # URLError wraps socket-level failures, including the DNS error
    # "[Errno 8] nodename nor servname provided, or not known" seen when the
    # machine wakes before the network/DNS resolver is ready.
    return isinstance(exc, (URLError, socket.timeout, TimeoutError, ConnectionError))


def _urlopen_with_retry(request: Request, timeout: float, label: str) -> str:
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                return _decode_response_body(response.read(), response.headers.get("Content-Encoding"))
        except HTTPError as exc:
            body = _decode_response_body(exc.read(), exc.headers.get("Content-Encoding"))
            raise RuntimeError(f"HTTP {exc.code} from {label}: {body[:300]}") from exc
        except Exception as exc:  # noqa: BLE001 - decide retry vs propagate below
            if not _is_transient(exc) or attempt == _MAX_ATTEMPTS:
                raise
            last_exc = exc
            time.sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
    # Unreachable: loop either returns, raises HTTPError/RuntimeError, or re-raises on the
    # final attempt. Guard kept so the function always has a definite outcome.
    raise last_exc if last_exc else RuntimeError(f"Failed to fetch {label}")


def get_json(url: str, headers: dict[str, str] | None = None, params: dict | None = None, timeout: float = 20) -> dict | list:
    query = urlencode({k: v for k, v in (params or {}).items() if v is not None}, doseq=True)
    request_url = f"{url}?{query}" if query else url
    request = Request(request_url, headers=headers or {})
    return json.loads(_urlopen_with_retry(request, timeout, request_url))


def post_json(url: str, headers: dict[str, str] | None = None, body: dict | None = None) -> dict | list:
    payload = json.dumps(body or {}).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = Request(url, data=payload, headers=request_headers, method="POST")
    return json.loads(_urlopen_with_retry(request, 20, url))


def _decode_response_body(raw: bytes, content_encoding: str | None = None) -> str:
    if content_encoding and "gzip" in content_encoding.lower():
        raw = gzip.decompress(raw)
    elif raw.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(raw)
    return raw.decode("utf-8")
