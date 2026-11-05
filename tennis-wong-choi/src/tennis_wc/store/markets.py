"""Market captures: which quotes are current, and the capture receipts that decide it."""
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


def ensure_market_captures(conn) -> None:
    conn.execute('''CREATE TABLE IF NOT EXISTS market_captures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,match_id INTEGER NOT NULL,event_id TEXT NOT NULL,
        source_provider TEXT NOT NULL,bookmaker TEXT NOT NULL,raw_response_id INTEGER NOT NULL,
        target_table TEXT NOT NULL,captured_at TEXT NOT NULL,listed INTEGER NOT NULL DEFAULT 1,
        UNIQUE(match_id,source_provider,bookmaker,raw_response_id,target_table))''')
    if 'listed' not in {r['name'] for r in conn.execute('PRAGMA table_info(market_captures)')}:
        conn.execute('ALTER TABLE market_captures ADD COLUMN listed INTEGER NOT NULL DEFAULT 1')
    conn.execute('''CREATE INDEX IF NOT EXISTS idx_market_captures_current
        ON market_captures(match_id,source_provider,bookmaker,target_table,id)''')


def record_market_capture(conn,match_id,row,provider,raw_id,now,table):
    if match_id is None:
        return
    ensure_market_captures(conn)
    conn.execute('''INSERT OR IGNORE INTO market_captures
        (match_id,event_id,source_provider,bookmaker,raw_response_id,target_table,captured_at,listed)
        VALUES (?,?,?,?,?,?,?,?)''',(match_id,str(row['event_id']),provider,
        str(row.get('bookmaker') or provider).strip().lower(),raw_id,table,now,int(row.get('listed',True))))


def bookmaker_event_for_match(conn, match_id: int, provider: str) -> str | None:
    """Resolve a provider's own event ID; fixture IDs belong to another feed."""
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='market_captures'").fetchone():
        row = conn.execute('''SELECT event_id FROM market_captures
            WHERE match_id=? AND source_provider=? AND target_table='market_odds_snapshots'
            ORDER BY id DESC LIMIT 1''', (match_id, provider)).fetchone()
        if row:
            return str(row['event_id'])
    row = conn.execute('''SELECT event_id FROM (
        SELECT event_id,raw_response_id,fetched_at,id FROM odds_snapshots
        WHERE match_id=? AND source_provider=?
        UNION ALL
        SELECT event_id,raw_response_id,fetched_at,id FROM market_odds_snapshots
        WHERE match_id=? AND source_provider=?)
        ORDER BY raw_response_id DESC,fetched_at DESC,id DESC LIMIT 1''',
        (match_id, provider, match_id, provider)).fetchone()
    if row:
        return str(row['event_id'])
    match = conn.execute('SELECT market_event_id,source_provider FROM matches WHERE id=?',
                         (match_id,)).fetchone()
    if match and match['source_provider'] == provider and match['market_event_id']:
        return str(match['market_event_id'])
    return None


def book_listing_clause(alias: str = "m", provider: str = "sportsbet") -> str:
    """The latest capture for the fixture still lists it (an empty listing de-lists it)."""
    return (f"COALESCE((SELECT cap.listed FROM market_captures cap WHERE cap.match_id={alias}.id "
            f"AND cap.source_provider='{provider}' AND cap.target_table='market_odds_snapshots' "
            f"ORDER BY cap.id DESC LIMIT 1),1)=1")
