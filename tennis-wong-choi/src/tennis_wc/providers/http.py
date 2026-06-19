from __future__ import annotations

import gzip
import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def get_json(url: str, headers: dict[str, str] | None = None, params: dict | None = None) -> dict | list:
    query = urlencode({k: v for k, v in (params or {}).items() if v is not None}, doseq=True)
    request_url = f"{url}?{query}" if query else url
    request = Request(request_url, headers=headers or {})
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(_decode_response_body(response.read(), response.headers.get("Content-Encoding")))
    except HTTPError as exc:
        body = _decode_response_body(exc.read(), exc.headers.get("Content-Encoding"))
        raise RuntimeError(f"HTTP {exc.code} from {request_url}: {body[:300]}") from exc


def post_json(url: str, headers: dict[str, str] | None = None, body: dict | None = None) -> dict | list:
    payload = json.dumps(body or {}).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = Request(url, data=payload, headers=request_headers, method="POST")
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(_decode_response_body(response.read(), response.headers.get("Content-Encoding")))
    except HTTPError as exc:
        error_body = _decode_response_body(exc.read(), exc.headers.get("Content-Encoding"))
        raise RuntimeError(f"HTTP {exc.code} from {url}: {error_body[:300]}") from exc


def _decode_response_body(raw: bytes, content_encoding: str | None = None) -> str:
    if content_encoding and "gzip" in content_encoding.lower():
        raw = gzip.decompress(raw)
    elif raw.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(raw)
    return raw.decode("utf-8")
