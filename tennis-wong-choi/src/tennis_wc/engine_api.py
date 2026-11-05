"""Stable read-only entry points used by the rebuild replay harness."""
from __future__ import annotations

import json


def match_probabilities(conn, day: str) -> dict[str, float]:
    out = {}
    for row in conn.execute(
            "SELECT p.match_id, p.model_probability FROM predictions p JOIN matches m ON m.id = p.match_id "
            "WHERE m.match_date = ? ORDER BY p.id", (day,)):
        out[str(row[0])] = row[1]
    return out


def price_props(conn, day: str) -> list[dict]:
    from tennis_wc.model.features.common import utc_now
    from tennis_wc.pricing.props import price_date

    rows = []
    for row in price_date(conn, day, utc_now()):
        row = dict(row)
        row["pricing_evidence"] = json.loads(row.pop("pricing_evidence_json"))
        rows.append(row)
    return rows
