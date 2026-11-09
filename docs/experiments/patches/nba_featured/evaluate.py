"""EXP-20261110-01: frozen evaluation of the NBA 大細盤精選 paper forward test.

The picks are made live by `nba_engine.featured` (one per game, edge >= 5pp, at most 10 a day)
and settled by the dashboard tracking export (`featured_records`). This script only judges them.

  F250   interim look at 250 settled picks: STOP only if clearly losing (CI upper < 0).
  F1000  final look at 1,000 settled picks: PASS if the flat-stake ROI CI lower bound > 0.

usage:
  python3 evaluate.py status            -> counts only (never a hit rate or ROI)
  python3 evaluate.py evaluate [--force]

Each look runs once and is frozen to ~/WongChoiData/NBA_Market_Eval/reports/.
Protocol: docs/experiments/EXP-20261110-01-nba-featured-ou-forward-protocol.md.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
EXPERIMENT = "EXP-20261110-01"
START = "2026-11-11"
SEED, DRAWS = 20261110, 2000
LOOKS = {"F250": 250, "F1000": 1000}


def records(repo: Path = REPO) -> list[dict]:
    backend = repo / "Horse_Racing_Dashboard" / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from services.nba_tracking import export_tracking
    tracking = export_tracking(repo)
    if tracking.get("status") not in ("valid", "stale"):
        raise RuntimeError(f"tracking_{tracking.get('status')}")
    return [r for r in tracking.get("featured_records") or []
            if r.get("day", "") >= START and r.get("tracking_kind") == "featured"]


def settled(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r.get("state") in ("won", "lost") and isinstance(r.get("odds"), (int, float))]


def roi(rows: list[dict]) -> float:
    return sum((r["odds"] - 1) if r["state"] == "won" else -1.0 for r in rows) / len(rows)


def boot(rows: list[dict]) -> tuple[float, float]:
    """Resample whole days: picks on one slate share news, pace and the same model run."""
    days = defaultdict(list)
    for r in rows:
        days[r["day"]].append(r)
    keys = sorted(days)
    rnd = random.Random(SEED)
    vals = sorted(roi([x for k in (rnd.choice(keys) for _ in keys) for x in days[k]]) for _ in range(DRAWS))
    return vals[int(0.025 * DRAWS)], vals[int(0.975 * DRAWS)]


def status(ledger=None, analysis=None, *, rows: list[dict] | None = None) -> dict:
    n = len(settled(records() if rows is None else rows))
    return {name: {"bets": n, "checkpoint": {"bets": need}, "ready": n >= need} for name, need in LOOKS.items()}


def judge(name: str, rows: list[dict]) -> dict:
    done = sorted(settled(rows), key=lambda r: (r["day"], r["id"]))[:LOOKS[name]]   # exactly the first N
    lo, hi = boot(done)
    out = {"experiment": EXPERIMENT, "test": name, "evaluated_at": datetime.now(timezone.utc).isoformat(),
           "n_bets": len(done), "roi": roi(done), "ci95": [lo, hi],
           "hit_rate": sum(r["state"] == "won" for r in done) / len(done),
           "days": len({r["day"] for r in done}),
           "by_side": {s: {"n": len(x), "roi": roi(x) if x else None}
                       for s in ("over", "under") for x in [[r for r in done if r["legs"][0]["side"] == s]]}}
    if name == "F250":
        out["stop"] = hi < 0          # clearly losing: stop the paper card
        out["pass"] = False           # an interim look can never pass
    else:
        out["pass"] = lo > 0
    return out


def evaluate(ledger=None, analysis=None, out_dir: Path | None = None, *, force=False, only=None,
             rows: list[dict] | None = None) -> dict:
    out_dir = Path(out_dir or Path.home() / "WongChoiData" / "NBA_Market_Eval" / "reports")
    rows = records() if rows is None else rows
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
    if a.mode == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(evaluate(out_dir=a.out, force=a.force), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
