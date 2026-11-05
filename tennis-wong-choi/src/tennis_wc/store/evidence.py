"""Pricing evidence frozen onto every prop_tracker row (``pricing_evidence_json``).

The context is captured once per match before pricing and frozen per row at
write time, so a row always records what was known when its price was made.
"""
from __future__ import annotations

import json
import math


def capture_context(conn, match_id: int, priced_at: str, quotes=()) -> dict:
    """Fixture, latest feature snapshot per player and the quotes priced from."""
    match = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
    features = [dict(r) for r in conn.execute("""
        SELECT fs.id, fs.player_id, fs.data_quality_score, fs.created_at
        FROM feature_snapshots fs WHERE fs.match_id=? AND fs.id=(
            SELECT MAX(x.id) FROM feature_snapshots x
            WHERE x.match_id=fs.match_id AND x.player_id=fs.player_id)
        ORDER BY fs.player_id""", (match_id,))]
    scores = [f["data_quality_score"] for f in features if f["data_quality_score"] is not None]
    return {"version": 1, "priced_at": priced_at, "fixture": dict(match) if match else None,
            "features": features, "data_quality_score": min(scores) if scores else None,
            "profiles": {}, "_quotes": [dict(r) for r in quotes]}


def source_quality(evidence: dict | None) -> float | None:
    """The match's feature data quality on a 0-1 scale (None if unknown)."""
    if not evidence:
        return None
    quality = evidence.get("data_quality_score")
    if quality is None:
        return None
    quality = float(quality)
    if quality > 1:
        quality /= 100
    return min(1.0, max(0.0, quality)) if math.isfinite(quality) else None


def freeze_context(context: dict, feed_key, feed_name, feed_selection, feed_line) -> str:
    """The JSON stored on one row: context minus private keys, plus the quote it used."""
    evidence = {k: v for k, v in context.items() if not k.startswith("_")}
    evidence["source_quality"] = source_quality(context)
    candidates = []
    if feed_key and feed_name and feed_selection:
        for quote in context.get("_quotes", []):
            if (quote["market_key"] == feed_key and quote["market_name"] == feed_name
                    and quote["selection_name"] == feed_selection and quote["line"] == feed_line):
                candidates.append(quote)
    evidence["quote"] = candidates[0] if len(candidates) == 1 else None
    evidence["quote_status"] = "OBSERVED" if evidence["quote"] else "UNVERIFIED"
    return json.dumps(evidence, sort_keys=True, allow_nan=False)


def read_evidence(value) -> dict | None:
    if not value:
        return None
    try:
        evidence = json.loads(value)
    except (ValueError, TypeError):
        return None
    return evidence if isinstance(evidence, dict) and evidence.get("version") == 1 else None
