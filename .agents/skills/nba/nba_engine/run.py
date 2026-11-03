"""Analyse one game: Sportsbet odds + ESPN package -> report, sidecar and (maybe) a banker.

usage: python3 -m nba_engine.run --sportsbet <Sportsbet_Odds_TAG.json> \
           --extractor <nba_game_data_TAG.json> --output <Game_TAG_Full_Analysis.md>

Same arguments and outputs as the retired generate_nba_reports.py, so the orchestrator,
ledger, reflector and dashboard keep working unchanged.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):          # `python3 nba_engine/run.py` as well as `-m`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "nba_engine"

from nba_sgm_quote import quote_combo, quote_valid  # noqa: E402
import nba_steady_policy  # noqa: E402

from . import report  # noqa: E402
from .banker import select_b2  # noqa: E402
from .legs import MARKET, build_legs  # noqa: E402

MIN_SGM_PRICE = 2.0


def quote_payload(legs):
    return [{"player": l.player, "market": MARKET[l.stat], "line": l.line, "side": "over"} for l in legs]


def analyse(odds: dict, package: dict, *, quote=quote_combo, valid=quote_valid, paused=None):
    """(legs, combo, quote or None, diagnostics). The combo is non-empty only with a valid
    Sportsbet SGM quote >= 2.0 and the steady stop-loss not paused."""
    legs, skipped = build_legs(odds, package)
    combo, rule = select_b2(legs, (package.get("meta") or {}).get("season_phase"))
    diagnostics = {"rule": rule, "skipped": skipped, "candidates": len(legs),
                   "flags": dict(Counter(f for l in legs for f in l.flags))}
    q = None
    if paused:
        combo, diagnostics["no_bet_reason"] = [], f"steady_paused:{paused}"
    elif not combo:
        diagnostics["no_bet_reason"] = "no_b2_combo"
    else:
        payload = quote_payload(combo)
        q = quote(odds, payload).quote
        if not valid(q, odds, payload) or (q.get("decimal_odds") or 0) < MIN_SGM_PRICE:
            diagnostics["no_bet_reason"] = f"quote_rejected:{q.get('status')}:{q.get('decimal_odds')}"
            combo = []
    return legs, combo, q, diagnostics


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sportsbet", required=True)
    parser.add_argument("--extractor", required=True)
    parser.add_argument("--output", required=True)
    args, _ = parser.parse_known_args(argv)   # tolerate the old generator's extra flags
    odds = json.loads(Path(args.sportsbet).read_text(encoding="utf-8"))
    package = json.loads(Path(args.extractor).read_text(encoding="utf-8"))
    paused = nba_steady_policy.paused_reason()
    legs, combo, q, diagnostics = analyse(odds, package, paused=paused)
    text = report.render(odds, package, legs, combo, q, diagnostics, paused=paused)
    report.write(args.output, text, report.sidecar(text, odds, package, legs, combo, q, diagnostics))
    banker = " + ".join(l.desc for l in combo) if combo else f"NO BET ({diagnostics['no_bet_reason']})"
    print(f"{odds['away_team']}@{odds['home_team']}: {len(legs)} legs, banker={banker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
