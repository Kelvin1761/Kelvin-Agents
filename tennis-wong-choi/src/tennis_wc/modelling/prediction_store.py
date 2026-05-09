from __future__ import annotations

import json

from tennis_wc.database.db import get_connection
from tennis_wc.features.common import utc_now


def store_prediction(match_id: int, feature_set_version: str, pricing: dict, filter_result: dict) -> int:
    now = utc_now()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO predictions (
                match_id, feature_set_version, selection_player_id, selection_name,
                model_probability, fair_odds, current_market_odds,
                market_implied_probability, no_vig_market_probability, edge,
                minimum_acceptable_odds, decision, stake_units, confidence, risk,
                pricing_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                match_id,
                feature_set_version,
                pricing.get("selection_player_id"),
                pricing.get("selection_name"),
                pricing.get("model_probability"),
                pricing.get("fair_odds"),
                pricing.get("current_market_odds"),
                pricing.get("market_implied_probability"),
                pricing.get("no_vig_market_probability"),
                pricing.get("edge"),
                pricing.get("minimum_acceptable_odds"),
                filter_result["decision"],
                filter_result["stake_units"],
                filter_result["confidence"],
                filter_result["risk"],
                json.dumps({"pricing": pricing, "filter": filter_result}, sort_keys=True),
                now,
            ),
        )
        return int(cursor.lastrowid)
