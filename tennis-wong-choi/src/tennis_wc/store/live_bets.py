"""Manual live-bet ledger: records a wager Kelvin already placed by hand.

No bookmaker client; it cannot place a wager. Only 精選 picks can be recorded,
at most 0.5 unit (A$0.50) while the forward test is unproven (EXP-20261105-10).
"""
from __future__ import annotations

import sqlite3

from tennis_wc.database.db import get_connection
from tennis_wc.features.common import utc_now
from tennis_wc.pricing.families import family_for_market

LIVE_UNIT_VALUE_AUD = 1.0
MAX_EARLY_STAKE_UNITS = 0.5


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
        if not conn.execute("SELECT 1 FROM featured_picks WHERE prop_id = ?", (int(prop_id),)).fetchone():
            raise ValueError("only 精選 picks can be recorded as live bets")
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
