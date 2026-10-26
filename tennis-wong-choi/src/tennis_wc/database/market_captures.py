"""Current quotes come from one observed batch, never a union of old lines."""
from __future__ import annotations


def ensure_market_captures(conn) -> None:
    conn.execute('''CREATE TABLE IF NOT EXISTS market_captures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,match_id INTEGER NOT NULL,event_id TEXT NOT NULL,
        source_provider TEXT NOT NULL,bookmaker TEXT NOT NULL,raw_response_id INTEGER NOT NULL,
        target_table TEXT NOT NULL,captured_at TEXT NOT NULL,
        UNIQUE(match_id,source_provider,bookmaker,raw_response_id,target_table))''')
    conn.execute('''CREATE INDEX IF NOT EXISTS idx_market_captures_current
        ON market_captures(match_id,source_provider,bookmaker,target_table,id)''')


def record_market_capture(conn,match_id,row,provider,raw_id,now,table):
    if match_id is None:
        return
    ensure_market_captures(conn)
    conn.execute('''INSERT OR IGNORE INTO market_captures
        (match_id,event_id,source_provider,bookmaker,raw_response_id,target_table,captured_at)
        VALUES (?,?,?,?,?,?,?)''',(match_id,str(row['event_id']),provider,
        str(row.get('bookmaker') or provider).strip().lower(),raw_id,table,now))


def current_market_clause(conn,alias='mo',table='market_odds_snapshots') -> str:
    """Missing quotes in the latest capture are unverified, not still offered.

    Legacy rows have no batch receipt; their latest raw response is the only
    coherent fallback. This does not invent proof of completeness/availability.
    Preclose receipts never replace the live board.
    """
    match=(f'x.match_id={alias}.match_id AND x.source_provider={alias}.source_provider '
           f'AND lower(trim(x.bookmaker))=lower(trim({alias}.bookmaker))')
    legacy=f'(SELECT x.raw_response_id FROM {table} x WHERE {match} ORDER BY x.id DESC LIMIT 1)'
    exists=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='market_captures'").fetchone()
    if exists:
        receipt_table='market_odds_snapshots' if table=='odds_snapshots' else table
        capture=(f"(SELECT x.raw_response_id FROM market_captures x WHERE {match} "
                 f"AND x.target_table='{receipt_table}' ORDER BY x.id DESC LIMIT 1)")
        batch=f'COALESCE({capture},{legacy})'
    else:
        batch=legacy
    clause=f'{alias}.raw_response_id={batch}'
    columns={r['name'] for r in conn.execute('PRAGMA table_info(matches)')}
    if 'fixture_status' in columns:
        clause+=(f" AND EXISTS(SELECT 1 FROM matches current_m WHERE current_m.id={alias}.match_id "
                 "AND current_m.fixture_status='ACTIVE')")
    return clause


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
