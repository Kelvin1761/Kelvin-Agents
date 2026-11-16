"""Sportsbet vs Betfair paper forward test (EXP-20261116-19, pre-registered 2026-11-16).

One decision per match, frozen: at the match's first Sportsbet match-winner
snapshot taken 20:45-22:30 Sydney (the 21:00 card run) and >=5 min before the
start, compare against the Betfair price valid within +-20 min. Bet 1u (paper)
on the side with the larger EV = sportsbet_odds * p_betfair - 1 when it is > 0;
otherwise record a no-bet decision. Nothing is revisited afterwards, so prices
moving later never change a bet; ROI counts only these frozen rows.

Paper only: never sent as a card, never on the dashboard, never a live bet.
Changing any rule = a new experiment, not an edit here.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from tennis_wc.select import featured
from tennis_wc.sources import betfair_prices as bf
from tennis_wc.sources.name_matching import match_pair_score, normalise_player_name

EXPERIMENT = "EXP-20261116-19"
SYDNEY = ZoneInfo("Australia/Sydney")
DECISION_FROM, DECISION_TO = time(20, 45), time(22, 30)
MIN_LEAD = timedelta(minutes=5)
PRICE_TOLERANCE = timedelta(minutes=20)
START_TOLERANCE = timedelta(hours=6)
EV_THRESHOLD = 0.0
FIRST_LOOK, FINAL_VERDICT = 300, 1000

SCHEMA = """
CREATE TABLE IF NOT EXISTS sharp_forward_picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL UNIQUE,
    match_date TEXT NOT NULL,
    match_label TEXT,
    start_time_utc TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    sportsbet_snapshot_id INTEGER NOT NULL,
    sportsbet_fetched_at TEXT NOT NULL,
    sb_a REAL NOT NULL,
    sb_b REAL NOT NULL,
    betfair_market_id TEXT NOT NULL,
    betfair_snapshot_id INTEGER NOT NULL,
    betfair_orientation TEXT NOT NULL,
    p_a REAL NOT NULL,
    ev_a REAL NOT NULL,
    ev_b REAL NOT NULL,
    bet INTEGER NOT NULL,
    side TEXT,
    selection_player_id INTEGER,
    odds REAL,
    ev REAL
)
"""


def ensure_schema(conn) -> None:
    bf.ensure_schema(conn)
    conn.execute(SCHEMA)


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def in_decision_window(fetched_at: datetime) -> bool:
    local = fetched_at.astimezone(SYDNEY).time()
    return DECISION_FROM <= local <= DECISION_TO


def decision_snapshots(conn, now: datetime) -> list[dict]:
    """Undecided matches whose decision snapshot is old enough that every Betfair
    tick within the tolerance has already been taken."""
    rows = conn.execute(
        """SELECT o.id AS snap_id, o.match_id, o.player_a_odds, o.player_b_odds, o.fetched_at,
                  m.match_date, m.start_time_utc, m.player_a_id, m.player_b_id,
                  pa.name AS a_name, pb.name AS b_name
           FROM odds_snapshots o
           JOIN matches m ON m.id = o.match_id
           JOIN players pa ON pa.id = m.player_a_id
           JOIN players pb ON pb.id = m.player_b_id
           WHERE o.bookmaker = 'Sportsbet' AND o.market = 'match_winner'
             AND o.fetched_at >= ? AND m.start_time_utc IS NOT NULL
             AND COALESCE(m.fixture_status, 'ACTIVE') != 'DISPUTED'
             AND NOT EXISTS (SELECT 1 FROM sharp_forward_picks s WHERE s.match_id = o.match_id)
           ORDER BY o.match_id, o.fetched_at, o.id""",
        (bf.iso(now - timedelta(days=2)),),
    ).fetchall()
    first: dict[int, dict] = {}
    for r in rows:
        r = dict(r)
        if r["match_id"] in first:
            continue
        fetched, start = _utc(r["fetched_at"]), _utc(r["start_time_utc"])
        if in_decision_window(fetched) and fetched <= start - MIN_LEAD:
            first[r["match_id"]] = r
    return [r for r in first.values() if _utc(r["fetched_at"]) + PRICE_TOLERANCE <= now]


def _loose_same(left: str, right: str) -> bool:
    """Betfair trims long surnames ("Guiomar Maristany Zuleta" for "... Zuleta De Reales"):
    every token of the shorter name is in the longer one, at least two tokens, same first token."""
    a, b = normalise_player_name(left).split(), normalise_player_name(right).split()
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 2 and short[0] == long_[0] and set(short) <= set(long_)


def _orientation(runner_a: str, runner_b: str, our_a: str, our_b: str) -> str | None:
    _, orientation = match_pair_score(runner_a, runner_b, our_a, our_b)
    if orientation:
        return orientation
    if _loose_same(runner_a, our_a) and _loose_same(runner_b, our_b):
        return "direct"
    if _loose_same(runner_a, our_b) and _loose_same(runner_b, our_a):
        return "swapped"
    return None


def find_market(conn, snap: dict) -> tuple[str, str] | None:
    start = _utc(snap["start_time_utc"])
    hits = []
    for m in conn.execute(
        "SELECT market_id, runner_a, runner_b FROM betfair_markets "
        "WHERE market_start_utc BETWEEN ? AND ?",
        (bf.iso(start - START_TOLERANCE), bf.iso(start + START_TOLERANCE)),
    ).fetchall():
        orientation = _orientation(m["runner_a"], m["runner_b"], snap["a_name"], snap["b_name"])
        if orientation:
            hits.append((m["market_id"], orientation))
    return hits[0] if len(hits) == 1 else None


def decide(snap: dict, p_a: float) -> dict:
    ev_a = snap["player_a_odds"] * p_a - 1
    ev_b = snap["player_b_odds"] * (1 - p_a) - 1
    side = "a" if ev_a >= ev_b else "b"
    ev = max(ev_a, ev_b)
    bet = ev > EV_THRESHOLD
    return {"ev_a": ev_a, "ev_b": ev_b, "bet": int(bet), "side": side if bet else None,
            "odds": (snap["player_a_odds"] if side == "a" else snap["player_b_odds"]) if bet else None,
            "ev": ev if bet else None,
            "selection_player_id": (snap["player_a_id"] if side == "a" else snap["player_b_id"]) if bet else None}


def record(conn, now: datetime | None = None) -> dict:
    """Freeze every decision that is ready. Returns counts."""
    now = now or datetime.now(timezone.utc)
    ensure_schema(conn)
    counts = {"ready": 0, "no_market": 0, "no_price": 0, "decided": 0, "bets": 0}
    for snap in decision_snapshots(conn, now):
        counts["ready"] += 1
        found = find_market(conn, snap)
        if not found:
            counts["no_market"] += 1
            continue
        market_id, orientation = found
        price = bf.price_at(conn, market_id, _utc(snap["fetched_at"]), PRICE_TOLERANCE)
        p_bf_a = bf.fair_a(price)
        if p_bf_a is None:
            counts["no_price"] += 1
            continue
        p_a = p_bf_a if orientation == "direct" else 1 - p_bf_a
        d = decide(snap, p_a)
        row = {
            "match_id": snap["match_id"], "match_date": snap["match_date"],
            "match_label": f"{snap['a_name']} v {snap['b_name']}", "start_time_utc": snap["start_time_utc"],
            "decided_at": bf.iso(now), "sportsbet_snapshot_id": snap["snap_id"],
            "sportsbet_fetched_at": snap["fetched_at"], "sb_a": snap["player_a_odds"], "sb_b": snap["player_b_odds"],
            "betfair_market_id": market_id, "betfair_snapshot_id": price["id"], "betfair_orientation": orientation,
            "p_a": p_a, **d,
        }
        conn.execute(f"INSERT OR IGNORE INTO sharp_forward_picks ({', '.join(row)}) "
                     f"VALUES ({', '.join('?' for _ in row)})", tuple(row.values()))
        counts["decided"] += 1
        counts["bets"] += d["bet"]
    conn.commit()
    return counts


def _winner(conn, match_id: int) -> int | None:
    winners = {r[0] for r in conn.execute(
        "SELECT winner_player_id FROM match_results WHERE match_id = ?", (match_id,)).fetchall()}
    return winners.pop() if len(winners) == 1 else None


def picks_with_results(conn) -> list[dict]:
    """Bet rows with a featured-style result_status / unit_profit, plus CLV vs the last pre-start Betfair price."""
    ensure_schema(conn)
    rows = []
    for r in conn.execute("SELECT * FROM sharp_forward_picks WHERE bet = 1 ORDER BY match_date, id").fetchall():
        row = dict(r)
        winner = _winner(conn, row["match_id"])
        row["result_status"] = None if winner is None else ("WON" if winner == row["selection_player_id"] else "LOST")
        row["unit_profit"] = featured.unit_profit(row["result_status"], float(row["odds"]))
        close = bf.fair_a(bf.last_before(conn, row["betfair_market_id"], _utc(row["start_time_utc"])))
        if close is not None:
            p_close_a = close if row["betfair_orientation"] == "direct" else 1 - close
            p_side = p_close_a if row["side"] == "a" else 1 - p_close_a
            row["clv"] = row["odds"] * p_side - 1
        else:
            row["clv"] = None
        rows.append(row)
    return rows


def decision_counts(conn) -> dict:
    ensure_schema(conn)
    r = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(bet), 0) bets FROM sharp_forward_picks").fetchone()
    return {"decisions": int(r["n"]), "bets": int(r["bets"])}


def verdict(perf: dict) -> str | None:
    n = perf["settled"]
    if n < FIRST_LOOK or perf["ci_low"] is None:
        return None
    if perf["ci_high"] < 0:
        return "REJECT"
    if n < FINAL_VERDICT:
        return "INTERIM_CONTINUE"
    if perf["ci_low"] > 0:
        return "ELIGIBLE_FOR_RELEASE_REVIEW"
    return "NOT_PROVEN"
