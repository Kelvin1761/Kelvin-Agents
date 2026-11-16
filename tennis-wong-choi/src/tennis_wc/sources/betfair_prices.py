"""Betfair Exchange tennis MATCH_ODDS capture (read-only; EXP-20261116-23).

Reuses the AU read-only client (`.agents/skills/au_racing/au_betfair/betfair_client.py`),
whose credentials live outside the repo in ``~/.wongchoi_betfair.env``. The client
refuses every method that is not a market read, so nothing here can place a bet.

Storage is deduplicated: a market's prices get a new row only when they change;
otherwise the latest row's ``last_seen_at`` moves forward. A price "at time T"
is the newest row with ``fetched_at <= T`` whose ``last_seen_at`` is near T.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CLIENT_DIR = Path(__file__).resolve().parents[4] / ".agents" / "skills" / "au_racing" / "au_betfair"
ENV_FILE = Path(os.environ.get("BETFAIR_ENV_FILE") or (Path.home() / ".wongchoi_betfair.env"))
WINDOW_HOURS = 36
BOOK_CHUNK = 40  # EX_BEST_OFFERS weight 5 per market; 200 per request

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS betfair_markets (
        market_id TEXT PRIMARY KEY,
        event_name TEXT,
        competition TEXT,
        market_start_utc TEXT NOT NULL,
        runner_a TEXT NOT NULL,
        runner_b TEXT NOT NULL,
        selection_a INTEGER NOT NULL,
        selection_b INTEGER NOT NULL,
        first_seen_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS betfair_price_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        market_id TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        status TEXT,
        in_play INTEGER,
        a_back REAL, a_lay REAL, b_back REAL, b_lay REAL,
        a_ltp REAL, b_ltp REAL,
        delayed INTEGER
    )""",
    "CREATE INDEX IF NOT EXISTS idx_bf_snap_market ON betfair_price_snapshots(market_id, fetched_at)",
)
PRICE_COLS = ("status", "in_play", "a_back", "a_lay", "b_back", "b_lay", "a_ltp", "b_ltp")


def ensure_schema(conn) -> None:
    for sql in SCHEMA:
        conn.execute(sql)


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_env(path: Path = ENV_FILE) -> None:
    """Put the Betfair env file into os.environ without overriding what is set."""
    if os.environ.get("BETFAIR_APP_KEY") or not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip().removeprefix("export ").strip(), value.strip().strip("'\""))


def client_rpc():
    load_env()
    if str(CLIENT_DIR) not in sys.path:
        sys.path.insert(0, str(CLIENT_DIR))
    import betfair_client  # noqa: PLC0415

    return betfair_client.rpc


def is_singles(market: dict) -> bool:
    runners = market.get("runners") or []
    return len(runners) == 2 and not any("/" in str(r.get("runnerName", "")) for r in runners)


def catalogue(now: datetime, rpc) -> list[dict]:
    flt = {"eventTypeIds": ["2"], "marketTypeCodes": ["MATCH_ODDS"],
           "marketStartTime": {"from": iso(now - timedelta(hours=1)),
                               "to": iso(now + timedelta(hours=WINDOW_HOURS))}}
    out = rpc("listMarketCatalogue", {
        "filter": flt, "maxResults": "1000",
        "marketProjection": ["COMPETITION", "EVENT", "RUNNER_DESCRIPTION", "MARKET_START_TIME"]})
    return [m for m in (out or []) if is_singles(m)]


def _best(ladder: list | None) -> float | None:
    return float(ladder[0]["price"]) if ladder else None


def price_row(book: dict, market: dict) -> dict | None:
    order = sorted(market["runners"], key=lambda r: r.get("sortPriority", 0))
    by_sel = {r["selectionId"]: r for r in book.get("runners") or []}
    a, b = by_sel.get(order[0]["selectionId"]), by_sel.get(order[1]["selectionId"])
    if a is None or b is None:
        return None
    ex_a, ex_b = a.get("ex") or {}, b.get("ex") or {}
    return {
        "status": book.get("status"), "in_play": int(bool(book.get("inplay"))),
        "a_back": _best(ex_a.get("availableToBack")), "a_lay": _best(ex_a.get("availableToLay")),
        "b_back": _best(ex_b.get("availableToBack")), "b_lay": _best(ex_b.get("availableToLay")),
        "a_ltp": a.get("lastPriceTraded"), "b_ltp": b.get("lastPriceTraded"),
        "delayed": int(bool(book.get("isMarketDataDelayed"))),
    }


