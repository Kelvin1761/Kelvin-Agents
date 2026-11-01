"""EXP-20261101-60: how much did the official.nba.com injury report change, historically?

usage: python3 EXP-20261101-60-nba-official-injury-effect.py [analysis root]

For each player-game's latest published pre-tip availability_obs (ledger), compare
the ESPN level with the league report's level; where the league report was
stricter, join the box score (Results_Brief) and Sportsbet pre-tip price_obs.
"""
import collections
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / ".agents/skills/nba/nba_daily_auto"))
import nba_availability_outcomes as A  # noqa: E402
import nba_market_ledger as L  # noqa: E402

ROOT = [Path(sys.argv[1] if len(sys.argv) > 1 else "/Users/imac/WongChoiData/Wong Choi NBA Analysis")]
SEV = {"ok": 0, "dtd": 1, "out": 2}


def espn(status):
    s = str(status or "").lower()
    return "out" if s in ("out", "suspension", "doubtful") else "dtd" if s in ("day-to-day", "questionable") else "ok"


def league(status):
    return A.official.STATUS_LEVEL.get(str(status or "").lower(), "ok")


ledger = L.ledger_root()
games = A.outcomes(ledger, ROOT, None, None)
prices = {}
counts, legs, priced = collections.Counter(), collections.Counter(), []
for o in games:
    e, f = espn(o["espn_status"]), league(o["official_status"])
    if SEV[f] <= SEV[e]:
        continue
    if o["date"] not in prices:
        prices[o["date"]] = [r for r in L.read_rows(ledger, o["date"])
                             if r.get("row_type") == "price_obs" and not r.get("post_tip")]
    key = A.official.name_key(o["player"])
    rows = [r for r in prices[o["date"]]
            if r.get("game_tag") == o["game_tag"] and A.official.name_key(r.get("player")) == key]
    counts[(f"{e}->{f}", "priced" if rows else "not_priced", "played" if o["played"] else "dnp")] += 1
    legs[f"{e}->{f}"] += len({(r["market"], r["line"], r["side"]) for r in rows})
    if rows:
        priced.append((o["date"], o["player"], f"{e}->{f}", "played" if o["played"] else "dnp"))
print("joined player-games", len(games), dict(collections.Counter(o["date"] for o in games)))
for k, v in sorted(counts.items()):
    print(" ", k, v)
print("distinct priced legs", dict(legs))
print("priced players", priced)
