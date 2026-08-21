"""Manual live-bet ledger for player props.

This records a wager Kelvin already placed by hand. It has no bookmaker client
and cannot place a wager. Phase 4 can therefore use actual out-of-sample bets
instead of assuming every recommendation was acted on.
"""
from __future__ import annotations

import sqlite3

from tennis_wc.database.db import get_connection
from tennis_wc.features.common import utc_now
from tennis_wc.props.strategy import (
    LIVE_UNIT_VALUE_AUD,
    MAX_EARLY_STAKE_UNITS,
    family_for_market,
    family_may_be_staked,
)


def record_live_prop_bet(
    *,
    prop_id: int,
    odds_taken: float,
    stake_aud: float,
    placed_at: str | None = None,
    notes: str | None = None,
) -> dict:
    """Record one already-placed manual bet; never contact a bookmaker."""
    price = float(odds_taken)
    money = round(float(stake_aud), 2)
    if price <= 1.0:
        raise ValueError("odds_taken must be greater than 1.0")
    if money <= 0:
        raise ValueError("stake_aud must be positive")
    units = round(money / LIVE_UNIT_VALUE_AUD, 4)
    if units > MAX_EARLY_STAKE_UNITS:
        raise ValueError(
            f"stake {units:g}u exceeds the live EARLY_MAIN cap of "
            f"{MAX_EARLY_STAKE_UNITS:g}u "
            f"(A${MAX_EARLY_STAKE_UNITS * LIVE_UNIT_VALUE_AUD:.2f} AUD)"
        )

    with get_connection() as conn:
        prop = conn.execute(
            """
            SELECT id, match_date, market_key, selection, is_value, result_status
            FROM prop_tracker WHERE id = ?
            """,
            (int(prop_id),),
        ).fetchone()
        if prop is None:
            raise ValueError(f"prop_tracker id {prop_id} does not exist")
        family = family_for_market(str(prop["market_key"]))
        if not family_may_be_staked(family):
            raise ValueError(f"{family} is not on the live family allowlist")
        if not bool(prop["is_value"]):
            raise ValueError("the selected prop is not a value recommendation")
        if prop["result_status"] != "PENDING":
            raise ValueError("cannot record a live bet after its result is known")

        timestamp = placed_at or utc_now()
        try:
            cursor = conn.execute(
                """
                INSERT INTO prop_live_bets (
                    prop_id, odds_taken, stake_units, unit_value_aud, stake_aud,
                    currency, placed_at, notes, recorded_at
                ) VALUES (?, ?, ?, ?, ?, 'AUD', ?, ?, ?)
                """,
                (int(prop_id), price, units, LIVE_UNIT_VALUE_AUD, money,
                 timestamp, notes, utc_now()),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"prop_tracker id {prop_id} is already recorded") from exc

    return {
        "live_bet_id": int(cursor.lastrowid),
        "prop_id": int(prop_id),
        "match_date": prop["match_date"],
        "family": family,
        "selection": prop["selection"],
        "odds_taken": price,
        "stake_units": units,
        "stake_aud": money,
        "currency": "AUD",
        "placed_at": timestamp,
        "wager_placed_by_software": False,
        "message": "recorded only; this command did not place a wager",
    }
