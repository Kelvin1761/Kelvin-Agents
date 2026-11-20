"""EXP-20261120-60: frozen paper arm 大細盤精選 v2 (forward only, never published).

v1 (EXP-20261110-01) borrows the milestone leg's p_final as the model's P(over) of an O/U line.
On 2,149 settled O/U lines (2026-11-05..11-19) that probability averaged 45.2% against an actual
over rate of 48.9% (de-vigged price 48.7%): the model sits low on every over, so v1 has picked an
under 46 times out of 46.

v2 changes two things, both frozen here:
  1. P(over) = sigmoid(logit(clip(p_final)) + DELTA[stat]); DELTA was fitted once on those 2,149
     lines so the mean matches the actual over rate, and never moves.
  2. lines at or below 1.5 are left out (5 of v1's 6 voids were Sportsbet pulling such a market).
  3. edge >= 0.03 (v1: 0.05). With the bias removed 5pp edges are rare (1.1 bets a day on 11-05..11-19);
     3pp gives 4.7 a day, 40 overs and 30 unders. Chosen from bet counts only, never from results.
Everything else is v1's rule: both sides, de-vig proportionally, price <= 3.0, the best edge per game,
at most 10 a day, flat 1 unit, void = no bet.

Everything comes from the market ledger as recorded before tip-off:
  model   first pre-tip `production` model_obs of the milestone leg ceil(ou_line)+ (the 21:00 run)
  price   latest pre-tip two-way price_obs captured at or before the odds that model run saw
  result  the ledger settlement of the same player and market

Looks (each judged once on the first N settled bets, frozen):
  V2_250   interim: STOP if the flat-stake ROI 95% CI upper bound < 0; never passes
  V2_600   final: PASS if the 95% CI lower bound > 0 (about what the rest of the regular season gives)
Day-clustered bootstrap, 2,000 draws, seed 20261120. Nothing here places a bet or changes v1.

usage:
  python3 evaluate.py status
  python3 evaluate.py evaluate [--force]

Protocol: docs/experiments/EXP-20261120-60-nba-featured-v2-shadow-protocol.md.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

EXPERIMENT = "EXP-20261120-60"
START = "2026-11-21"
SEED, DRAWS = 20261120, 2000
LOOKS = {"V2_250": 250, "V2_600": 600}
DELTA = {"pts": 0.3889, "reb": 0.0493, "ast": 0.2715, "fg3m": 0.0853}
STAT = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "3PM"}
CLIP = (0.02, 0.98)
MIN_EDGE, MAX_PRICE, MAX_LINE_EXCLUDED, DAILY_LIMIT = 0.03, 3.0, 1.5, 10
LEDGER = Path.home() / "WongChoiData" / "NBA_Market_Eval" / "ledger"
REPORTS = Path.home() / "WongChoiData" / "NBA_Market_Eval" / "reports"


def _time(text) -> datetime | None:
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def p_over(market: str, p_final: float) -> float:
    p = min(max(float(p_final), CLIP[0]), CLIP[1])
    return 1.0 / (1.0 + math.exp(-(math.log(p / (1 - p)) + DELTA[market])))


def day_picks(rows: list[dict]) -> list[dict]:
    """v2 picks of one target date (settled or not), after the daily cap."""
    model: dict[tuple, dict] = {}
    prices: dict[tuple, list] = defaultdict(list)
    actual: dict[tuple, dict] = {}
    for r in rows:
        kind = r.get("row_type")
        if kind == "model_obs":
            if (r.get("post_tip") or r.get("snapshot_role") != "production" or r.get("p_final") is None
                    or r.get("market") not in DELTA or r.get("line") is None):
                continue
            key = (r.get("game_tag"), r.get("player"), r.get("market"), float(r["line"]))
            if key not in model or str(r.get("recorded_at")) < str(model[key].get("recorded_at")):
                model[key] = r
        elif kind == "price_obs" and r.get("price_source") == "ou_two_way":
            if r.get("post_tip") or r.get("tip_unknown") or r.get("ou_line") is None:
                continue
            t, price, other = _time(r.get("captured_at")), r.get("price"), r.get("complement_price")
            if t is None or not price or not other:
                continue
            over, under = (price, other) if r.get("side") == "over" else (other, price)
            prices[(r.get("game_tag"), r.get("player"), r.get("market"), float(r["ou_line"]))].append(
                (t, float(over), float(under)))
        elif kind == "settlement":
            actual.setdefault((r.get("game_tag"), r.get("player"), r.get("market")), r)
    best: dict[str, dict] = {}
    for (game, player, market, ou_line), obs in sorted(prices.items(), key=lambda kv: tuple(map(str, kv[0]))):
        if float(ou_line).is_integer() or ou_line <= MAX_LINE_EXCLUDED:
            continue
        leg = model.get((game, player, market, float(math.ceil(ou_line))))
        if leg is None:
            continue
        seen = _time(leg.get("odds_captured_at"))
        usable = [o for o in obs if seen is not None and o[0] <= seen]
        if not usable:
            continue
        _, over, under = max(usable, key=lambda o: o[0])
        if over < 1.01 or under < 1.01:
            continue
        fair_over = (1 / over) / (1 / over + 1 / under)
        model_over = p_over(market, leg["p_final"])
        for side, price, p_model, fair in (("over", over, model_over, fair_over),
                                           ("under", under, 1 - model_over, 1 - fair_over)):
            edge = p_model - fair
            if edge < MIN_EDGE or price > MAX_PRICE:
                continue
            pick = {"day": leg.get("target_date"), "game_tag": game, "player": player, "market": market,
                    "stat": STAT[market], "ou_line": ou_line, "side": side, "odds": price,
                    "p_model": round(p_model, 4), "p_fair": round(fair, 4), "edge": round(edge, 4)}
            key = (pick["edge"], player, market, -ou_line, side)
            if game not in best or key > best[game]["_key"]:
                best[game] = {**pick, "_key": key}
    picks = sorted(best.values(), key=lambda p: (-p["edge"], str(p["game_tag"]), p["player"]))[:DAILY_LIMIT]
    out = []
    for p in picks:
        p.pop("_key")
        s = actual.get((p["game_tag"], p["player"], p["market"]))
        if s is None:
            state, value = "pending", None
        elif s.get("outcome") == "void" or s.get("actual") is None:
            state, value = "void", None
        else:
            value = float(s["actual"])
            won = value > p["ou_line"] if p["side"] == "over" else value < p["ou_line"]
            state = "won" if won else "lost"
        profit = round(p["odds"] - 1, 4) if state == "won" else -1.0 if state == "lost" else None
        out.append({**p, "id": f"{p['day']}|{p['game_tag']}", "actual": value, "state": state, "profit": profit})
    return out


def _read(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if '"model_obs"' in line or '"ou_two_way"' in line or '"settlement"' in line:
                rows.append(json.loads(line))
    return rows


def records(ledger: Path | None = None, cache_dir: Path | None = None) -> list[dict]:
    """All v2 picks from START on; a day is cached against its ledger file's size and mtime."""
    ledger = Path(ledger or LEDGER)
    cache_path = Path(cache_dir or REPORTS) / f"{EXPERIMENT}-picks-cache.json"
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    out, fresh = [], {}
    for path in sorted(ledger.glob("*.jsonl")):
        if path.stem < START:
            continue
        stat = path.stat()
        stamp = [stat.st_size, stat.st_mtime_ns]
        entry = cache.get(path.stem)
        if not entry or entry.get("stamp") != stamp:
            entry = {"stamp": stamp, "picks": day_picks(_read(path))}
        fresh[path.stem] = entry
        out.extend(entry["picks"])
    if fresh != cache:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(fresh), encoding="utf-8")
        except OSError:
            pass
    return out


