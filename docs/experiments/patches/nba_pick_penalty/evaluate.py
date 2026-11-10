"""EXP-20261111-01: do the legs the banker picks hit less often than the model says? (forward only)

Background (exploratory, 2026-10-22..11-10): over every leg priced 1.20-1.60 the published
probability is calibrated (2,897 legs: actual 66.4% vs model 65.1%), and it stays calibrated
among legs with L10 and L5 hit rates >= 80%. Only the legs that ended up in the published banker
fall short (214 legs: 67.3% vs 73.8%). That points at the selection, not the formula.

Test P, from the market ledger only, target dates from START:

  picked    legs of the first pre-tip `production` banker (sgm_obs combo "1") of each game
  control   legs the banker could have used but did not: first pre-tip production model_obs,
            price 1.20-1.60, L10 and L5 hit rate >= 80%, one line per player and stat (the
            highest), never a leg of that game's banker
  residual  y - p_final (y from the ledger settlement of that exact leg; void legs dropped)
  primary   mean residual(picked) - mean residual(control)

Judged once, at the end of the first day on which 400 picked legs over at least 20 days are
settled; 95% CI from a day-clustered bootstrap. PASS = CI upper bound < 0: being picked costs
hit rate beyond what the model already says. Nothing here changes the banker or the model.

usage:
  python3 evaluate.py status
  python3 evaluate.py evaluate [--force]

Protocol: docs/experiments/EXP-20261111-01-nba-banker-pick-penalty-forward-protocol.md.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

EXPERIMENT = "EXP-20261111-01"
START = "2026-11-12"             # first target date after the banker resumed (2026-11-11)
SEED, DRAWS = 20261111, 2000
CHECKPOINT = {"days": 20, "flagged_legs": 400}
PRICE = (1.20, 1.60)
MIN_HIT = 0.8
LEDGER = Path.home() / "WongChoiData" / "NBA_Market_Eval" / "ledger"
REPORTS = Path.home() / "WongChoiData" / "NBA_Market_Eval" / "reports"


def _key(game, player, market, line) -> tuple:
    return (game, player, market, float(line))


def day_legs(rows: list[dict]) -> list[dict]:
    """Settled picked and control legs of one target date."""
    banker: dict[str, dict] = {}                 # game -> first production combo 1
    model: dict[tuple, dict] = {}                # leg -> first production model row
    result: dict[tuple, dict] = {}
    for r in rows:
        kind = r.get("row_type")
        if r.get("post_tip"):
            continue
        if kind == "sgm_obs":
            if r.get("snapshot_role") != "production" or str(r.get("combo_id")) != "1":
                continue
            game = r.get("game_tag")
            if game not in banker or str(r.get("recorded_at")) < str(banker[game].get("recorded_at")):
                banker[game] = r
        elif kind == "model_obs":
            if r.get("snapshot_role") != "production" or r.get("p_final") is None or r.get("line") is None:
                continue
            key = _key(r.get("game_tag"), r.get("player"), r.get("market"), r["line"])
            if key not in model or str(r.get("recorded_at")) < str(model[key].get("recorded_at")):
                model[key] = r
        elif kind == "settlement" and r.get("line") is not None:
            result.setdefault(_key(r.get("game_tag"), r.get("player"), r.get("market"), r["line"]), r)

    def settled(key):
        s = result.get(key)
        return None if s is None or s.get("y") is None else s

    out, picked_keys = [], set()
    for game, combo in banker.items():
        for leg in combo.get("legs") or []:
            if leg.get("p_final") is None or leg.get("line") is None:
                continue
            key = _key(game, leg.get("player"), leg.get("market"), leg["line"])
            picked_keys.add(key)
            s = settled(key)
            if s is not None:
                out.append({"day": combo.get("target_date"), "group": "picked", "market": key[2],
                            "p": float(leg["p_final"]), "y": int(s["y"]),
                            "near_miss": s.get("actual") is not None and float(s["actual"]) == key[3] - 1})
    best: dict[tuple, tuple] = {}                # (game, player, market) -> (line, row)
    for key, r in model.items():
        inputs = ((r.get("prop_training") or {}).get("inputs") or {})
        try:
            price, h10, h5 = float(r.get("price_at_model")), float(inputs.get("hit_l10")), float(inputs.get("hit_l5"))
        except (TypeError, ValueError):
            continue
        if not (PRICE[0] <= price <= PRICE[1]) or h10 < MIN_HIT or h5 < MIN_HIT or key in picked_keys:
            continue
        if key[:3] not in best or key[3] > best[key[:3]][0]:
            best[key[:3]] = (key[3], r)
    for (game, player, market), (line, r) in best.items():
        s = settled(_key(game, player, market, line))
        if s is not None:
            out.append({"day": r.get("target_date"), "group": "control", "market": market,
                        "p": float(r["p_final"]), "y": int(s["y"]),
                        "near_miss": s.get("actual") is not None and float(s["actual"]) == line - 1})
    return sorted(out, key=lambda x: (str(x["day"]), x["group"], x["market"], x["p"], x["y"]))


def _read(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if '"sgm_obs"' in line or '"model_obs"' in line or '"settlement"' in line:
                rows.append(json.loads(line))
    return rows


def load(ledger: Path | None = None, cache_dir: Path | None = None) -> list[dict]:
    ledger = Path(ledger or LEDGER)
    cache_path = Path(cache_dir or REPORTS) / f"{EXPERIMENT}-legs-cache.json"
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
            entry = {"stamp": stamp, "legs": day_legs(_read(path))}
        fresh[path.stem] = entry
        out.extend(entry["legs"])
    if fresh != cache:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(fresh), encoding="utf-8")
        except OSError:
            pass
    return out


def window(legs: list[dict]) -> list[dict]:
    """Whole days, up to and including the day the checkpoint is first met."""
    days, picked = [], 0
    for day in sorted({x["day"] for x in legs}):
        days.append(day)
        picked += sum(x["day"] == day and x["group"] == "picked" for x in legs)
        if picked >= CHECKPOINT["flagged_legs"] and len(days) >= CHECKPOINT["days"]:
            break
    keep = set(days)
    return [x for x in legs if x["day"] in keep]


def progress(legs: list[dict]) -> dict:
    used = window(legs)
    days = len({x["day"] for x in used})
    picked = sum(x["group"] == "picked" for x in used)
    return {"days": days, "flagged_legs": picked, "control_legs": len(used) - picked, "checkpoint": CHECKPOINT,
            "ready": days >= CHECKPOINT["days"] and picked >= CHECKPOINT["flagged_legs"]}


def _delta(legs: list[dict]) -> float | None:
    a = [x["y"] - x["p"] for x in legs if x["group"] == "picked"]
    b = [x["y"] - x["p"] for x in legs if x["group"] == "control"]
    return None if not a or not b else sum(a) / len(a) - sum(b) / len(b)


def judge(legs: list[dict]) -> dict:
    used = window(legs)
    by_day = defaultdict(list)
    for x in used:
        by_day[x["day"]].append(x)
    keys = sorted(by_day)
    rnd = random.Random(SEED)
    vals = sorted(v for v in (_delta([x for k in (rnd.choice(keys) for _ in keys) for x in by_day[k]])
                              for _ in range(DRAWS)) if v is not None)
    lo, hi = vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]
    picked = [x for x in used if x["group"] == "picked"]
    control = [x for x in used if x["group"] == "control"]

    def side(rows):
        return {"n": len(rows), "hit_rate": sum(x["y"] for x in rows) / len(rows),
                "model": sum(x["p"] for x in rows) / len(rows),
                "near_miss_rate": sum(bool(x["near_miss"]) for x in rows) / len(rows)}

    return {"n_flagged": len(picked), "n_legs": len(used), "days": len(keys),
            "primary_delta_resid": _delta(used), "ci95": [lo, hi], "pass": hi < 0,
            "picked": side(picked), "control": side(control),
            "by_market": {m: {"picked": len([x for x in picked if x["market"] == m]),
                              "delta": _delta([x for x in used if x["market"] == m])}
                          for m in ("pts", "reb", "ast", "fg3m")}}


def status(ledger=None, analysis=None, *, legs: list[dict] | None = None) -> dict:
    return {"P": progress(load(ledger) if legs is None else legs)}


def evaluate(ledger=None, analysis=None, out_dir: Path | None = None, *, force=False, only=None,
             legs: list[dict] | None = None) -> dict:
    if only and only != "P":
        return {}
    out_dir = Path(out_dir or REPORTS)
    path = out_dir / f"{EXPERIMENT}-P-result.json"
    if path.is_file() and not force:
        return {"P": json.loads(path.read_text(encoding="utf-8"))}
    legs = load(ledger) if legs is None else legs
    state = progress(legs)
    if not state["ready"]:
        return {"P": {"status": "not_ready", "progress": state}}
    result = {"experiment": EXPERIMENT, "test": "P", "evaluated_at": datetime.now(timezone.utc).isoformat(),
              "start": START, "progress": state, **judge(legs)}
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"P": result}


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
