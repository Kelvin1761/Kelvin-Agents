"""精選 shadow arms: paper-only variants of the 精選 rule, frozen like the real thing.

Pre-registered 2026-11-16 (EXP-20261116-11) before any pick was written:

  cap3   the 精選 rule unchanged, except a candidate's odds must be < 3.0.
         Why: on the odds >= 3 rows the model put ~0.5 where the de-vigged
         market put ~0.2 and the result matched the market (EXP-20261116-08),
         and ranking by raw edge lifts exactly those rows to the top.

A shadow arm is never sent, never shown on the dashboard and never accepts a
live bet; its picks are written to ``featured_shadow_picks`` at the same
moment the real 精選 runs (21:00 / 23:00 / 09:00), with the same freeze and
top-up rules, so both arms see the same candidates at the same prices.

Verdict: the same pre-registered rule as the real arm (featured.forward_verdict,
250 then 600 settled). Secondary, descriptive only: the real arm's ROI over the
same match dates. Changing the arm after looking = a new arm with a new name.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from tennis_wc.select import featured


@dataclass(frozen=True)
class ShadowArm:
    name: str
    max_odds_exclusive: float
    experiment: str


ARMS: dict[str, ShadowArm] = {
    "cap3": ShadowArm("cap3", 3.0, "EXP-20261116-11"),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS featured_shadow_picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arm TEXT NOT NULL,
    prop_id INTEGER NOT NULL,
    match_id INTEGER NOT NULL,
    match_date TEXT NOT NULL,
    rank INTEGER NOT NULL,
    run_label TEXT NOT NULL,
    market_key TEXT NOT NULL,
    selection TEXT NOT NULL,
    match_label TEXT,
    start_time_utc TEXT NOT NULL,
    odds REAL NOT NULL,
    edge REAL,
    ev REAL,
    model_prob REAL,
    featured_at TEXT NOT NULL,
    UNIQUE(arm, match_id),
    UNIQUE(arm, prop_id)
)
"""


def ensure_schema(conn) -> None:
    conn.execute(SCHEMA)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_featured_shadow_arm_date "
        "ON featured_shadow_picks(arm, match_date)"
    )


def arm_candidates(arm: ShadowArm, candidates: list[featured.Candidate]) -> list[featured.Candidate]:
    return [c for c in candidates if c.odds < arm.max_odds_exclusive]


def record(conn, match_date: str, run_label: str, now: datetime | None = None,
           *, candidates: list[featured.Candidate] | None = None) -> dict[str, list[dict]]:
    """Freeze new shadow picks for every arm; return the newly added rows per arm."""
    now = now or datetime.now(timezone.utc)
    ensure_schema(conn)
    pool = candidates if candidates is not None else featured.candidates(conn, match_date, now)
    added: dict[str, list[dict]] = {}
    for arm in ARMS.values():
        existing = conn.execute(
            "SELECT match_id, rank FROM featured_shadow_picks WHERE arm = ? AND match_date = ?",
            (arm.name, match_date),
        ).fetchall()
        taken = {int(r["match_id"]) for r in existing}
        next_rank = max((int(r["rank"]) for r in existing), default=0) + 1
        picks = featured.choose(arm_candidates(arm, pool), taken, featured.MAX_PER_DAY - len(existing))
        rows = []
        for offset, c in enumerate(picks):
            row = {
                "arm": arm.name, "prop_id": c.prop_id, "match_id": c.match_id,
                "match_date": match_date, "rank": next_rank + offset, "run_label": run_label,
                "market_key": c.market_key, "selection": c.selection, "match_label": c.match_label,
                "start_time_utc": c.start_time_utc, "odds": c.odds, "edge": c.edge, "ev": c.ev,
                "model_prob": c.model_prob, "featured_at": featured._iso(now),
            }
            conn.execute(
                f"INSERT OR IGNORE INTO featured_shadow_picks ({', '.join(row)}) "
                f"VALUES ({', '.join('?' for _ in row)})",
                tuple(row.values()),
            )
            rows.append(row)
        added[arm.name] = rows
    conn.commit()
    return added


def picks_with_results(conn, arm: str) -> list[dict]:
    ensure_schema(conn)
    rows = []
    for r in conn.execute(
        "SELECT s.*, p.result_status FROM featured_shadow_picks s "
        "LEFT JOIN prop_tracker p ON p.id = s.prop_id WHERE s.arm = ? "
        "ORDER BY s.match_date, s.rank", (arm,),
    ).fetchall():
        row = dict(r)
        row["unit_profit"] = featured.unit_profit(row.get("result_status"), float(row["odds"]))
        rows.append(row)
    return rows


def real_arm_same_dates(conn, shadow_rows: list[dict]) -> dict:
    """Descriptive comparison: the real 精選 over the match dates the shadow arm covers."""
    dates = sorted({r["match_date"] for r in shadow_rows})
    if not dates:
        return featured.performance([])
    real = [r for r in featured.picks_with_results(conn, since=dates[0], until=dates[-1])
            if r["match_date"] in set(dates)]
    return featured.performance(real)
