"""EXP-20261110-03: frozen evaluation of two NBA 大細盤 under paper arms (forward only).

Both arms bet the UNDER of a Sportsbet two-way player line (O/U .5), flat 1 unit, on paper:

  FU_AVG   the line sits more than 5% above the player's last-10 average
           (mean(L10) - ou_line) / max(ou_line, 1) < -0.05, L10 needs >= 5 games
  FU_EDGE  the published model disagrees with the de-vigged price by >= 8pp
           fair_over - p_final >= 0.08, p_final of the milestone leg ceil(ou_line)+

Everything comes from the market ledger, as recorded before tip-off:
  model   latest pre-tip `production` model_obs of the leg (p_final, L10 values)
  price   latest two-way price_obs captured at or before the odds that model run saw
  result  the ledger settlement of the same player and market (void = no bet)

Each arm is judged once, on its first N settled bets, and the result is frozen.
PASS needs the flat-stake ROI lower bound > 0 on a 97.5% day-clustered bootstrap CI
(two arms, Bonferroni). Nothing here places a bet or changes the model.

usage:
  python3 evaluate.py status            -> counts only (never a hit rate or ROI)
  python3 evaluate.py evaluate [--force]

Protocol: docs/experiments/EXP-20261110-03-nba-ou-under-arms-forward-protocol.md.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

EXPERIMENT = "EXP-20261110-03"
START = "2026-11-11"
SEED, DRAWS = 20261111, 2000
ALPHA = 0.025                      # two arms -> 97.5% CI each
LOOKS = {"FU_AVG": 1200, "FU_EDGE": 300}
AVG_GAP = -0.05
MIN_L10 = 5
MIN_EDGE = 0.08
LEDGER = Path.home() / "WongChoiData" / "NBA_Market_Eval" / "ledger"
REPORTS = Path.home() / "WongChoiData" / "NBA_Market_Eval" / "reports"


def _time(text) -> datetime | None:
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def day_bets(rows: list[dict]) -> list[dict]:
    """Every qualifying under bet of one target date (settled or not), both arms."""
    model: dict[tuple, dict] = {}        # (game, player, market, line) -> latest production row
    prices: dict[tuple, list] = defaultdict(list)   # (game, player, market, ou_line) -> [(t, over, under)]
    actual: dict[tuple, dict] = {}       # (game, player, market) -> settlement
    for r in rows:
        kind = r.get("row_type")
        if kind == "model_obs":
            if r.get("post_tip") or r.get("snapshot_role") != "production" or r.get("p_final") is None:
                continue
            key = (r.get("game_tag"), r.get("player"), r.get("market"), float(r["line"]))
            if key not in model or str(r.get("recorded_at")) > str(model[key].get("recorded_at")):
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
    bets = []
    for (game, player, market, ou_line), obs in sorted(prices.items(), key=lambda kv: tuple(map(str, kv[0]))):
        if float(ou_line).is_integer():
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
        l10 = (((leg.get("prop_training") or {}).get("inputs") or {}).get("l10_values")) or []
        arms = []
        if len(l10) >= MIN_L10 and (sum(l10) / len(l10) - ou_line) / max(ou_line, 1.0) < AVG_GAP:
            arms.append("FU_AVG")
        if fair_over - float(leg["p_final"]) >= MIN_EDGE:
            arms.append("FU_EDGE")
        if not arms:
            continue
        s = actual.get((game, player, market))
        state = "pending"
        if s is not None:
            state = ("void" if s.get("outcome") == "void" or s.get("actual") is None
                     else "won" if float(s["actual"]) < ou_line else "lost")
        bets.append({"day": leg.get("target_date"), "id": f"{game}|{player}|{market}|{ou_line:g}",
                     "arms": arms, "odds": under, "state": state})
    return bets


def _read(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if '"model_obs"' in line or '"ou_two_way"' in line or '"settlement"' in line:
                rows.append(json.loads(line))
    return rows


def records(ledger: Path | None = None, cache_dir: Path | None = None) -> list[dict]:
    """All bets from START on. A day's bets are cached against its ledger file's size and mtime."""
    ledger = Path(ledger or LEDGER)
    cache_path = Path(cache_dir or REPORTS) / f"{EXPERIMENT}-bets-cache.json"
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
            entry = {"stamp": stamp, "bets": day_bets(_read(path))}
        fresh[path.stem] = entry
        out.extend(entry["bets"])
    if fresh != cache:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(fresh), encoding="utf-8")
        except OSError:
            pass
    return out


def settled(rows: list[dict], arm: str) -> list[dict]:
    return sorted((r for r in rows if arm in r["arms"] and r["state"] in ("won", "lost")),
                  key=lambda r: (r["day"], r["id"]))


def roi(rows: list[dict]) -> float:
    return sum((r["odds"] - 1) if r["state"] == "won" else -1.0 for r in rows) / len(rows)


def boot(rows: list[dict]) -> tuple[float, float]:
    """Resample whole days: one slate shares news, pace and one model run."""
    days = defaultdict(list)
    for r in rows:
        days[r["day"]].append(r)
    keys = sorted(days)
    rnd = random.Random(SEED)
    vals = sorted(roi([x for k in (rnd.choice(keys) for _ in keys) for x in days[k]]) for _ in range(DRAWS))
    return vals[int(ALPHA / 2 * DRAWS)], vals[int((1 - ALPHA / 2) * DRAWS) - 1]


def status(ledger=None, analysis=None, *, rows: list[dict] | None = None) -> dict:
    rows = records(ledger) if rows is None else rows
    return {arm: {"bets": len(settled(rows, arm)), "checkpoint": {"bets": need},
                  "ready": len(settled(rows, arm)) >= need} for arm, need in LOOKS.items()}


def judge(arm: str, rows: list[dict]) -> dict:
    done = settled(rows, arm)[:LOOKS[arm]]          # exactly the first N
    lo, hi = boot(done)
    return {"experiment": EXPERIMENT, "test": arm, "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "n_bets": len(done), "days": len({r["day"] for r in done}), "roi": roi(done),
            "ci95": [lo, hi], "ci_level": 1 - ALPHA,
            "hit_rate": sum(r["state"] == "won" for r in done) / len(done), "pass": lo > 0}


def evaluate(ledger=None, analysis=None, out_dir: Path | None = None, *, force=False, only=None,
             rows: list[dict] | None = None) -> dict:
    out_dir = Path(out_dir or REPORTS)
    rows = records(ledger) if rows is None else rows
    results = {}
    for arm, need in LOOKS.items():
        if only and arm != only:
            continue
        path = out_dir / f"{EXPERIMENT}-{arm}-result.json"
        if path.is_file() and not force:
            results[arm] = json.loads(path.read_text(encoding="utf-8"))
            continue
        n = len(settled(rows, arm))
        if n < need:
            results[arm] = {"status": "not_ready", "bets": n, "checkpoint": need}
            continue
        results[arm] = judge(arm, rows)
        out_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(results[arm], ensure_ascii=False, indent=1), encoding="utf-8")
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("status", "evaluate"))
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if a.mode == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(evaluate(out_dir=a.out, force=a.force), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
