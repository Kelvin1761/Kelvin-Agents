"""EXP-20261111-05: does a bigger share for the price-free model, with v2 minutes, beat the published MS?

Forward only, from the market ledger. Two frozen blends are scored against the published
probability on every milestone leg of the first pre-tip `production` snapshot:

  MS2   market + S2 (S with the v2 minutes forecast, `p_s2`)      <- the candidate, primary
  MSR   market + S  (same refit, old minutes)                     <- tells refit apart from S2

  logit p = a_stat + beta * logit(clip(1/price)) + gamma * logit(clip(S))

Coefficients were fitted once on 2026-11-03..11-10 (7,520 legs) and never move. Primary metric:
mean log-loss(MS2) - mean log-loss(p_final) over legs that carry p_s2, p_s and p_final.
Judged once, at the end of the first day on which 14 days and 10,000 legs are settled;
95% CI from a day-clustered bootstrap. PASS = CI upper bound < 0.
Nothing here changes what is published.

usage:
  python3 evaluate.py status
  python3 evaluate.py evaluate [--force]

Protocol: docs/experiments/EXP-20261111-05-nba-s2-shadow-forward-protocol.md.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

EXPERIMENT = "EXP-20261111-05"
START = "2026-11-12"          # first 21:00 run after the shadow ships; legs without p_s2 are skipped
SEED, DRAWS = 20261111, 2000
CHECKPOINT = {"days": 14, "flagged_legs": 10000}
CLIP = (0.02, 0.98)
STAT = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M"}
BLENDS = {
    "MS2": {"source": "p_s2", "beta": 0.6514, "gamma": 0.3494,
            "intercepts": {"PTS": -0.2285, "REB": -0.1958, "AST": -0.1767, "FG3M": -0.0545}},
    "MSR": {"source": "p_s", "beta": 0.7087, "gamma": 0.2868,
            "intercepts": {"PTS": -0.2473, "REB": -0.2090, "AST": -0.1993, "FG3M": -0.0728}},
}
LEDGER = Path.home() / "WongChoiData" / "NBA_Market_Eval" / "ledger"
REPORTS = Path.home() / "WongChoiData" / "NBA_Market_Eval" / "reports"


def _logit(p: float) -> float:
    p = min(max(p, CLIP[0]), CLIP[1])
    return math.log(p / (1 - p))


def blend(name: str, stat: str, price: float, s: float) -> float:
    c = BLENDS[name]
    z = c["intercepts"][stat] + c["beta"] * _logit(1.0 / price) + c["gamma"] * _logit(s)
    return 1.0 / (1.0 + math.exp(-z))


def _loss(p: float, y: int) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return -(math.log(p) if y else math.log(1 - p))


def day_legs(rows: list[dict]) -> list[dict]:
    """Per-leg losses of one target date: published, MS2, MSR, S and S2."""
    model: dict[tuple, dict] = {}
    result: dict[tuple, int] = {}
    for r in rows:
        kind = r.get("row_type")
        if kind == "model_obs":
            if r.get("post_tip") or r.get("snapshot_role") != "production" or r.get("market") not in STAT:
                continue
            if any(r.get(k) is None for k in ("p_final", "p_s", "p_s2", "price_at_model", "line")):
                continue
            key = (r.get("game_tag"), r.get("player"), r.get("market"), float(r["line"]))
            if key not in model or str(r.get("recorded_at")) < str(model[key].get("recorded_at")):
                model[key] = r
        elif kind == "settlement" and r.get("y") is not None and r.get("line") is not None:
            result.setdefault((r.get("game_tag"), r.get("player"), r.get("market"), float(r["line"])), int(r["y"]))
    out = []
    for key, r in sorted(model.items(), key=lambda kv: tuple(map(str, kv[0]))):
        if key not in result:
            continue
        price = float(r["price_at_model"])
        if price <= 1.0:
            continue
        y, stat = result[key], STAT[key[2]]
        out.append({"day": r.get("target_date"), "stat": stat,
                    "pub": _loss(float(r["p_final"]), y),
                    "ms2": _loss(blend("MS2", stat, price, float(r["p_s2"])), y),
                    "msr": _loss(blend("MSR", stat, price, float(r["p_s"])), y),
                    "s": _loss(float(r["p_s"]), y), "s2": _loss(float(r["p_s2"]), y)})
    return out


def _read(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if '"model_obs"' in line or '"settlement"' in line:
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
    days, count = [], 0
    for day in sorted({x["day"] for x in legs}):
        days.append(day)
        count += sum(x["day"] == day for x in legs)
        if count >= CHECKPOINT["flagged_legs"] and len(days) >= CHECKPOINT["days"]:
            break
    keep = set(days)
    return [x for x in legs if x["day"] in keep]


def progress(legs: list[dict]) -> dict:
    used = window(legs)
    days = len({x["day"] for x in used})
    return {"days": days, "flagged_legs": len(used), "checkpoint": CHECKPOINT,
            "ready": days >= CHECKPOINT["days"] and len(used) >= CHECKPOINT["flagged_legs"]}


def _delta(rows: list[dict], a: str, b: str) -> float:
    return sum(x[a] - x[b] for x in rows) / len(rows)


def _ci(rows: list[dict], a: str, b: str) -> list[float]:
    by_day = defaultdict(list)
    for x in rows:
        by_day[x["day"]].append(x[a] - x[b])
    keys = sorted(by_day)
    rnd = random.Random(SEED)
    vals = []
    for _ in range(DRAWS):
        sample = [v for k in (rnd.choice(keys) for _ in keys) for v in by_day[k]]
        vals.append(sum(sample) / len(sample))
    vals.sort()
    return [vals[int(0.025 * DRAWS)], vals[int(0.975 * DRAWS) - 1]]


def judge(legs: list[dict]) -> dict:
    used = window(legs)
    ci = _ci(used, "ms2", "pub")
    mean = lambda key: sum(x[key] for x in used) / len(used)  # noqa: E731
    return {"n_legs": len(used), "days": len({x["day"] for x in used}),
            "logloss": {k: mean(k) for k in ("pub", "ms2", "msr", "s", "s2")},
            "primary_delta": _delta(used, "ms2", "pub"), "ci95": ci, "pass": ci[1] < 0,
            "msr_vs_published": {"delta": _delta(used, "msr", "pub"), "ci95": _ci(used, "msr", "pub")},
            "ms2_vs_msr": {"delta": _delta(used, "ms2", "msr"), "ci95": _ci(used, "ms2", "msr")},
            "s2_vs_s": {"delta": _delta(used, "s2", "s"), "ci95": _ci(used, "s2", "s")},
            "by_stat": {s: {"n": len(rows), "delta": _delta(rows, "ms2", "pub")}
                        for s in STAT.values() for rows in [[x for x in used if x["stat"] == s]] if rows}}


def status(ledger=None, analysis=None, *, legs: list[dict] | None = None) -> dict:
    return {"S2": progress(load(ledger) if legs is None else legs)}


def evaluate(ledger=None, analysis=None, out_dir: Path | None = None, *, force=False, only=None,
             legs: list[dict] | None = None) -> dict:
    if only and only != "S2":
        return {}
    out_dir = Path(out_dir or REPORTS)
    path = out_dir / f"{EXPERIMENT}-S2-result.json"
    if path.is_file() and not force:
        return {"S2": json.loads(path.read_text(encoding="utf-8"))}
    legs = load(ledger) if legs is None else legs
    state = progress(legs)
    if not state["ready"]:
        return {"S2": {"status": "not_ready", "progress": state}}
    result = {"experiment": EXPERIMENT, "test": "S2", "evaluated_at": datetime.now(timezone.utc).isoformat(),
              "start": START, "blends": BLENDS, "progress": state, **judge(legs)}
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"S2": result}


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
