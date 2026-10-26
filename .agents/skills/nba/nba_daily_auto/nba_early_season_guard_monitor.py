#!/usr/bin/env python3
"""Forward monitor for the early-season banker guard (EXP-20261026-03). Read-only.

For banker-like legs (L10 >= 80%, C >= 60%, price >= 1.15) on the latest published
pre-tip snapshot, compares guarded and unguarded legs by stat: count, games, mean C,
actual hit rate and market 1/price. The guard is right if guarded legs keep landing
well below C while unguarded ones track it. Legs in one game are correlated, so the
games column is the effective sample. Never changes a pick.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import nba_market_ledger as ledger

BANKER_LIKE = {"l10": 0.8, "p": 0.6, "price": 1.15}


def legs(root: Path, since: str | None, until: str | None) -> list[dict]:
    out = []
    for day in ledger._iter_dates(since, until, root):
        rows = ledger.read_rows(root, day)
        models, settlements = defaultdict(list), {}
        for r in rows:
            if r.get("row_type") == "model_obs":
                models[ledger._leg_key(r)].append(r)
            elif r.get("row_type") == "settlement":
                settlements.setdefault(ledger._leg_key(r), r)
        for key, group in models.items():
            snap = ledger._choose_snapshot(group)
            if snap is None:
                continue
            m = next(r for r in group if r.get("snapshot_id") == snap)
            s = settlements.get(key)
            if "early_season_guard" not in m or not s or s.get("y") not in (0, 1):
                continue  # pre-guard snapshot, unsettled or void
            l10, p, price = m.get("p_l10_base_rate"), m.get("p_final"), m.get("price_at_model")
            if None in (l10, p, price) or l10 < BANKER_LIKE["l10"] or p < BANKER_LIKE["p"] \
                    or price < BANKER_LIKE["price"]:
                continue
            reasons = m.get("early_season_guard") or []
            out.append({"day": day, "game": key[1], "stat": m.get("market"), "p": p, "y": s["y"],
                        "price": price, "guard": "+".join(sorted(reasons)) or "none"})
    return out


def summarise(rows: list[dict]) -> dict:
    groups = defaultdict(list)
    for r in rows:
        groups[(r["stat"], r["guard"])].append(r)
    table = {}
    for (stat, guard), g in sorted(groups.items()):
        n = len(g)
        table[f"{stat} | {guard}"] = {
            "legs": n, "games": len({(r["day"], r["game"]) for r in g}),
            "mean_c": round(sum(r["p"] for r in g) / n, 3), "hit": round(sum(r["y"] for r in g) / n, 3),
            "market": round(sum(1 / r["price"] for r in g) / n, 3)}
    return {"protocol": "EXP-20261026-03", "banker_like": BANKER_LIKE, "table": table,
            "note": "descriptive; judge only by games, not legs"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--since", default="2026-10-27")
    parser.add_argument("--until")
    args = parser.parse_args(argv)
    print(json.dumps(summarise(legs(args.root or ledger.ledger_root(), args.since, args.until)),
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
