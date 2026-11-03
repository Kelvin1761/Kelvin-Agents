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
from pathlib import Path

if __package__ in (None, ""):          # `python3 nba_engine/run.py` as well as `-m`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "nba_engine"

from nba_sgm_quote import quote_combo, quote_valid  # noqa: E402
import nba_steady_policy  # noqa: E402

from . import report  # noqa: E402
from .legs import MARKET, build_legs  # noqa: E402
from .select import Policy, select  # noqa: E402

POLICY = Policy()


def quote_payload(legs):
    return [{"player": l.player, "market": MARKET[l.stat], "line": l.line, "side": "over"} for l in legs]


def analyse(odds: dict, package: dict, policy: Policy = POLICY, *, quote=quote_combo, valid=quote_valid,
            paused=None):
    legs, skipped = build_legs(odds, package)
    combo, diagnostics = select(legs, policy)
    diagnostics["skipped"] = skipped
    q = None
    if paused:
        combo, diagnostics["no_bet_reason"] = [], f"steady_paused:{paused}"
    elif not combo:
        diagnostics["no_bet_reason"] = "no_combo_in_price_range"
    else:
        payload = quote_payload(combo)
        q = quote(odds, payload).quote
        if not valid(q, odds, payload) or (q.get("decimal_odds") or 0) < policy.min_price:
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
    legs, combo, q, diagnostics = analyse(odds, package, paused=nba_steady_policy.paused_reason())
    text = report.render(odds, package, legs, combo, q, POLICY, diagnostics, paused=nba_steady_policy.paused_reason())
    report.write(args.output, text, report.sidecar(text, odds, package, legs, combo, q, POLICY, diagnostics))
    print(f"{odds['away_team']}@{odds['home_team']}: {len(legs)} legs, "
          f"banker={'NO BET (' + diagnostics.get('no_bet_reason', '') + ')' if not combo else ' + '.join(l.desc for l in combo)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
