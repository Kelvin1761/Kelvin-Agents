"""Which market quotes are current: the latest capture batch per match and book."""
from __future__ import annotations


def current_market_clause(alias: str = "mo", table: str = "market_odds_snapshots") -> str:
    """Rows from the newest capture batch of an ACTIVE fixture.

    ``market_captures`` records each event-page fetch, including fetches where a
    market disappeared, so an old quote never outlives a newer empty capture.
    """
    match = (f"x.match_id={alias}.match_id AND x.source_provider={alias}.source_provider"
             f" AND lower(trim(x.bookmaker))=lower(trim({alias}.bookmaker))")
    legacy = f"(SELECT x.raw_response_id FROM {table} x WHERE {match} ORDER BY x.id DESC LIMIT 1)"
    receipt_table = "market_odds_snapshots" if table == "odds_snapshots" else table
    capture = (f"(SELECT x.raw_response_id FROM market_captures x WHERE {match}"
               f" AND x.target_table='{receipt_table}' ORDER BY x.id DESC LIMIT 1)")
    return (f"{alias}.raw_response_id=COALESCE({capture},{legacy})"
            f" AND EXISTS(SELECT 1 FROM matches current_m WHERE current_m.id={alias}.match_id"
            f" AND current_m.fixture_status='ACTIVE')")
