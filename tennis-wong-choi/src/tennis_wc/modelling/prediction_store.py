from __future__ import annotations

import json

from tennis_wc.database.db import get_connection
from tennis_wc.features.common import utc_now


def store_prediction(match_id: int, feature_set_version: str, pricing: dict, filter_result: dict) -> int:
    now = utc_now()
    with get_connection() as conn:
        fixture=conn.execute('SELECT * FROM matches WHERE id=?',(match_id,)).fetchone()
        if fixture is None:
            raise ValueError(f'Match not found: {match_id}')
        fixture=dict(fixture)
        if fixture.get('fixture_status','ACTIVE')!='ACTIVE':
            raise ValueError(f'Inactive fixture identity: {match_id}')
        if pricing.get('selection_player_id') not in (None,fixture['player_a_id'],fixture['player_b_id']):
            raise ValueError(f'Forecast player outside fixture identity: {match_id}')
        evidence={k:fixture.get(k) for k in ('id','player_a_id','player_b_id','match_date','start_time_utc','fixture_status')}
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
                json.dumps({"pricing": pricing, "filter": filter_result,"fixture_at_prediction":evidence}, sort_keys=True),
                now,
            ),
        )
        return int(cursor.lastrowid)
