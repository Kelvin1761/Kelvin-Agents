"""Match-win predictions. Props read P(player A wins) from the latest row per match.

The match model no longer produces bets of its own, so decision is always
MODEL and stake 0; the columns stay for older rows.
"""
from __future__ import annotations

import json

from tennis_wc.store.db import get_connection
from tennis_wc.model.features.common import utc_now


def store_prediction(match_id: int, feature_set_version: str, pricing: dict) -> int:
    with get_connection() as conn:
        fixture = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
        if fixture is None:
            raise ValueError(f"Match not found: {match_id}")
        fixture = dict(fixture)
        if fixture.get("fixture_status", "ACTIVE") != "ACTIVE":
            raise ValueError(f"Inactive fixture identity: {match_id}")
        if pricing.get("selection_player_id") not in (None, fixture["player_a_id"], fixture["player_b_id"]):
            raise ValueError(f"Forecast player outside fixture identity: {match_id}")
        evidence = {k: fixture.get(k) for k in
                    ("id", "player_a_id", "player_b_id", "match_date", "start_time_utc", "fixture_status")}
        cursor = conn.execute("""
            INSERT INTO predictions (
                match_id, feature_set_version, selection_player_id, selection_name,
                model_probability, fair_odds, current_market_odds,
                market_implied_probability, no_vig_market_probability, edge,
                minimum_acceptable_odds, decision, stake_units, confidence, risk,
                pricing_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'MODEL', 0, 0, ?, ?, ?)""", (
            match_id, feature_set_version, pricing.get("selection_player_id"), pricing.get("selection_name"),
            pricing.get("model_probability"), pricing.get("fair_odds"), pricing.get("current_market_odds"),
            pricing.get("market_implied_probability"), pricing.get("no_vig_market_probability"),
            pricing.get("edge"), pricing.get("minimum_acceptable_odds"),
            pricing.get("segment_risk_label") or "",
            json.dumps({"pricing": pricing, "fixture_at_prediction": evidence}, sort_keys=True), utc_now()))
        return int(cursor.lastrowid)
