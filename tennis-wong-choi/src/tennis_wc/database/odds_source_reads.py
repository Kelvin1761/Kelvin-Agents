"""Check retained event receipts without changing their historical contents."""
from __future__ import annotations

import json

from tennis_wc.database.payload_archive import PayloadArchiveError, read_payload
from tennis_wc.event_source_identity import direct_event_response_issue, sportsbet_url_event_id


MAX_EVENT_BODY_BYTES = 8 * 1024 * 1024
EVENT_ENDPOINTS = {"/event-odds", "/event-odds-preclose"}


class OddsSourceReader:
    """Classify a receipt once per connection; a matched ID is not PIT proof."""

    def __init__(self, conn):
        self.conn = conn
        self.cache = {}

    def assess(self, raw_id):
        if raw_id in self.cache:
            return self.cache[raw_id]
        row = self.conn.execute(
            """SELECT provider_name,endpoint,request_params_json,response_json,
                      length(CAST(response_json AS BLOB)) AS body_bytes
               FROM raw_api_responses WHERE id=?""", (raw_id,)
        ).fetchone()
        if row is None:
            result = ("unverified_missing_receipt", False)
        elif row["provider_name"] != "sportsbet" or row["endpoint"] not in EVENT_ENDPOINTS:
            result = ("outside_direct_event_scope", False)
        else:
            try:
                request = json.loads(row["request_params_json"])
                if not isinstance(request, dict) or not request.get("event_id"):
                    raise ValueError("missing request event")
            except (TypeError, ValueError):
                result = ("unverified_request", True)
            else:
                event_ref = request["event_id"]
                if sportsbet_url_event_id(row["provider_name"], event_ref) is None:
                    result = ("unverified_reference_namespace", False)
                elif row["body_bytes"] is None or row["body_bytes"] > MAX_EVENT_BODY_BYTES:
                    result = ("unverified_response_size", True)
                else:
                    try:
                        body = read_payload(self.conn, "raw_response", raw_id, row["response_json"],
                                            max_bytes=MAX_EVENT_BODY_BYTES)
                        if len(body.encode("utf-8")) > MAX_EVENT_BODY_BYTES:
                            raise ValueError("response exceeds byte budget")
                        payload = json.loads(body)
                        if not isinstance(payload, dict) or not payload.get("event_id"):
                            raise ValueError("response is missing an event ID")
                        issue = direct_event_response_issue(row["provider_name"], event_ref, payload)
                        result = ("wrong_event" if issue else "matched_event_id", bool(issue))
                    except (PayloadArchiveError, TypeError, ValueError):
                        result = ("unverified_response", True)
        self.cache[raw_id] = result
        return result
