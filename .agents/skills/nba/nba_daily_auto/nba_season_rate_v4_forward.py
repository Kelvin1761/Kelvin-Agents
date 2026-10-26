#!/usr/bin/env python3
"""Frozen forward test: S_v4 vs S_v2 on legs whose history still holds last season. Read-only.

Protocol: docs/experiments/EXP-20261026-08-nba-s-v4-shadow-and-forward-protocol.md.
S_v4 only differs from S_v2 while previous-season games are in a player's history, so
only those legs are compared (paired, same leg, same snapshot). Never changes a pick.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from datetime import date
from pathlib import Path

import nba_market_ledger as ledger

EPOCH = "2026-10-27"
FINAL_DATE = "2026-12-01"
QUIET_DAYS = 3            # analyse once no affected legs appear for this many slate days
MIN_EVENTS = 100
BOOTSTRAP_DRAWS = 4000
BOOTSTRAP_SEED = 20261027


def collect(root: Path, since: str, until: str | None) -> tuple[list[dict], list[str]]:
    legs, slate_days = [], []
    for day in ledger._iter_dates(since, until, root):
        rows = ledger.read_rows(root, day)
        models, settlements = defaultdict(list), {}
        for r in rows:
            if r.get("row_type") == "model_obs":
                models[ledger._leg_key(r)].append(r)
            elif r.get("row_type") == "settlement":
                settlements.setdefault(ledger._leg_key(r), r)
        affected = 0
        for key, group in models.items():
            snap = ledger._choose_snapshot(group)
            if snap is None:
                continue
            m = next(r for r in group if r.get("snapshot_id") == snap)
            if "season_rate_v4_status" not in m:
                continue  # written before the S_v4 shadow existed
            inputs = m.get("season_rate_v4_inputs") or {}
            if m.get("season_rate_v4_status") != "ok" or not inputs.get("previous_games"):
                continue
            affected += 1
            s = settlements.get(key)
            p2, p4 = m.get("season_rate_v2_prob_S"), m.get("season_rate_v4_prob_S")
            if not s or s.get("y") not in (0, 1) or p2 is None or p4 is None or (m.get("side") or "over") != "over":
                continue
            legs.append({"day": day, "event": f"{day}:{key[1]}", "player": key[2], "stat": m.get("market"),
                         "y": int(s["y"]), "p2": float(p2), "p4": float(p4),
                         "leak": str(inputs.get("last_game_date") or "") >= day})
        if any(r.get("row_type") == "model_obs" for r in rows):
            slate_days.append((day, affected))
    return legs, slate_days


def _ll(p, y):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def analyse(legs: list[dict], slate_days: list, today: str) -> dict:
    size = defaultdict(int)
    for l in legs:
        size[(l["event"], l["player"], l["stat"])] += 1
    w = [1.0 / size[(l["event"], l["player"], l["stat"])] for l in legs]
    quiet = len(slate_days) >= QUIET_DAYS and all(a == 0 for _, a in slate_days[-QUIET_DAYS:])
    due = quiet or today >= FINAL_DATE
    events = len({l["event"] for l in legs})
    report = {"protocol": "EXP-20261026-08", "legs": len(legs), "events": events,
              "dates": len({l["day"] for l in legs}), "analysis_due": due,
              "leak_rows": sum(l["leak"] for l in legs), "promotion_allowed": False}
    if report["leak_rows"]:
        report["status"] = "INVALID_DATA"
        return report
    if not legs:
        report["status"] = "AWAITING_DATA"
        return report

    def delta(idx):
        tw = sum(w[i] for i in idx)
        return sum(w[i] * (_ll(legs[i]["p4"], legs[i]["y"]) - _ll(legs[i]["p2"], legs[i]["y"])) for i in idx) / tw

    allidx = list(range(len(legs)))
    report["logloss_v4_minus_v2"] = round(delta(allidx), 6)
    report["by_stat"] = {s: round(delta([i for i in allidx if legs[i]["stat"] == s]), 6)
                         for s in sorted({l["stat"] for l in legs})}
    if not due:
        report["status"] = "ACCUMULATING"
        return report
    if events < MIN_EVENTS:
        report["status"] = "NEEDS_MORE_TESTING"   # carry to next season's early window
        return report
    by_day = defaultdict(list)
    for i, l in enumerate(legs):
        by_day[l["day"]].append(i)
    days = sorted(by_day)
    rng = random.Random(BOOTSTRAP_SEED)
    draws = sorted(delta([i for d in (rng.choice(days) for _ in days) for i in by_day[d]])
                   for _ in range(BOOTSTRAP_DRAWS))
    ci = [round(draws[int(0.025 * BOOTSTRAP_DRAWS)], 6), round(draws[int(0.975 * BOOTSTRAP_DRAWS) - 1], 6)]
    report["ci95"] = ci
    report["status"] = "KEEP" if ci[1] < 0 else ("REJECT" if ci[0] > 0 or report["logloss_v4_minus_v2"] >= 0
                                                 else "NEEDS_MORE_TESTING")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--until", default=None)
    args = parser.parse_args(argv)
    legs, slate_days = collect(args.root or ledger.ledger_root(), EPOCH, args.until)
    print(json.dumps(analyse(legs, slate_days, args.until or date.today().isoformat()),
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
