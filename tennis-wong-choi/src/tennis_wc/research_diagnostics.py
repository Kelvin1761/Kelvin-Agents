"""Bounded, diagnostic-only journal for a rejected research projection.

This is never a feature-evidence artifact or a qualification decision. Preserve
the exact supplied observations, including warnings and invalid/missing fields;
do not reconstruct them from a later database state.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from typing import Mapping, Sequence


SCHEMA = "wong-choi-tennis-research-diagnostics/v1"
MAX_UNCOMPRESSED_BYTES = 128 * 1024**2
MAX_COMPRESSED_BYTES = 16 * 1024**2


def build_research_diagnostics(
    *, event_id: str, captured_at: datetime, predictions: Sequence[dict],
    observations: Sequence[dict], raw_responses: Mapping[int, dict], reason: str,
) -> tuple[dict[str, bytes], dict]:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", event_id):
        raise ValueError("canonical Tennis diagnostic event date required")
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("diagnostic capture needs an aware timestamp")
    expected = [row.get("id") for row in predictions]
    observed = [row.get("prediction_id") for row in observations]
    coverage = (
        bool(expected)
        and all(type(i) is int and i > 0 for i in expected + observed)
        and len(set(expected)) == len(expected)
        and len(set(observed)) == len(observed)
        and sorted(expected) == sorted(observed)
    )
    # raw_responses comes only from the read-only six-column response query.
    # Never copy request headers, settings, environment, or API credentials.
    raw_fields = ("id", "provider_name", "endpoint", "response_json", "fetched_at", "created_at")
    raw_rows = [{k: row[k] for k in raw_fields if k in row}
                for _, row in sorted(raw_responses.items())]
    payload = {
        "schema_version": SCHEMA, "event_id": event_id,
        "generated_at": captured_at.astimezone(timezone.utc).isoformat(),
        "qualification": "DIAGNOSTIC_ONLY_UNVERIFIED",
        "feature_availability_verified": False, "model_promotion_allowed": False,
        "projection_failure": reason, "expected_prediction_ids": expected,
        "observation_coverage_complete": coverage, "observations": list(observations),
        "raw_responses": raw_rows,
        "raw_capture": "supplied_rows_only; absent references are not fabricated",
    }
    stream, uncompressed = io.BytesIO(), 0
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))
    with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0, filename="") as compressed:
        for part in encoder.iterencode(payload):
            block = part.encode("utf-8")
            uncompressed += len(block)
            if uncompressed > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("Tennis diagnostic uncompressed byte budget exceeded")
            compressed.write(block)
            if stream.tell() > MAX_COMPRESSED_BYTES:
                raise ValueError("Tennis diagnostic compressed byte budget exceeded")
    raw = stream.getvalue()
    if len(raw) > MAX_COMPRESSED_BYTES:
        raise ValueError("Tennis diagnostic compressed byte budget exceeded")
    name = f"Tennis_Research_Diagnostics_{event_id}.json.gz"
    return {name: raw}, {
        "status": "captured", "artifact_name": name,
        "sha256": hashlib.sha256(raw).hexdigest(), "compressed_bytes": len(raw),
        "uncompressed_bytes": uncompressed, "observations": len(observations),
        "expected_predictions": len(predictions), "observation_coverage_complete": coverage,
        "raw_responses": len(raw_rows), "feature_availability_verified": False,
        "model_promotion_allowed": False,
    }
