"""Replay-equivalence harness for the Tennis Wong Choi rebuild.

Runs ONE code tree (``--src``) against a frozen, read-only DB and writes every
priced number to JSON, so the old and new engines can be diffed:

  match   predict_match_probability for every feature snapshot in the window
  props   every priced prop for every date in the window (log=False)

The DB is opened with ``immutable=1``: any write attempt fails loudly instead of
changing the baseline.  ``utc_now`` is pinned to the start of each date.

  python3 replay.py --src <tree>/tennis-wong-choi/src --db baseline.db \
      --start 2026-10-28 --end 2026-11-05 --out old.json
  python3 replay.py --diff old.json new.json
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import sqlite3
import sys
from datetime import date, timedelta


def _plain(value):
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


# Families the rebuild keeps pricing (Kelvin 2026-11-05 paused aces, double
# faults and exact set score; match total games was never bettable).
KEPT = {
    "player_total_games", "player_win_a_set", "first_set_winner",
    "player_first_set_match", "player_first_set_game_handicap",
    "player_game_handicap", "player_set_handicap",
}


def _kept(market_key: str) -> bool:
    for family in KEPT:
        if market_key.startswith(family + "_"):
            return True
    return False


FEED_KEYS = ("feed_market_key", "feed_market_name", "feed_selection_name", "feed_line")


def _normalise(row: dict) -> dict:
    """Absent feed fields == None; drop evidence profiles of families no longer priced."""
    for key in FEED_KEYS:
        row.setdefault(key, None)
    profiles = (row.get("pricing_evidence") or {}).get("profiles") or {}
    for paused in ("aces", "double_faults"):
        profiles.pop(paused, None)
    return row


def _connect(db: str):
    conn = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _dates(start: str, end: str):
    d, last = date.fromisoformat(start), date.fromisoformat(end)
    while d <= last:
        yield d.isoformat()
        d += timedelta(days=1)


class _LegacyApi:
    """Adapter for trees from before the rebuild (no ``tennis_wc.engine_api``)."""

    @staticmethod
    def match_probabilities(conn, day):
        out = {}
        for row in conn.execute(
            "SELECT p.match_id, p.model_probability, p.selection_player_id, p.pricing_json "
            "FROM predictions p JOIN matches m ON m.id = p.match_id "
            "WHERE m.match_date = ? ORDER BY p.id", (day,)):
            out[str(row[0])] = row[1]
        return out

    @staticmethod
    def price_props(conn, day):
        """Every row the old engine would write to prop_tracker for ``day``."""
        import tennis_wc.props.daily as daily

        from tennis_wc.features.common import utc_now  # legacy tree layout
        from tennis_wc.props.pricing_evidence import freeze_context
        from tennis_wc.props.registry import family_for_market

        rows = []

        def capture(_conn, *, pricing_evidence=None, **kw):
            # Exactly what record_prop stores in pricing_evidence_json.
            ctx = dict(pricing_evidence or {})
            ctx = {**ctx, "context_captured_at": ctx.get("priced_at"), "priced_at": utc_now()}
            kw["pricing_evidence"] = json.loads(freeze_context(
                ctx, family_for_market(kw["market_key"]), kw["subject_player_id"],
                kw.get("feed_market_key"), kw.get("feed_market_name"),
                kw.get("feed_selection_name"), kw.get("feed_line")))
            rows.append(kw)

        original = daily.record_prop
        daily.record_prop = capture
        try:
            daily.price_ace_props_for_date(conn, day, log=True)
        finally:
            daily.record_prop = original
        return rows


def _engine_api():
    try:
        from tennis_wc import engine_api
        return engine_api
    except ImportError:
        return _LegacyApi


def run(src: str, db: str, start: str, end: str) -> dict:
    sys.path.insert(0, src)
    try:  # tree layout after 2026-11-06 / before
        import tennis_wc.model.features.common as common
    except ImportError:
        import tennis_wc.features.common as common
    engine_api = _engine_api()

    conn = _connect(db)
    out = {"match": {}, "props": {}, "engine": getattr(engine_api, "__name__", str(engine_api))}
    for day in _dates(start, end):
        pinned = f"{day}T00:00:00+00:00"
        common.utc_now = lambda pinned=pinned: pinned
        out["match"].update(engine_api.match_probabilities(conn, day))
        rows = [_normalise(_plain(r)) for r in engine_api.price_props(conn, day)]
        out["props"][day] = sorted(
            (r for r in rows if _kept(r["market_key"])),
            key=lambda r: (r["match_id"], r["market_key"], r["selection"]))
    return out


def _walk(a, b, path, diffs, tol):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                diffs.append(f"{path}.{k}: only in {'new' if k in b else 'old'}")
            else:
                _walk(a[k], b[k], f"{path}.{k}", diffs, tol)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append(f"{path}: len {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            _walk(x, y, f"{path}[{i}]", diffs, tol)
    elif isinstance(a, float) and isinstance(b, (int, float)) and not isinstance(b, bool):
        if abs(a - b) > tol:
            diffs.append(f"{path}: {a!r} != {b!r}")
    elif a != b:
        diffs.append(f"{path}: {a!r} != {b!r}")


def diff(old_path: str, new_path: str, tol: float = 1e-9) -> list[str]:
    with open(old_path) as f:
        old = json.load(f)
    with open(new_path) as f:
        new = json.load(f)
    diffs: list[str] = []
    old.pop("engine", None)
    new.pop("engine", None)
    _walk(old, new, "", diffs, tol)
    return diffs


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--src")
    p.add_argument("--db")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--out")
    p.add_argument("--diff", nargs=2)
    a = p.parse_args()
    if a.diff:
        diffs = diff(*a.diff)
        print("engines:", [json.load(open(x)).get("engine") for x in a.diff])
        for line in diffs[:200]:
            print(line)
        print(f"{len(diffs)} differences")
        return 1 if diffs else 0
    result = run(a.src, a.db, a.start, a.end)
    with open(a.out, "w") as f:
        json.dump(result, f, sort_keys=True)
    n = sum(len(v) for v in result["props"].values())
    print(f"match={len(result['match'])} boards={n} -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
