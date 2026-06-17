#!/usr/bin/env python3
"""
rescore_backtest.py — full-pipeline HKJC Auto backtest.

Re-runs the LIVE scoring engine (feature scorers + matrix + weights) on historical
Race_*_Logic.json files entirely IN MEMORY (deep-copied; no files are written, the
archive is never mutated) and evaluates the resulting ranking against the actual
*全日賽果.json results.

Unlike walk_forward_auto_backtest.py — which recomputes ability from the persisted
matrix/feature scores and therefore only tests the matrix-weight layer — this tool
exercises the ENTIRE pipeline. Use it to validate feature-scorer changes (speed,
draw, form, class, consistency, …), not just weight tweaks.

Metrics (model picks top 4; actual top-3 includes dead-heats, pos<=3):
  gold        all of picks[:3] in actual top3
  good        picks[0] and picks[1] both in actual top3
  min         >=2 of picks[:3] in actual top3
  single      >=1 of picks[:3] in actual top3
  champion    picks[0] is an actual winner
  top3_champ  an actual winner is in picks[:3]

Usage:
  python3 rescore_backtest.py <meeting_dir> [<meeting_dir> ...] [--json]
"""
from __future__ import annotations
import argparse
import copy
import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_ENGINE = Path(__file__).resolve().parents[2] / "hkjc_wong_choi_auto" / "scripts" / "racing_engine"
sys.path.insert(0, str(_ENGINE))
from engine_core import RacingEngine  # noqa: E402

METRICS = ("gold", "good", "min", "single", "champion", "top3_champ")


def find_results_json(meeting_dir: Path):
    files = sorted(meeting_dir.glob("*全日賽果.json"))
    return files[0] if files else None


def load_results(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    results = {}
    for race_key, race_data in data.items():
        try:
            race_num = int(race_key)
        except (TypeError, ValueError):
            continue
        rr = {}
        for row in race_data.get("results", []):
            try:
                rr[int(row["horse_no"])] = int(row["pos"])
            except (KeyError, TypeError, ValueError):
                continue
        if rr:
            results[race_num] = rr
    return results


def race_num_from_path(path: Path):
    m = re.search(r"Race_(\d+)_Logic\.json$", path.name)
    return int(m.group(1)) if m else 0


def rescore_meeting(md: Path):
    rp = find_results_json(md)
    if rp is None:
        return [], []
    actual = load_results(rp)
    races, errors = [], []
    for lp in sorted(md.glob("Race_*_Logic.json"), key=race_num_from_path):
        rn = race_num_from_path(lp)
        if rn not in actual:
            continue
        logic = json.loads(lp.read_text(encoding="utf-8"))
        race_context = logic.get("race_analysis", {})
        scored = []
        for hn_text, h_obj in logic.get("horses", {}).items():
            try:
                hn = int(hn_text)
            except ValueError:
                continue
            try:
                result = RacingEngine(copy.deepcopy(h_obj), race_context).analyze_horse()
                scored.append({"hn": hn, "ability": float(result["ability_score"])})
            except Exception as exc:
                errors.append(f"{md.name} R{rn} #{hn}: {exc}")
        if scored:
            races.append({"scored": scored, "actual": actual[rn]})
    return races, errors


def evaluate(races):
    agg = {m: 0 for m in METRICS}
    for race in races:
        ap = race["actual"]
        if not ap:
            continue
        best = min(ap.values())
        winners = {h for h, p in ap.items() if p == best}
        top3 = {h for h, p in ap.items() if p <= 3}
        order = [s["hn"] for s in sorted(race["scored"], key=lambda x: (-x["ability"], x["hn"]))]
        picks = order[:4]
        hits3 = sum(1 for x in picks[:3] if x in top3)
        agg["gold"] += hits3 == 3
        agg["good"] += len(picks) >= 2 and picks[0] in top3 and picks[1] in top3
        agg["min"] += hits3 >= 2
        agg["single"] += hits3 >= 1
        agg["champion"] += bool(picks and picks[0] in winners)
        agg["top3_champ"] += bool(winners & set(picks[:3]))
    agg["races"] = len(races)
    return agg


def fmt(a):
    n = a["races"] or 1
    return (f"races={a['races']} "
            + " ".join(f"{m}={a[m]}({100*a[m]/n:.1f}%)" for m in METRICS))


def main() -> int:
    parser = argparse.ArgumentParser(description="HKJC Auto full-pipeline re-score backtest")
    parser.add_argument("meeting_dirs", nargs="+")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    all_races, all_errors = [], []
    for d in sorted(args.meeting_dirs):
        races, errors = rescore_meeting(Path(d))
        all_races.extend(races)
        all_errors.extend(errors)

    agg = evaluate(all_races)
    if args.json:
        print(json.dumps({"summary": agg, "errors": all_errors}, ensure_ascii=False, indent=2))
    else:
        print("LIVE ENGINE full-pipeline re-score:")
        print("  ", fmt(agg))
        if all_errors:
            print(f"  ({len(all_errors)} horse(s) errored; first: {all_errors[0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
