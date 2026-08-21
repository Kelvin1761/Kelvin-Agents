#!/usr/bin/env python3
"""
AU Wong Choi Auto Orchestrator.
Deterministic full-Python AU scoring/ranking/output pipeline.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.append(str(SCRIPT_DIR))

from au_racing_engine.engine_core import (
    RacingEngine,
    backfill_pf_metrics,
    enrich_logic_from_facts,
    horse_prize_level,
)
from au_racing_engine.io_utils import write_json_atomic as _write_json_atomic
from au_racing_engine.io_utils import write_text_atomic as _atomic_write_text
from au_racing_engine.renderer import ensure_verdict, render_meeting_csv, validate_report_text, write_race_outputs
from au_racing_engine.validation import validate_engine_scripts, validate_logic_data


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


def _load_logic_file(logic_path: Path) -> dict:
    try:
        logic_data = json.loads(logic_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"Failed to read/parse Logic.json: {logic_path}\n{e}")
    _validate_input_shape(logic_path, logic_data)
    race_number = logic_data["race_analysis"].get("race_number")
    _validate_race_identity(logic_path, race_number)
    return logic_data


def process_logic_file(
    logic_path: Path,
    going_override: str | None = None,
    *,
    logic_data: dict | None = None,
) -> dict:
    logic_data = (
        _load_logic_file(logic_path)
        if logic_data is None
        else logic_data
    )
    race_number = logic_data["race_analysis"].get("race_number")
    facts_path = _facts_path_for_logic(logic_path, race_number)
    logic_data, audit = _prepare_logic_data(
        logic_data,
        facts_path=facts_path,
        going_override=going_override,
    )
    if audit:
        _report_going_refresh(logic_path, audit)
    if "race_analysis" not in logic_data:
        logic_data["race_analysis"] = {}
    race_context = logic_data["race_analysis"]
    # Before the field summary: 段速實速 is field-relative, so PF has to be
    # complete for the whole race or not counted at all.
    backfill_pf_metrics(logic_data, facts_path)
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
    _write_json_atomic(logic_path, logic_data)
    md_path, csv_path = write_race_outputs(logic_path, logic_data)
    report_errors = validate_report_text(md_path.read_text(encoding="utf-8"))
    if report_errors:
        raise ValueError(f"Report validation failed for {md_path}:\n" + "\n".join(report_errors))
    print(f"✅ Auto analysis written: {md_path.name}")
    print(f"✅ Auto scoring written: {csv_path.name}")
    return logic_data


def process_meeting_dir(meeting_dir: Path, going_override: str | None = None) -> list[dict]:
    logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"), key=_logic_sort_key)
    if not logic_files:
        raise FileNotFoundError(f"No Race_*_Logic.json files found in {meeting_dir}")
    # Preflight the whole meeting before any JSON/Markdown/CSV mutation. A
    # corrupt late-race file must not leave earlier races refreshed and the
    # meeting summary stale.
    preloaded = [
        (logic_path, _load_logic_file(logic_path))
        for logic_path in logic_files
    ]
    results = [
        process_logic_file(
            logic_path,
            going_override=going_override,
            logic_data=logic_data,
        )
        for logic_path, logic_data in preloaded
    ]
    meeting_csv = render_meeting_csv(results)
    if meeting_csv:
        _atomic_write_text(meeting_dir / "Meeting_Auto_Scoring.csv", meeting_csv)
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


def _prepare_logic_data(
    logic_data: dict,
    *,
    facts_path: Path | None,
    going_override: str | None,
) -> tuple[dict, dict | None]:
    if facts_path and facts_path.exists():
        logic_data = enrich_logic_from_facts(logic_data, facts_path)
    audit = apply_going_refresh(logic_data, going_override) if going_override else None
    return logic_data, audit


def _report_going_refresh(logic_path: Path, audit: dict) -> None:
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


def _validate_race_identity(logic_path: Path, race_number: object) -> None:
    filename_match = re.fullmatch(r"Race_(\d+)_Logic", logic_path.stem)
    if not filename_match:
        raise ValueError(f"Invalid Logic filename: {logic_path.name}")
    metadata_match = re.search(r"\d+", str(race_number or ""))
    if not metadata_match:
        raise ValueError(f"Missing race_analysis.race_number in {logic_path.name}")
    if int(filename_match.group(1)) != int(metadata_match.group(0)):
        raise ValueError(
            f"Race identity mismatch: {logic_path.name} contains Race "
            f"{filename_match.group(1)} but metadata says Race {race_number}"
        )


def _validate_input_shape(logic_path: Path, logic_data: object) -> None:
    if not isinstance(logic_data, dict):
        raise ValueError(f"Logic root must be an object: {logic_path}")
    if not isinstance(logic_data.get("race_analysis"), dict):
        raise ValueError(f"race_analysis must be an object: {logic_path}")
    if not isinstance(logic_data.get("horses"), dict) or not logic_data["horses"]:
        raise ValueError(f"horses must be a non-empty object: {logic_path}")


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
        # A malformed archive can contain a directory whose name ends in
        # ``Facts.md`` (for example a run-log directory).  ``exists()`` is not
        # enough: passing that directory to the enricher raises
        # IsADirectoryError and aborts the whole meeting.
        matches = sorted(
            path for path in logic_path.parent.glob(pattern) if path.is_file()
        )
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
    performance_quality = []
    # 班次代理（2026-07-31）：逐匹馬近仗獎金水平嘅場內中位數，供 `_form_score`
    # 做場內相對班次調整。同下面 pf_fields 嘅場內 mean/stdev 同一個 pattern。
    prize_levels = []
    pf_fields = {
        "race_time_diff": [],
        "l800_delta": [],
        "l600_delta": [],
        "l400_delta": [],
        "l200_delta": [],
        "tempo_qrank": [],
    }
    complete_profiles = 0
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
        level = horse_prize_level((horse.get("_data") or {}).get("facts_section"))
        if level is not None:
            prize_levels.append(level)
        try:
            quality = float(
                (horse.get("_data") or {}).get("performance_quality_raw")
            )
        except (TypeError, ValueError):
            quality = None
        if quality is not None:
            performance_quality.append(quality)
        pf_agg = ((horse.get("_data") or {}).get("pf_metrics") or {}).get("pf_aggregates") or {}
        for key, values in pf_fields.items():
            value = pf_agg.get(f"{key}_avg")
            if value is None:
                continue
            try:
                values.append(float(value))
            except (TypeError, ValueError):
                pass
        if all(
            pf_agg.get(f"{key}_avg") is not None
            for key in ("l800_delta", "l600_delta", "l400_delta", "l200_delta")
        ):
            complete_profiles += 1
    if not horses:
        return {}
    ratings_sorted = sorted(ratings, reverse=True)
    summary = {
        "pf_complete_profile_field_count": complete_profiles,
        "count": len(horses),
        "min_weight": min(weights) if weights else 0.0,
        "max_weight": max(weights) if weights else 0.0,
        "avg_weight": (sum(weights) / len(weights)) if weights else 0.0,
        # Spread of the handicapper's own ability ranking. Used only where the
        # official rating is absent (`_rating_score` proxy) — see that method.
        "weighted_count": len(weights),
        "weight_stdev": (
            (
                sum(
                    (value - (sum(weights) / len(weights))) ** 2
                    for value in weights
                )
                / len(weights)
            )
            ** 0.5
            if len(weights) >= 2
            else 0.0
        ),
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
    for key, values in pf_fields.items():
        mean = (sum(values) / len(values)) if values else 0.0
        stdev = (
            (sum((value - mean) ** 2 for value in values) / len(values)) ** 0.5
            if len(values) >= 2
            else 0.0
        )
        summary[f"{key}_field_count"] = len(values)
        summary[f"{key}_field_mean"] = mean
        summary[f"{key}_field_stdev"] = stdev
    quality_mean = (
        sum(performance_quality) / len(performance_quality)
        if performance_quality
        else 0.0
    )
    summary["performance_quality_field_count"] = len(performance_quality)
    summary["performance_quality_field_mean"] = quality_mean
    summary["performance_quality_field_stdev"] = (
        (
            sum((value - quality_mean) ** 2 for value in performance_quality)
            / len(performance_quality)
        )
        ** 0.5
        if len(performance_quality) >= 2
        else 0.0
    )
    # 用中位數而唔係平均：獎金 log10 分佈有長尾（一匹跑過 Group 1 嘅馬會拉高平均，
    # 令全場其他馬齊齊被扣分）。少於 4 匹有數據就唔提供 —— 樣本太細嘅「場內中位」
    # 冇意義，`_form_score` 會自動跳過班次調整。
    if len(prize_levels) >= 4:
        summary["prize_level_field_count"] = len(prize_levels)
        summary["prize_level_field_median"] = statistics.median(prize_levels)
    return summary


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

    script_errors = validate_engine_scripts(SCRIPT_DIR / "au_racing_engine")
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