def settled(rows: list[dict]) -> list[dict]:
    return sorted((r for r in rows if r["state"] in ("won", "lost")), key=lambda r: (r["day"], r["id"]))


def roi(rows: list[dict]) -> float:
    return sum(r["profit"] for r in rows) / len(rows)


def boot(rows: list[dict]) -> tuple[float, float]:
    days = defaultdict(list)
    for r in rows:
        days[r["day"]].append(r)
    keys = sorted(days)
    rnd = random.Random(SEED)
    vals = sorted(roi([x for k in (rnd.choice(keys) for _ in keys) for x in days[k]]) for _ in range(DRAWS))
    return vals[int(0.025 * DRAWS)], vals[int(0.975 * DRAWS) - 1]


def status(ledger=None, analysis=None, *, rows: list[dict] | None = None) -> dict:
    n = len(settled(records(ledger) if rows is None else rows))
    return {name: {"bets": n, "checkpoint": {"bets": need}, "ready": n >= need} for name, need in LOOKS.items()}


def judge(name: str, rows: list[dict]) -> dict:
    done = settled(rows)[:LOOKS[name]]
    lo, hi = boot(done)
    out = {"experiment": EXPERIMENT, "test": name, "evaluated_at": datetime.now(timezone.utc).isoformat(),
           "n_bets": len(done), "days": len({r["day"] for r in done}), "roi": roi(done), "ci95": [lo, hi],
           "hit_rate": sum(r["state"] == "won" for r in done) / len(done),
           "by_side": {s: {"n": len(x), "roi": roi(x) if x else None}
                       for s in ("over", "under") for x in [[r for r in done if r["side"] == s]]}}
    if name == "V2_250":
        out["stop"], out["pass"] = hi < 0, False
    else:
        out["pass"] = lo > 0
    return out


def evaluate(ledger=None, analysis=None, out_dir: Path | None = None, *, force=False, only=None,
             rows: list[dict] | None = None) -> dict:
    out_dir = Path(out_dir or REPORTS)
    rows = records(ledger) if rows is None else rows
    results = {}
    for name, need in LOOKS.items():
        if only and name != only:
            continue
        path = out_dir / f"{EXPERIMENT}-{name}-result.json"
        if path.is_file() and not force:
            results[name] = json.loads(path.read_text(encoding="utf-8"))
            continue
        if len(settled(rows)) < need:
            results[name] = {"status": "not_ready", "bets": len(settled(rows)), "checkpoint": need}
            continue
        results[name] = judge(name, rows)
        out_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(results[name], ensure_ascii=False, indent=1), encoding="utf-8")
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("status", "evaluate"))
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    out = status() if a.mode == "status" else evaluate(out_dir=a.out, force=a.force)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
