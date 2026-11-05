"""精選 (featured picks): at most ten bets a day, one per match, frozen when sent.

Pre-registered 2026-11-05 (docs/plans/2026-11-05-tennis-strategy-and-rebuild-plan.md
section C, EXP-20261105-08). Do not change the rule after looking at results:
a new rule is a new forward arm.

Why one per match: on 264 point-in-time matches that carried several value
props, the highest-edge bet beat the rest of the same match by +15.1pp
[+4.2, +25.9]; the extra bets were mostly the same player's handicap ladder.
Why not "top ten by confidence": ranking the day by model probability picked
the shortest prices and was the worst ordering measured (-16.4%).

A pick is frozen at the price and moment it is first sent. Later passes (23:00
and the 09:00 backup) may only ADD picks for matches not yet featured and not
yet started, within the same ten-a-day cap.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone

# Score-settled families only (Kelvin 2026-11-05). Aces, double faults, match
# aces and exact set score are paused: thin samples, and stat-settled.
FAMILIES = frozenset({
    "player_game_handicap",
    "first_set_winner",
    "player_win_a_set",
    "player_first_set_game_handicap",
    "player_set_handicap",
    "player_total_games",
})
MAX_PER_DAY = 10

# Forward test (section D of the plan). It starts with the first pick ever written
# to featured_picks; replays are never written there.
FORWARD_FIRST_VERDICT = 250
FORWARD_FINAL_VERDICT = 600
BOOTSTRAP_DRAWS = 4000
BOOTSTRAP_SEED = 20260826

SCHEMA = """
CREATE TABLE IF NOT EXISTS featured_picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prop_id INTEGER NOT NULL UNIQUE,
    match_id INTEGER NOT NULL UNIQUE,
    match_date TEXT NOT NULL,
    rank INTEGER NOT NULL,
    run_label TEXT NOT NULL,
    market_key TEXT NOT NULL,
    selection TEXT NOT NULL,
    match_label TEXT,
    feed_market_name TEXT,
    feed_selection_name TEXT,
    start_time_utc TEXT NOT NULL,
    odds REAL NOT NULL,
    edge REAL,
    ev REAL,
    model_prob REAL,
    featured_at TEXT NOT NULL
)
"""


def ensure_schema(conn) -> None:
    conn.execute(SCHEMA)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_featured_picks_date ON featured_picks(match_date)"
    )


def _utc(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Candidate:
    prop_id: int
    match_id: int
    market_key: str
    selection: str
    match_label: str
    start_time_utc: str
    odds: float
    edge: float
    ev: float
    model_prob: float | None
    feed_market_name: str = ""
    feed_selection_name: str = ""


def _sort_key(c: Candidate) -> tuple:
    # Tie-break order agreed 2026-11-05: edge, then EV, then price.
    return (c.edge, c.ev, c.odds)


def choose(candidates: list[Candidate], already_featured_matches: set[int],
           slots_left: int) -> list[Candidate]:
    """Pure rule: best bet per new match, best matches first, within the cap."""
    if slots_left <= 0:
        return []
    best: dict[int, Candidate] = {}
    for c in candidates:
        if c.match_id in already_featured_matches:
            continue
        current = best.get(c.match_id)
        if current is None or _sort_key(c) > _sort_key(current):
            best[c.match_id] = c
    ranked = sorted(best.values(), key=_sort_key, reverse=True)
    return ranked[:slots_left]


def _live_quality(evidence_json) -> float | None:
    from tennis_wc.props.pricing_evidence import read_evidence

    evidence = read_evidence(evidence_json)
    return evidence.get("source_quality") if evidence else None


def candidates(conn, match_date: str, now: datetime, *, pending_only: bool = True) -> list[Candidate]:
    """Value props for the date that are bettable right now under the formal profile.

    ``pending_only=False`` is for replays of past dates only.
    """
    from tennis_wc.props.registry import family_for_market
    from tennis_wc.props.strategy import meets_formal_profile

    rows = conn.execute(
        """
        SELECT p.id, p.match_id, p.market_key, p.selection, p.match_label,
               p.feed_market_name, p.feed_selection_name,
               p.decimal_odds, p.edge, p.ev, p.model_prob_raw, p.blended_prob,
               p.pricing_evidence_json, p.priced_at, p.recorded_at,
               m.start_time_utc, m.fixture_status, m.source_provider
        FROM prop_tracker p
        JOIN matches m ON m.id = p.match_id
        WHERE p.match_date = ? AND p.is_value = 1
          AND (? = 0 OR p.result_status = 'PENDING')
        """,
        (match_date, 1 if pending_only else 0),
    ).fetchall()
    out: list[Candidate] = []
    for r in rows:
        start = _utc(r["start_time_utc"])
        priced = _utc(r["priced_at"] or r["recorded_at"])
        if start is None or priced is None or not (priced < start) or now >= start:
            continue
        if r["fixture_status"] == "DISPUTED" or r["source_provider"] == "mock":
            continue
        if family_for_market(r["market_key"] or "") not in FAMILIES:
            continue
        if not meets_formal_profile(
            r["market_key"], r["model_prob_raw"], r["blended_prob"], r["decimal_odds"],
            _live_quality(r["pricing_evidence_json"]), r["edge"], r["ev"],
        ):
            continue
        out.append(Candidate(
            prop_id=int(r["id"]), match_id=int(r["match_id"]),
            market_key=r["market_key"], selection=str(r["selection"] or ""),
            match_label=str(r["match_label"] or ""), start_time_utc=r["start_time_utc"],
            odds=float(r["decimal_odds"]), edge=float(r["edge"] or 0.0),
            ev=float(r["ev"] or 0.0),
            model_prob=None if r["model_prob_raw"] is None else float(r["model_prob_raw"]),
            feed_market_name=str(r["feed_market_name"] or ""),
            feed_selection_name=str(r["feed_selection_name"] or ""),
        ))
    return out


def record(conn, match_date: str, run_label: str, now: datetime | None = None) -> list[dict]:
    """Freeze any new picks for the date; return only the newly added ones."""
    now = now or datetime.now(timezone.utc)
    ensure_schema(conn)
    existing = conn.execute(
        "SELECT match_id, rank FROM featured_picks WHERE match_date = ?", (match_date,)
    ).fetchall()
    taken = {int(r["match_id"]) for r in existing}
    next_rank = max((int(r["rank"]) for r in existing), default=0) + 1
    picks = choose(candidates(conn, match_date, now), taken, MAX_PER_DAY - len(existing))
    added = []
    for offset, c in enumerate(picks):
        row = {
            "prop_id": c.prop_id, "match_id": c.match_id, "match_date": match_date,
            "rank": next_rank + offset, "run_label": run_label, "market_key": c.market_key,
            "selection": c.selection, "match_label": c.match_label,
            "feed_market_name": c.feed_market_name, "feed_selection_name": c.feed_selection_name,
            "start_time_utc": c.start_time_utc, "odds": c.odds, "edge": c.edge,
            "ev": c.ev, "model_prob": c.model_prob, "featured_at": _iso(now),
        }
        conn.execute(
            f"INSERT OR IGNORE INTO featured_picks ({', '.join(row)}) "
            f"VALUES ({', '.join('?' for _ in row)})",
            tuple(row.values()),
        )
        added.append(row)
    conn.commit()
    return added


def unit_profit(status: str | None, odds: float) -> float | None:
    if status == "WON":
        return odds - 1.0
    if status == "LOST":
        return -1.0
    if status == "VOID":
        return 0.0
    return None


def picks_with_results(conn, since: str | None = None, until: str | None = None) -> list[dict]:
    """Featured picks joined to the single source of results (prop_tracker)."""
    ensure_schema(conn)
    where, params = [], []
    if since:
        where.append("f.match_date >= ?"); params.append(since)
    if until:
        where.append("f.match_date <= ?"); params.append(until)
    sql = (
        "SELECT f.*, p.result_status, p.actual_value FROM featured_picks f "
        "LEFT JOIN prop_tracker p ON p.id = f.prop_id"
        + (" WHERE " + " AND ".join(where) if where else "")
        + " ORDER BY f.match_date, f.rank"
    )
    rows = []
    for r in conn.execute(sql, params).fetchall():
        row = dict(r)
        row["unit_profit"] = unit_profit(row.get("result_status"), float(row["odds"]))
        rows.append(row)
    return rows


def performance(rows: list[dict]) -> dict:
    """ROI over settled non-void picks with a 95% bootstrap CI.

    One pick per match, so resampling picks is resampling matches.
    """
    settled = [r for r in rows if r["unit_profit"] is not None and r.get("result_status") != "VOID"]
    n = len(settled)
    out = {
        "picks": len(rows), "settled": n,
        "wins": sum(r["result_status"] == "WON" for r in settled),
        "pending": sum(r["unit_profit"] is None for r in rows),
        "pnl": round(sum(r["unit_profit"] for r in settled), 3),
        "roi": None, "ci_low": None, "ci_high": None,
    }
    if not n:
        return out
    profits = [r["unit_profit"] for r in settled]
    out["roi"] = sum(profits) / n
    if n >= 10:
        rng = random.Random(BOOTSTRAP_SEED)
        draws = sorted(sum(rng.choice(profits) for _ in range(n)) / n for _ in range(BOOTSTRAP_DRAWS))
        out["ci_low"] = draws[int(0.025 * BOOTSTRAP_DRAWS)]
        out["ci_high"] = draws[int(0.975 * BOOTSTRAP_DRAWS) - 1]
    return out


def forward_verdict(perf: dict) -> str | None:
    """Pre-registered decision; None until the first verdict point."""
    n = perf["settled"]
    if n < FORWARD_FIRST_VERDICT or perf["ci_low"] is None:
        return None
    if perf["ci_low"] > 0:
        return "ELIGIBLE_FOR_RELEASE_REVIEW"
    if perf["ci_high"] < 0:
        return "REJECT"
    if n >= FORWARD_FINAL_VERDICT:
        # No further extension: still unproven means no real money.
        return "NOT_PROVEN"
    return "CONTINUE_TO_600"


# ---------------------------------------------------------------- Telegram

FAMILY_LABELS = {
    "player_game_handicap": "讓局",
    "first_set_winner": "首盤勝方",
    "player_win_a_set": "贏至少一盤",
    "player_first_set_game_handicap": "首盤讓局",
    "player_set_handicap": "讓盤",
    "player_total_games": "球員總局數",
}


def _sydney_time(start_time_utc: str) -> str:
    from zoneinfo import ZoneInfo

    moment = _utc(start_time_utc)
    return moment.astimezone(ZoneInfo("Australia/Sydney")).strftime("%H:%M") if moment else "--:--"


def _pick_lines(picks: list[dict]) -> list[str]:
    from tennis_wc.props.registry import family_for_market

    lines = []
    for p in sorted(picks, key=lambda r: (r["start_time_utc"], r["rank"])):
        family = FAMILY_LABELS.get(family_for_market(p["market_key"] or ""), "")
        market = p.get("feed_market_name") or family
        choice = p.get("feed_selection_name") or p.get("selection") or ""
        lines += [
            "",
            f"{_sydney_time(p['start_time_utc'])}  {p.get('match_label') or ''}",
            f"• {family}｜Sportsbet：{market} → {choice}",
            f"• 賠率 {float(p['odds']):.2f}｜1 注",
        ]
    return lines


def _progress_line(perf: dict) -> str:
    if not perf["settled"]:
        return "前向測試：暫時未有已結算精選。"
    roi = f"{perf['roi']:+.1%}" if perf["roi"] is not None else "—"
    ci = (f"｜95% CI [{perf['ci_low']:+.1%}, {perf['ci_high']:+.1%}]"
          if perf["ci_low"] is not None else "")
    return f"前向測試：{perf['settled']}／{FORWARD_FIRST_VERDICT} 注已結算｜ROI {roi}{ci}"


def telegram_message(match_date: str, picks: list[dict], *, kind: str, perf: dict) -> str:
    """kind: 'main' (21:00, always sent) or 'topup' (23:00 / 09:00, new picks only)."""
    if kind == "main":
        head = [f"🎾 Tennis Wong Choi｜精選｜{match_date}",
                f"聽日精選 {len(picks)}／{MAX_PER_DAY} 注（每注 1 單位，今晚 21:00–00:00 落）"]
        if not picks:
            head.append("聽日暫時無精選。23:00 同明朝 09:00 會再睇，有先通知。")
    else:
        head = [f"🎾 Tennis Wong Choi｜補充精選｜{match_date}",
                f"新增 {len(picks)} 注（之前未開盤）"]
    verdict = forward_verdict(perf)
    footer = ["", _progress_line(perf),
              "未證實賺錢，只係紙上前向測試，唔好落真錢。" if verdict is None
              else f"前向判決：{verdict}（落唔落真錢由 Kelvin 決定）"]
    return "\n".join(head + _pick_lines(picks) + footer)
