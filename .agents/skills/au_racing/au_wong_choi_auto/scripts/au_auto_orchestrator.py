#!/usr/bin/env python3
"""
AU Wong Choi Auto Orchestrator.
Deterministic full-Python AU scoring/ranking/output pipeline.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from engine_core import RacingEngine, enrich_logic_from_facts
from renderer import ensure_verdict, render_meeting_csv, validate_report_text, write_race_outputs
from validation import validate_engine_scripts, validate_logic_data


def _condition_family(condition: str) -> str:
    from au_archive_calibrator import normalize_condition_bucket

    return normalize_condition_bucket(condition)


def stored_going(logic_data: dict) -> str:
    """Today's going exactly as the engine would read it (same precedence)."""
    race = logic_data.get("race_analysis") or {}
    meeting = race.get("meeting_intelligence") if isinstance(race.get("meeting_intelligence"), dict) else {}
    speed_map = race.get("speed_map") if isinstance(race.get("speed_map"), dict) else {}
    return str(
        meeting.get("going")
        or speed_map.get("going")
        or speed_map.get("track_condition")
        or race.get("going")
        or ""
    ).strip()


def apply_going_refresh(logic_data: dict, official_going: str) -> dict:
    """Overwrite every going field the engine reads with the official pre-race going.

    Data-correctness gate from the 2026-07-16 shadow review: Warwick Farm
    2026-07-15 was scored on stale Soft 5 Logic data while the meeting raced
    Good 4 (4/7 races mismatched). Going must be refreshed immediately before
    scoring; the audit trail is stored in race_analysis["going_refresh"].
    """
    official_going = str(official_going).strip()
    race = logic_data.setdefault("race_analysis", {})
    previous = stored_going(logic_data)
    race["going"] = official_going
    speed_map = race.get("speed_map")
    if isinstance(speed_map, dict):
        speed_map["going"] = official_going
        if "track_condition" in speed_map:
            speed_map["track_condition"] = official_going
    meeting = race.get("meeting_intelligence")
    if isinstance(meeting, dict):
        meeting["going"] = official_going
        meeting["track_summary"] = official_going
    audit = {
        "previous": previous,
        "applied": official_going,
        "changed": previous != official_going,
        "family_changed": _condition_family(previous) != _condition_family(official_going),
    }
    race["going_refresh"] = audit
    return audit


def process_logic_file(logic_path: Path, going_override: str | None = None) -> dict:
    try:
        logic_data = json.loads(logic_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"Failed to read/parse Logic.json: {logic_path}\n{e}")
    if going_override:
        audit = apply_going_refresh(logic_data, going_override)
        if audit["family_changed"]:
            print(
                f"⚠️  GOING REFRESH {logic_path.name}: stored '{audit['previous']}' → official "
                f"'{audit['applied']}' (family change — wet/soft handling recomputed)",
                file=sys.stderr,
            )
        elif audit["changed"]:
            print(
                f"ℹ️  Going refresh {logic_path.name}: '{audit['previous']}' → '{audit['applied']}'",
                file=sys.stderr,
            )
    race_number = logic_data.get("race_analysis", {}).get("race_number")
    facts_path = _facts_path_for_logic(logic_path, race_number)
    if facts_path and facts_path.exists():
        logic_data = enrich_logic_from_facts(logic_data, facts_path)
    if "race_analysis" not in logic_data:
        logic_data["race_analysis"] = {}
    race_context = logic_data["race_analysis"]
    race_context["field_summary"] = _build_field_summary(logic_data.get("horses", {}))
    # Today's runner names so the engine can flag 賽績線 head-to-head rematches.
    race_context["field_horse_names"] = [
        h.get("horse_name") for h in logic_data.get("horses", {}).values()
        if isinstance(h, dict) and h.get("horse_name")
    ]
    for horse_num, horse in logic_data.get("horses", {}).items():
        # Inject the saddlecloth number (it is the dict key, not a field) so the
        # engine can match the horse to its speed-map pace role / settling pattern.
        horse.setdefault("horse_number", horse_num)
        facts_section = ""
        data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
        if isinstance(data, dict):
            facts_section = data.get("facts_section", "")
        engine = RacingEngine(horse, race_context, facts_section=facts_section, facts_path=facts_path)
        horse["python_auto"] = engine.analyze_horse()
    # SIP-030: legacy post-hoc place rerank layer removed; engine ability_score is computed upstream.
    ensure_verdict(logic_data)
    errors = validate_logic_data(logic_data)
    if errors:
        raise ValueError(f"Logic validation failed for {logic_path}:\n" + "\n".join(errors))
    # Write JSON first to avoid inconsistent state (json write before md/csv)
    try:
        logic_path.write_text(json.dumps(logic_data, ensure_ascii=False, indent=2), encoding="utf-8")
    except TypeError as e:
        raise ValueError(f"Failed to serialize Logic.json: {logic_path}\n{e}")
    md_path, csv_path = write_race_outputs(logic_path, logic_data)
    report_errors = validate_report_text(md_path.read_text(encoding="utf-8"))
    if report_errors:
        raise ValueError(f"Report validation failed for {md_path}:\n" + "\n".join(report_errors))
    print(f"✅ Auto analysis written: {md_path.name}")
    print(f"✅ Auto scoring written: {csv_path.name}")
    return logic_data


