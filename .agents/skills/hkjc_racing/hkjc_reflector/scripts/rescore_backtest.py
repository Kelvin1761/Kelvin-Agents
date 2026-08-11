#!/usr/bin/env python3
"""
rescore_backtest.py — full-pipeline HKJC Auto backtest.

Re-runs the LIVE scoring core (header canonicalization + feature scorers + matrix
+ SIP + ranking) on historical
Race_*_Logic.json files entirely IN MEMORY (deep-copied; no files are written, the
archive is never mutated) and evaluates the resulting ranking against the actual
*全日賽果.json results.

Unlike walk_forward_auto_backtest.py — which recomputes ability from the persisted
matrix/feature scores and therefore only tests the matrix-weight layer — this tool
exercises the ENTIRE pipeline. Use it to validate feature-scorer changes (speed,
draw, form, class, consistency, …), not just weight tweaks.

Important: this diagnostic uses the priors currently available to the live
engine. It is NOT point-in-time and must not be used alone to promote weights.
Use pit_backtest.py for no-lookahead promotion evidence.

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
_AUTO = _ENGINE.parent
_REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(_AUTO))
sys.path.insert(0, str(_ENGINE))
sys.path.insert(0, str(_REPO))
from engine_core import RacingEngine  # noqa: E402
from hkjc_auto_orchestrator import _apply_sip_enhancements, _enrich_horse_headers  # noqa: E402
from renderer import ensure_verdict  # noqa: E402
from full_rank_ml import apply_full_rank_ml  # noqa: E402
from wongchoi_paths import is_materialized_file  # noqa: E402

METRICS = ("gold", "good", "min", "single", "champion", "top3_champ")


def find_results_json(meeting_dir: Path):
    files = [
        path
        for path in sorted(meeting_dir.glob("*全日賽果.json"))
        if is_materialized_file(path)
    ]
    if len(files) > 1:
        raise ValueError(
            "multiple materialized result files: "
            + ", ".join(path.name for path in files)
        )
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


def meeting_is_legacy_schema(md: Path, sample: int = 3):
    """Detect legacy-pipeline meetings (April–early-May 2026 and earlier) whose
    Logic JSONs carry a sparse `_data` (~8 keys, no raw_l400/medical) because the
    data was never extracted. The current engine scores those on mostly neutral
    fallbacks, so mixing them in silently DILUTES backtest metrics. Heuristic:
    median `_data` key count < 20 across a few sampled horses.
    """
    counts = []
    logic_files = [
        path
        for path in sorted(md.glob("Race_*_Logic.json"), key=race_num_from_path)
        if is_materialized_file(path)
    ]
    for lp in logic_files[:sample]:
        try:
            logic = json.loads(lp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for h in list(logic.get("horses", {}).values())[:8]:
            d = h.get("_data")
            counts.append(len(d) if isinstance(d, dict) else 0)
    if not counts:
        return False
    counts.sort()
    median = counts[len(counts) // 2]
    return median < 20


def rescore_logic(logic: dict, *, keep_embedded_combo_prior: bool = False):
    """Production-equivalent, write-free scoring core for one Logic document."""
    logic = copy.deepcopy(logic)
    race_context = logic.get("race_analysis", {})
    horses = logic.get("horses", {})
    _enrich_horse_headers(
        horses,
        {},
        keep_embedded_combo_prior=keep_embedded_combo_prior,
    )
    if isinstance(race_context, dict):
        race_context["field_horse_names"] = [
            horse.get("horse_name")
            for horse in horses.values()
            if isinstance(horse, dict) and horse.get("horse_name")
        ]
    for horse in horses.values():
        if not isinstance(horse, dict):
            continue
        horse["python_auto"] = RacingEngine(horse, race_context).analyze_horse()
    _apply_sip_enhancements(horses)
    if len(horses) >= 2:
        apply_full_rank_ml(logic)
    ensure_verdict(logic)
    return logic


def rescore_meeting(
    md: Path,
    include_legacy: bool = False,
    *,
    keep_embedded_combo_prior: bool = False,
):
    try:
        rp = find_results_json(md)
    except ValueError as exc:
        return [], [f"{md.name}: {exc}"]
    if rp is None:
        return [], []
    if not include_legacy and meeting_is_legacy_schema(md):
        return [], [f"SKIP {md.name}: legacy sparse-schema meeting (use --include-legacy to force)"]
    actual = load_results(rp)
    races, errors = [], []
    logic_files = sorted(md.glob("Race_*_Logic.json"), key=race_num_from_path)
    for lp in logic_files:
        if not is_materialized_file(lp):
            errors.append(f"{md.name} {lp.name}: file is not materialized locally")
            continue
        rn = race_num_from_path(lp)
        if rn not in actual:
            continue
        logic = json.loads(lp.read_text(encoding="utf-8"))
        try:
            rescored = rescore_logic(
                logic,
                keep_embedded_combo_prior=keep_embedded_combo_prior,
            )
        except Exception as exc:
            errors.append(f"{md.name} R{rn}: {exc}")
            continue
        scored = []
        for hn_text, h_obj in rescored.get("horses", {}).items():
            try:
                hn = int(hn_text)
            except ValueError:
                continue
            try:
                result = h_obj["python_auto"]
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
    parser.add_argument("--include-legacy", action="store_true",
                        help="Include legacy sparse-schema meetings (default: skip them).")
    parser.add_argument(
        "--keep-embedded-combo-prior",
        action="store_true",
        help="Replay the retired reflector-wide Full combo prior for A/B comparison",
    )
    args = parser.parse_args()

    all_races, all_errors, skipped = [], [], []
    for d in sorted(args.meeting_dirs):
        races, errors = rescore_meeting(
            Path(d),
            include_legacy=args.include_legacy,
            keep_embedded_combo_prior=args.keep_embedded_combo_prior,
        )
        all_races.extend(races)
        for e in errors:
            (skipped if e.startswith("SKIP ") else all_errors).append(e)

    agg = evaluate(all_races)
    if args.json:
        print(
            json.dumps(
                {
                    "mode": "diagnostic_current_priors_not_point_in_time",
                    "promotion_safe": False,
                    "summary": agg,
                    "errors": all_errors,
                    "skipped": skipped,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print("LIVE ENGINE full-pipeline re-score (diagnostic; NOT point-in-time):")
        print("  ", fmt(agg))
        if skipped:
            print(f"  skipped {len(skipped)} legacy-schema meeting(s): " + ", ".join(s.split(":")[0][5:] for s in skipped))
        if all_errors:
            print(f"  ({len(all_errors)} horse(s) errored; first: {all_errors[0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
