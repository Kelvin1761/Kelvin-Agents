from __future__ import annotations

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
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"HTTP {exc.code} from {request_url}: {body[:300]}") from exc


def post_json(url: str, headers: dict[str, str] | None = None, body: dict | None = None) -> dict | list:
    payload = json.dumps(body or {}).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = Request(url, data=payload, headers=request_headers, method="POST")
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {error_body[:300]}") from exc
