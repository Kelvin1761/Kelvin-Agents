#!/usr/bin/env python3
"""Check the live book against the stop rule pre-registered in docs/STOP_RULE.md.

The rule is only a rule if something reads it. Written 2026-08-11 before the first
bet, so that neither the stop nor the review point is decided in the middle of a
losing run.

Counts only the families on the go-live allowlist and only bets on the live
profile, because those are the ones money is on. Prints the composition of the
book first: a pooled ROI has hidden an opposite result inside it every time it has
been trusted in this project.

Exit 0 = continue accumulating, 2 = pause, 3 = stop, 4 = 200-bet review due.

  PYTHONPATH=src .venv/bin/python scripts/check_stop_rule.py --since 2026-08-12
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sqlite3
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from tennis_wc.evaluation.corpus import point_in_time_clause  # noqa: E402


def _max_drawdown(values) -> float:
    peak = cumulative = 0.0
    worst = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        worst = min(worst, cumulative - peak)
    return worst


def _p_loss(values, seed: int = 20260811, trials: int = 4000):
    if len(values) < 20:
        return None
    rng = random.Random(seed)
    n = len(values)
    worse = sum(1 for _ in range(trials)
                if sum(values[rng.randrange(n)] for _ in range(n)) <= 0)
    return round(worse / trials, 3)


def _profit_for_live_bet(row) -> float:
    """Settle at the manually recorded odds/stake, not the paper tracker price."""
    stake = float(row["stake_units"] or 0.0)
    odds = float(row["odds_taken"] or 0.0)
    if stake <= 0 or odds <= 1:
        raise ValueError("a live-bet row needs positive stake and odds above 1")
    if row["result_status"] == "WON":
        return stake * (odds - 1.0)
    if row["result_status"] == "LOST":
        return -stake
    raise ValueError("only settled WON/LOST live bets belong in the verdict")


def _phase4_verdict(state: dict) -> str:
    """Give hard rules priority; never silently continue past the review point."""
    if state["action"] == "STOP":
        return "STOP"
    if state["action"] == "PAUSE":
        return "PAUSE_AND_AUDIT"
    if state["review_due"]:
        return "REVIEW_REQUIRED"
    return "CONTINUE_ACCUMULATING"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=PROJECT_DIR / "tennis_wc.db")
    ap.add_argument(
        "--since",
        required=True,
        help="first date of live staking, YYYY-MM-DD. Required so the fitted "
             "paper record can never be mistaken for the live book.",
    )
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    import os

    os.environ.setdefault("DATABASE_URL", f"sqlite:///{args.db}")
    from tennis_wc.props.daily import _tier_of
    from tennis_wc.props.strategy import (
        LIVE_FAMILIES, LIVE_INTERIM_CHECK_SETTLED, LIVE_INTERIM_MIN_ROI,
        LIVE_REVIEW_AFTER_SETTLED, LIVE_STOP_DRAWDOWN_UNITS,
        LIVE_UNIT_VALUE_AUD, MAX_EARLY_STAKE_UNITS, family_for_market,
        live_stop_state,
    )

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    # Provably pre-match rows only. The 2026-08-10 backfill wrote three months
    # of recommendations after the results were known, and counting those as
    # "recommendations we made" is how a stop rule gets talked out of firing.
    recommendation_count = int(conn.execute(
        f"""SELECT COUNT(*) FROM prop_tracker p
           WHERE p.result_status IN ('WON','LOST') AND p.stake_units > 0
             AND p.is_value = 1 AND {point_in_time_clause('p')}
             AND p.match_date >= ?""",
        (args.since,),
    ).fetchone()[0])
    recorded_live_bets = int(conn.execute(
        """SELECT COUNT(*) FROM prop_live_bets lb
           JOIN prop_tracker p ON p.id = lb.prop_id
           WHERE p.match_date >= ?""",
        (args.since,),
    ).fetchone()[0])
    settled_recorded_live_bets = int(conn.execute(
        """SELECT COUNT(*) FROM prop_live_bets lb
           JOIN prop_tracker p ON p.id = lb.prop_id
           WHERE p.match_date >= ? AND p.result_status IN ('WON','LOST')""",
        (args.since,),
    ).fetchone()[0])
    context_rows = conn.execute(
        """
            SELECT p.id, p.match_date, p.market_key, lb.stake_units,
                   lb.odds_taken, p.result_status,
                   COALESCE(p.side, 'unknown') AS side,
                   COALESCE(p.feed_market_name, p.feed_market_key, 'missing')
                       AS pricing_path,
                   COALESCE(m.source_provider, 'unknown') AS fixture_source,
                   t.name AS tname,
                   (SELECT tl.level FROM tournament_levels tl
                     WHERE tl.tournament_id = m.tournament_id
                     ORDER BY tl.id DESC LIMIT 1) AS lvl,
                   COALESCE((SELECT tl.surface FROM tournament_levels tl
                              WHERE tl.tournament_id = m.tournament_id
                                AND tl.surface IS NOT NULL
                              ORDER BY tl.id DESC LIMIT 1), 'unknown') AS surface
            FROM prop_live_bets lb
            JOIN prop_tracker p ON p.id = lb.prop_id
            JOIN matches m ON m.id = p.match_id
            LEFT JOIN tournaments t ON t.id = m.tournament_id
            WHERE p.result_status IN ('WON','LOST') AND p.match_date >= ?
            ORDER BY p.match_date, p.id
        """,
        (args.since,),
    ).fetchall()
    classified = [(row, family_for_market(str(row["market_key"])))
                  for row in context_rows]
    rows = [row for row, family in classified if family in LIVE_FAMILIES]
    excluded_by_family: dict[str, int] = {}
    for _, family in classified:
        if family not in LIVE_FAMILIES:
            excluded_by_family[family] = excluded_by_family.get(family, 0) + 1

    clv_by_prop_id = {
        int(row["source_id"]): float(row["clv"])
        for row in conn.execute(
            """
            SELECT c.source_id, c.clv
            FROM clv_tracker c
            JOIN prop_tracker p ON p.id = c.source_id
            WHERE c.recommendation_type = 'PROP_RECOMMENDATION'
              AND p.match_date >= ? AND c.clv IS NOT NULL
            """,
            (args.since,),
        ).fetchall()
    }

    profits = [_profit_for_live_bet(row) for row in rows]
    staked = sum(float(row["stake_units"]) for row in rows)
    roi = (sum(profits) / staked) if staked else None

    state = live_stop_state(
        settled=len(rows),
        pnl_units=round(sum(profits), 2),
        max_drawdown_units=round(_max_drawdown(profits), 2),
        roi=roi,
    )
    verdict = _phase4_verdict(state)

    def family_of(market_key: str) -> str:
        return family_for_market(str(market_key))

    def slice_roi(subset):
        subset_staked = sum(float(r["stake_units"]) for r in subset)
        if not subset_staked:
            return None
        return sum(_profit_for_live_bet(r) for r in subset) / subset_staked

    def slice_clv(subset):
        values = [clv_by_prop_id[int(r["id"])] for r in subset
                  if int(r["id"]) in clv_by_prop_id]
        return {
            "captured": len(values),
            "missing": len(subset) - len(values),
            "average": round(sum(values) / len(values), 4) if values else None,
        }

    breakdown = {}
    for label, key in (("family", lambda r: family_of(r["market_key"])),
                       ("surface", lambda r: r["surface"]),
                       ("tier", lambda r: _tier_of(r["tname"], r["lvl"])),
                       ("pricing_path", lambda r: r["pricing_path"]),
                       ("fixture_source", lambda r: r["fixture_source"]),
                       ("side", lambda r: r["side"])):
        groups: dict = {}
        for row in rows:
            groups.setdefault(key(row), []).append(row)
        breakdown[label] = {
            str(name): {
                "settled": len(subset),
                "roi": round(slice_roi(subset), 4) if slice_roi(subset) is not None else None,
                "p_loss": _p_loss([
                    _profit_for_live_bet(r) for r in subset
                ]),
                "clv": slice_clv(subset),
            }
            for name, subset in sorted(groups.items(), key=lambda kv: -len(kv[1]))
        }

    payload = {
        "window": {"since": args.since, "through": "latest settled row"},
        "row_accounting": {
            "settled_value_recommendations": recommendation_count,
            "recorded_live_bets": recorded_live_bets,
            "settled_live_bets_with_context": len(context_rows),
            "allowlisted_live_rows": len(rows),
            "pending_live_bets": recorded_live_bets - settled_recorded_live_bets,
            "settled_without_match_context": (
                settled_recorded_live_bets - len(context_rows)
            ),
            "excluded_by_family": dict(sorted(excluded_by_family.items())),
        },
        "rule": {
            "stop_drawdown_units": LIVE_STOP_DRAWDOWN_UNITS,
            "review_after_settled": LIVE_REVIEW_AFTER_SETTLED,
            "interim_check_settled": LIVE_INTERIM_CHECK_SETTLED,
            "interim_min_roi": LIVE_INTERIM_MIN_ROI,
        },
        "state": state,
        "verdict": verdict,
        "book": {
            "stake_cap_units": MAX_EARLY_STAKE_UNITS,
            "unit_value_aud": LIVE_UNIT_VALUE_AUD,
            "actual_staked_units": round(staked, 2),
            "actual_staked_aud": round(staked * LIVE_UNIT_VALUE_AUD, 2),
        },
        "p_loss": _p_loss(profits),
        "clv": slice_clv(rows),
        "days": len({row["match_date"] for row in rows}),
        "breakdown": breakdown,
    }

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        accounting = payload["row_accounting"]
        print(f"WINDOW: live staking from {args.since}; prop_tracker contains "
              f"{accounting['settled_value_recommendations']} settled value "
              "recommendations, but the manual live ledger contains "
              f"{accounting['recorded_live_bets']} actual recorded bets; "
              f"{accounting['settled_live_bets_with_context']} are settled with "
              "match context, and the family parser kept "
              f"{accounting['allowlisted_live_rows']} allowlisted rows.")
        if accounting["pending_live_bets"]:
            print(f"Pending recorded live bets: {accounting['pending_live_bets']}")
        if accounting["settled_without_match_context"]:
            print("WARNING: "
                  f"{accounting['settled_without_match_context']} settled live "
                  "bets had no match context and were excluded.")
        if accounting["excluded_by_family"]:
            excluded = ", ".join(
                f"{family}={count}" for family, count
                in accounting["excluded_by_family"].items()
            )
            print(f"Excluded by live-family rule: {excluded}")
        for label, groups in breakdown.items():
            print(f"\nby {label}:")
            for name, stats in groups.items():
                shown = ("--" if stats["roi"] is None else f"{stats['roi']:+.2%}")
                clv = stats["clv"]
                clv_shown = ("--" if clv["average"] is None
                             else f"{clv['average']:+.2%}")
                print(f"  {name:>22} {stats['settled']:5d} {shown:>9}  "
                      f"P(<=0) {stats['p_loss']}  CLV {clv_shown} "
                      f"({clv['captured']}/{stats['settled']})")
        print(f"\nsettled {state['settled']} over {payload['days']} days · "
              f"P/L {state['pnl_units']:+.2f}u / "
              f"A${state['pnl_units'] * LIVE_UNIT_VALUE_AUD:+.2f} AUD · "
              f"ROI {'--' if roi is None else f'{roi:+.2%}'} · "
              f"worst drawdown {state['max_drawdown_units']:+.2f}u")
        print(f"stop at {LIVE_STOP_DRAWDOWN_UNITS:.1f}u · "
              f"review at {LIVE_REVIEW_AFTER_SETTLED} settled "
              f"({state['bets_until_review']} to go)"
              f"{' · REVIEW DUE' if state['review_due'] else ''}")
        overall_clv = payload["clv"]
        overall_clv_shown = ("--" if overall_clv["average"] is None
                             else f"{overall_clv['average']:+.2%}")
        print(f"CLV captured {overall_clv['captured']}/{state['settled']} · "
              f"missing {overall_clv['missing']} · average {overall_clv_shown}")
        print()
        if verdict == "STOP":
            print("STOP — " + "; ".join(state["breaches"]))
        elif verdict == "PAUSE_AND_AUDIT":
            print("PAUSE AND AUDIT — " + "; ".join(state["breaches"]))
        elif verdict == "REVIEW_REQUIRED":
            print("REVIEW REQUIRED — 200 settled bets reached. Do not silently "
                  "continue; write the family/surface/CLV verdict first.")
        else:
            print("CONTINUE ACCUMULATING — no pre-registered threshold has been reached.")

    return {
        "CONTINUE_ACCUMULATING": 0,
        "PAUSE_AND_AUDIT": 2,
        "STOP": 3,
        "REVIEW_REQUIRED": 4,
    }[verdict]


if __name__ == "__main__":
    raise SystemExit(main())