def process_meeting_dir(meeting_dir: Path, going_override: str | None = None) -> list[dict]:
    results = []
    logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"), key=_logic_sort_key)
    if not logic_files:
        raise FileNotFoundError(f"No Race_*_Logic.json files found in {meeting_dir}")
    for logic_path in logic_files:
        try:
            results.append(process_logic_file(logic_path, going_override=going_override))
        except Exception as e:
            print(f"⚠️  Skipping {logic_path.name}: {e}", file=sys.stderr)
            continue
    meeting_csv = render_meeting_csv(results)
    if meeting_csv:
        (meeting_dir / "Meeting_Auto_Scoring.csv").write_text(meeting_csv, encoding="utf-8")
        print("✅ Meeting_Auto_Scoring.csv updated")
    refreshed = [r.get("race_analysis", {}).get("going_refresh") for r in results]
    refreshed = [audit for audit in refreshed if audit]
    if refreshed:
        family_changes = sum(1 for audit in refreshed if audit["family_changed"])
        text_changes = sum(1 for audit in refreshed if audit["changed"])
        print(
            f"✅ Going refresh applied to {len(refreshed)} races "
            f"({text_changes} changed, {family_changes} family changes)"
        )
    return results


def _facts_path_for_logic(logic_path: Path, race_number):
    if race_number in (None, ""):
        return None
    # Sanitise race_number to prevent glob injection
    safe_race_num = re.sub(r"[^0-9]", "", str(race_number))
    if not safe_race_num:
        return None
    # Archive meetings name Facts files "MM-DD Race N Facts.md" (spaces), live
    # tooling uses "Race_N_Facts.md" (underscores) — accept both.
    for pattern in (f"*Race_{safe_race_num}_Facts.md", f"*Race {safe_race_num} Facts.md"):
        matches = sorted(logic_path.parent.glob(pattern))
        if matches:
            return matches[0]
    return None


def _logic_sort_key(path: Path):
    stem = path.stem
    try:
        return int(stem.split("_")[1])
    except (IndexError, ValueError):
        return 999


def _build_field_summary(horses):
    weights = []
    ratings = []
    l600_deltas = []  # racenet PuntingForm L600-vs-benchmark, per runner (for pace_figure z)
    for horse in horses.values():
        try:
            weight = float(horse.get("weight"))
        except (TypeError, ValueError):
            weight = None
        if weight is not None:
            weights.append(weight)
        try:
            rating = float(horse.get("rating"))
        except (TypeError, ValueError):
            rating = None
        if rating is not None:
            ratings.append(rating)
        pf_agg = ((horse.get("_data") or {}).get("pf_metrics") or {}).get("pf_aggregates") or {}
        ld = pf_agg.get("l600_delta_avg")
        if ld is not None:
            try:
                l600_deltas.append(float(ld))
            except (TypeError, ValueError):
                pass
    if not horses:
        return {}
    ratings_sorted = sorted(ratings, reverse=True)
    l600_mean = (sum(l600_deltas) / len(l600_deltas)) if l600_deltas else 0.0
    l600_stdev = (
        (sum((v - l600_mean) ** 2 for v in l600_deltas) / len(l600_deltas)) ** 0.5
        if len(l600_deltas) >= 2 else 0.0
    )
    return {
        "l600_delta_field_count": len(l600_deltas),
        "l600_delta_field_mean": l600_mean,
        "l600_delta_field_stdev": l600_stdev,
        "count": len(horses),
        "min_weight": min(weights) if weights else 0.0,
        "max_weight": max(weights) if weights else 0.0,
        "avg_weight": (sum(weights) / len(weights)) if weights else 0.0,
        "rated_count": len(ratings),
        "min_rating": min(ratings) if ratings else 0.0,
        "max_rating": max(ratings) if ratings else 0.0,
        "avg_rating": (sum(ratings) / len(ratings)) if ratings else 0.0,
        "rating_stdev": (
            (sum((value - (sum(ratings) / len(ratings))) ** 2 for value in ratings) / len(ratings)) ** 0.5
            if ratings
            else 0.0
        ),
        "top3_rating_cutoff": ratings_sorted[2] if len(ratings_sorted) >= 3 else (ratings_sorted[-1] if ratings_sorted else 0.0),
    }


def _horse_number_sort_key(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 999


def main():
    parser = argparse.ArgumentParser(description="AU Wong Choi Auto Orchestrator")
    parser.add_argument("target", help="Meeting directory or Race_X_Logic.json")
    parser.add_argument(
        "--going",
        default=None,
        help=(
            "Official current track condition (e.g. 'Good 4'). Applied to every going "
            "field the engine reads immediately before scoring, with an audit trail in "
            "race_analysis.going_refresh. Always pass this for live meetings — stored "
            "Logic going can be stale (Warwick Farm 2026-07-15 raced Good 4 but was "
            "scored on Soft 5 Logic data)."
        ),
    )
    args = parser.parse_args()

    script_errors = validate_engine_scripts(SCRIPT_DIR / "racing_engine")
    if script_errors:
        raise ValueError("Engine validation failed:\n" + "\n".join(script_errors))

    target = Path(args.target).resolve()
    if target.is_file():
        process_logic_file(target, going_override=args.going)
    elif target.is_dir():
        process_meeting_dir(target, going_override=args.going)
    else:
        raise FileNotFoundError(target)


if __name__ == "__main__":
    main()