def store(conn, market: dict, row: dict, now: datetime) -> str:
    """Insert or extend; returns 'new' / 'unchanged'."""
    order = sorted(market["runners"], key=lambda r: r.get("sortPriority", 0))
    stamp = iso(now)
    conn.execute(
        "INSERT OR IGNORE INTO betfair_markets (market_id, event_name, competition, market_start_utc, "
        "runner_a, runner_b, selection_a, selection_b, first_seen_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (market["marketId"], (market.get("event") or {}).get("name"),
         (market.get("competition") or {}).get("name"), market["marketStartTime"].replace(".000Z", "Z"),
         order[0]["runnerName"], order[1]["runnerName"], order[0]["selectionId"], order[1]["selectionId"], stamp),
    )
    # Betfair moves a market's start time when the order of play changes.
    conn.execute("UPDATE betfair_markets SET market_start_utc = ? WHERE market_id = ?",
                 (market["marketStartTime"].replace(".000Z", "Z"), market["marketId"]))
    last = conn.execute(
        "SELECT id, " + ", ".join(PRICE_COLS) + " FROM betfair_price_snapshots "
        "WHERE market_id = ? ORDER BY id DESC LIMIT 1", (market["marketId"],)).fetchone()
    if last is not None and all(last[c] == row[c] for c in PRICE_COLS):
        conn.execute("UPDATE betfair_price_snapshots SET last_seen_at = ? WHERE id = ?", (stamp, last["id"]))
        return "unchanged"
    cols = ("market_id", "fetched_at", "last_seen_at", *PRICE_COLS, "delayed")
    vals = (market["marketId"], stamp, stamp, *(row[c] for c in PRICE_COLS), row["delayed"])
    conn.execute(f"INSERT INTO betfair_price_snapshots ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals)
    return "new"


def snapshot(conn, now: datetime | None = None, rpc=None) -> dict:
    now = now or datetime.now(timezone.utc)
    rpc = rpc or client_rpc()
    ensure_schema(conn)
    markets = {m["marketId"]: m for m in catalogue(now, rpc)}
    counts = {"markets": len(markets), "new": 0, "unchanged": 0, "missing": 0}
    ids = list(markets)
    for start in range(0, len(ids), BOOK_CHUNK):
        books = rpc("listMarketBook", {"marketIds": ids[start:start + BOOK_CHUNK],
                                       "priceProjection": {"priceData": ["EX_BEST_OFFERS"]}}) or []
        for book in books:
            market = markets.get(book.get("marketId"))
            row = price_row(book, market) if market else None
            if row is None:
                counts["missing"] += 1
                continue
            counts[store(conn, market, row, now)] += 1
    conn.commit()
    return counts


def price_at(conn, market_id: str, moment: datetime, tolerance: timedelta) -> dict | None:
    """The price valid at `moment`: newest row fetched by moment+tol and still seen at moment-tol."""
    row = conn.execute(
        "SELECT * FROM betfair_price_snapshots WHERE market_id = ? AND fetched_at <= ? "
        "AND last_seen_at >= ? ORDER BY fetched_at DESC LIMIT 1",
        (market_id, iso(moment + tolerance), iso(moment - tolerance))).fetchone()
    return dict(row) if row else None


def last_before(conn, market_id: str, moment: datetime) -> dict | None:
    row = conn.execute(
        "SELECT * FROM betfair_price_snapshots WHERE market_id = ? AND fetched_at < ? AND in_play = 0 "
        "ORDER BY fetched_at DESC LIMIT 1", (market_id, iso(moment))).fetchone()
    return dict(row) if row else None


def fair_a(row: dict | None, max_spread: float = 1.10) -> float | None:
    """Probability of runner A from the back/lay mids; None when the book is too thin."""
    if not row or row.get("in_play"):
        return None
    mids = []
    for side in ("a", "b"):
        back, lay = row.get(f"{side}_back"), row.get(f"{side}_lay")
        if not back or not lay or back <= 1 or lay / back > max_spread:
            return None
        mids.append((back + lay) / 2)
    ia, ib = 1 / mids[0], 1 / mids[1]
    return ia / (ia + ib)
