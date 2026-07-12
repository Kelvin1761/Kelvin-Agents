#!/usr/bin/env python3
"""Replay historical slates through the CURRENT engine — reference only.

Re-prices every stored Sportsbet slate (odds already in the DB; nothing is
re-scraped) with today's code: metadata name-heuristic, Challenger Elo,
chalk chains, retired 穩膽 tier, prop two-way pricing. Results are settled
against match_results where available and aggregated per structure.

READ-MOSTLY BY DESIGN:
- writes NOTHING to predictions / prop_tracker / clv_tracker / combo_tracker
  (props priced with log=False; filter results stay in memory);
- the only DB write is backfill_confirmed_metadata_for_date (idempotent,
  current-code metadata — the same thing run-daily does);
- the archived daily folders are the record of what was ACTUALLY advised and
  are never touched; output goes to a separate Replay Review folder.

HONESTY CAVEAT (printed in the report): players' Elo is TODAY's rating built
over the full history INCLUDING these matches and later ones, so match-winner
model probabilities are look-ahead-contaminated (optimistic). The prop models
are leakage-safe (profiles use strictly-before-date history; calibration
curves were fit on pre-period seasons). Chalk chains are market-odds-driven
with the model only as a veto, so contamination there is second-order.

Usage:
  DATA_MAX_STALENESS_MINUTES_ODDS=99999999 PYTHONPATH=src \
      .venv/bin/python scripts/replay_review.py [--limit-dates N]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from itertools import combinations
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from tennis_wc.database.db import get_connection  # noqa: E402
from tennis_wc.features.feature_builder import build_sportsbet_feature_snapshots_for_date  # noqa: E402
from tennis_wc.ingestion.confirmed_metadata import backfill_confirmed_metadata_for_date  # noqa: E402
from tennis_wc.modelling.pricing import price_match_snapshot  # noqa: E402
from tennis_wc.betting.bet_filter import apply_bet_filter  # noqa: E402
from tennis_wc.props.daily import price_ace_props_for_date  # noqa: E402
from tennis_wc.props.settlement import actual_total_aces, actual_player_aces, actual_total_games  # noqa: E402

_CHALK_MIN_ODDS, _CHALK_MAX_ODDS = 1.05, 1.20
_CHALK_MIN_PROB, _CHALK_MIN_CONF = 0.52, 65
_CHALK_EXCLUDE_RE = re.compile(r"\b(challenger|itf|futures|utr|doubles)\b", re.IGNORECASE)


def _match_index(conn, match_date: str) -> dict[int, dict]:
    rows = conn.execute(
        """
        SELECT m.id, m.player_a_id, m.player_b_id, t.name AS tournament_name,
               p1.name AS player_a_name, p2.name AS player_b_name,
               (SELECT r.winner_player_id FROM match_results r WHERE r.match_id = m.id
                ORDER BY CASE WHEN r.source_provider='tennismylife' THEN 0 ELSE 1 END, r.id DESC LIMIT 1
               ) AS winner_player_id
        FROM matches m
        JOIN tournaments t ON t.id = m.tournament_id
        JOIN players p1 ON p1.id = m.player_a_id
        JOIN players p2 ON p2.id = m.player_b_id
        WHERE m.match_date = ?
        """,
        (match_date,),
    ).fetchall()
    return {int(r["id"]): dict(r) for r in rows}


def _grade(units: list[tuple[float, float, bool | None]]) -> dict:
    """units: (stake, odds, won|None). Returns settled aggregates."""
    settled = [(s, o, w) for s, o, w in units if w is not None]
    staked = sum(s for s, _, _ in settled)
    pnl = sum(s * (o - 1) if w else -s for s, o, w in settled)
    return {
        "picks": len(units),
        "settled": len(settled),
        "wins": sum(1 for _, _, w in settled if w),
        "staked": round(staked, 2),
        "pnl": round(pnl, 3),
        "roi": round(pnl / staked, 4) if staked else None,
    }


def replay_date(match_date: str) -> dict:
    backfill_confirmed_metadata_for_date(match_date)
    snaps = build_sportsbet_feature_snapshots_for_date(match_date)
    conn = get_connection()
    idx = _match_index(conn, match_date)

    decisions: dict[str, int] = {}
    bet_singles: list[dict] = []
    chalk_legs: list[dict] = []
    for snap in snaps:
        match_id = int(snap["match_id"]["value"])
        info = idx.get(match_id) or {}
        pricing = price_match_snapshot(snap)
        fr = apply_bet_filter(snap, pricing)
        decisions[fr["decision"]] = decisions.get(fr["decision"], 0) + 1
        side = pricing.get("selection_side")
        sel_player_id = info.get("player_a_id") if side == "player_a" else info.get("player_b_id")
        winner = info.get("winner_player_id")
        won = None if winner is None or sel_player_id is None else (winner == sel_player_id)
        odds = pricing.get("current_market_odds")
        if fr["decision"] == "BET" and odds:
            bet_singles.append(
                {
                    "date": match_date,
                    "selection": pricing.get("selection_name"),
                    "odds": float(odds),
                    "prob": pricing.get("adjusted_model_probability") or pricing.get("model_probability"),
                    "edge": pricing.get("edge"),
                    "won": won,
                }
            )
        # Chalk qualification: per side, market favourite within the band.
        market = snap.get("market", {})
        tname = str(info.get("tournament_name") or "")
        if not _CHALK_EXCLUDE_RE.search(tname):
            for cand_side, odds_key in (("player_a", "player_a_odds"), ("player_b", "player_b_odds")):
                point = market.get(odds_key) or {}
                c_odds = point.get("value")
                if c_odds is None or not (_CHALK_MIN_ODDS <= float(c_odds) <= _CHALK_MAX_ODDS):
                    continue
                model = pricing.get("model", {})
                p_a = model.get("player_a_probability")
                if p_a is None:
                    continue
                c_prob = float(p_a) if cand_side == "player_a" else 1 - float(p_a)
                if c_prob <= _CHALK_MIN_PROB or int(fr.get("confidence") or 0) < _CHALK_MIN_CONF:
                    continue
                pid = info.get("player_a_id") if cand_side == "player_a" else info.get("player_b_id")
                c_won = None if info.get("winner_player_id") is None else (info["winner_player_id"] == pid)
                name = info.get("player_a_name") if cand_side == "player_a" else info.get("player_b_name")
                chalk_legs.append({"match_id": match_id, "name": name, "odds": float(c_odds), "prob": c_prob, "won": c_won})

    # One leg per match (highest prob), then greedy disjoint 3-leg chains + a 2-leg tail.
    best: dict[int, dict] = {}
    for leg in chalk_legs:
        if leg["match_id"] not in best or leg["prob"] > best[leg["match_id"]]["prob"]:
            best[leg["match_id"]] = leg
    legs = sorted(best.values(), key=lambda r: -r["prob"])
    chains: list[list[dict]] = []
    i = 0
    while len(legs) - i >= 3:
        chains.append(legs[i : i + 3]); i += 3
    if len(legs) - i == 2:
        chains.append(legs[i : i + 2])
    chain_units: list[tuple[float, float, bool | None]] = []
    chain_rows: list[dict] = []
    for grp in chains:
        odds = 1.0
        won: bool | None = True
        for leg in grp:
            odds *= leg["odds"]
            if leg["won"] is None:
                won = None
            elif won is not None and not leg["won"]:
                won = False
        chain_units.append((1.0, odds, won))
        chain_rows.append({"legs": [f"{l['name']} @{l['odds']}" for l in grp], "odds": round(odds, 3), "won": won})

    # Props (leakage-safe): value sides only (same rule as the engine:
    # value_side present, edge >= 0.04, EV > 0), flat 1u, no tracker writes.
    prop_units: list[tuple[float, float, bool | None]] = []
    prop_rows: list[dict] = []
    try:
        boards = price_ace_props_for_date(conn, match_date, log=False)
    except Exception:
        boards = []
    for board in boards:
        mid = board.match_id
        info = idx.get(mid) or {}
        groups = (
            ("match_aces", board.match_ou),
            ("player_aces", board.player_ou),
            ("match_games", board.games_ou),
        )
        for kind, tws in groups:
            for tw in tws or []:
                side = tw.value_side
                odds = tw.value_odds
                if not side or not odds or tw.edge < 0.04 or tw.ev <= 0:
                    continue
                if kind == "match_aces":
                    actual = actual_total_aces(conn, mid)
                elif kind == "match_games":
                    actual = actual_total_games(conn, mid)
                else:
                    # scope holds the PLAYER NAME for player-level props.
                    pid = None
                    for id_key, name_key in (("player_a_id", "player_a_name"), ("player_b_id", "player_b_name")):
                        if str(info.get(name_key) or "").lower() == str(tw.scope or "").lower():
                            pid = info.get(id_key)
                            break
                    actual = actual_player_aces(conn, mid, pid) if pid is not None else None
                line = float(tw.line)
                won = None if actual is None else (actual >= line if side == "over" else actual < line)
                prop_units.append((1.0, float(odds), won))
                prop_rows.append({"market": tw.market_key, "kind": kind, "side": side, "line": line, "odds": float(odds), "won": won})

    return {
        "date": match_date,
        "snapshots": len(snaps),
        "decisions": decisions,
        "bet_singles": bet_singles,
        "chalk_chains": chain_rows,
        "chalk_units": chain_units,
        "prop_rows": prop_rows,
        "prop_units": prop_units,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-dates", type=int, default=0)
    args = parser.parse_args()
    with get_connection() as conn:
        dates = [
            r["match_date"]
            for r in conn.execute(
                """
                SELECT DISTINCT m.match_date FROM matches m
                JOIN odds_snapshots o ON o.match_id = m.id
                WHERE o.source_provider = 'sportsbet'
                ORDER BY m.match_date
                """
            ).fetchall()
        ]
    if args.limit_dates:
        dates = dates[-args.limit_dates:]
    results = []
    for d in dates:
        try:
            res = replay_date(d)
        except Exception as exc:  # noqa: BLE001 - one bad date must not kill the replay
            res = {"date": d, "error": str(exc)}
        results.append(res)
        print(json.dumps({k: v for k, v in res.items() if k in ("date", "snapshots", "decisions", "error")}), flush=True)

    ok = [r for r in results if "error" not in r]
    singles_units = [(1.0, b["odds"], b["won"]) for r in ok for b in r["bet_singles"]]
    chalk_units = [u for r in ok for u in r["chalk_units"]]
    prop_units = [u for r in ok for u in r["prop_units"]]
    summary = {
        "dates": len(results),
        "dates_failed": len(results) - len(ok),
        "match_winner_bet_singles(LEAKY_ELO)": _grade(singles_units),
        "chalk_chains_flat1u": _grade(chalk_units),
        "prop_value_flat1u(leakage_safe)": _grade(prop_units),
    }
    print(json.dumps({"summary": summary}, ensure_ascii=False, indent=2))

    out_dir = PROJECT_DIR.parent / "Wong Choi Tennis Analysis" / "2026-07-12 Replay Review"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summary, "per_date": results}
    (out_dir / "replay_results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    print(f"written: {out_dir / 'replay_results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
