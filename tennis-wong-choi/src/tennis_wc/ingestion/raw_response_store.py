from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from tennis_wc.database.db import get_connection


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash_request(endpoint: str, request_params: dict) -> str:
    payload = json.dumps({"endpoint": endpoint, "params": request_params}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def store_raw_response(
    provider_name: str,
    endpoint: str,
    request_params: dict,
    response_json: dict | list,
    status_code: int,
    entity_type: str | None = None,
    entity_external_id: str | None = None,
) -> int:
    """
    Store raw API response and return raw_response_id.
    """
    now = utc_now()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO raw_api_responses (
                provider_name, endpoint, request_url_hash, request_params_json,
                response_json, status_code, fetched_at, entity_type,
                entity_external_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provider_name,
                endpoint,
                _hash_request(endpoint, request_params),
                json.dumps(request_params, sort_keys=True),
                json.dumps(response_json, sort_keys=True),
                status_code,
                now,
                entity_type,
                entity_external_id,
                now,
            ),
        )
        return int(cursor.lastrowid)
