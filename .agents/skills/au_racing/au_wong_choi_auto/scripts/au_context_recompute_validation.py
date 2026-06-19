#!/usr/bin/env python3
"""
AU context extraction full-engine recompute validation.

This validates the context extraction rebuild by re-running RacingEngine from
Logic + Facts, then comparing the recomputed ranking against known results.
It does not write back meeting logic, scoring CSVs, or analysis reports.
"""
from __future__ import annotations

import argparse
import copy
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]

import sys

sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from au_archive_calibrator import (  # noqa: E402
    HISTORICAL_RESULTS_CSV,
    choose_track_rows,
    detect_meeting_date,
    detect_meeting_track,
    load_historical_results,
    normalize_horse_name,
    parse_int,
)
from au_auto_orchestrator import _build_field_summary, _facts_path_for_logic  # noqa: E402
from au_immediate_fix_shadow_test import (  # noqa: E402
    TIGHT_TURN_VENUES,
    context_audit,
    discover_meetings,
    load_csv_rows,
    load_json_results,
    meeting_results_json,
    norm_text,
    venue_key,
)
from engine_core import RacingEngine, enrich_logic_from_facts  # noqa: E402


OUTPUT_MD = PROJECT_ROOT / "2026-06-09 AU Context Recompute Validation.md"
OUTPUT_JSON = PROJECT_ROOT / "2026-06-09 AU Context Recompute Validation.json"


def load_logic(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def actuals_from_historical(
    historical: dict,
    meeting: Path,
    sample_logic: dict[str, Any],
    race_no: int,
) -> dict[int, dict[str, Any]]:
    meeting_date = detect_meeting_date(meeting)
    meeting_track = detect_meeting_track(meeting, sample_logic)
    if not meeting_date or not meeting_track:
        return {}
    rows = choose_track_rows(historical.get((meeting_date, race_no), []), meeting_track)
    horses = sample_logic.get("horses") or {}
    slug_to_num = {
        normalize_horse_name(horse.get("horse_name")): parse_int(num)
        for num, horse in horses.items()
    }
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        hn = slug_to_num.get(row.get("horse_slug"))
        if hn is None:
            continue
        out[hn] = {
            "pos": int(row["pos"]),
            "horse_name": row.get("horse_name", ""),
            "condition": row.get("condition", ""),
        }
    return out


def match_actual(row: dict[str, Any], actual_map: dict[int, dict[str, Any]]) -> dict[str, Any] | None:
    hn = parse_int(row.get("horse_number"))
    if hn is not None and hn in actual_map:
        return actual_map[hn]
    slug = normalize_horse_name(row.get("horse_name"))
    return next(
        (
            value
            for value in actual_map.values()
            if normalize_horse_name(value.get("horse_name")) == slug
        ),
        None,
    )


def recompute_logic(logic_path: Path, enable_legacy_barrier_bias: bool = False) -> dict[str, Any]:
    logic = copy.deepcopy(load_logic(logic_path))
    race_number = (logic.get("race_analysis") or {}).get("race_number")
    facts_path = _facts_path_for_logic(logic_path, race_number)
    if facts_path and facts_path.exists():
        logic = enrich_logic_from_facts(logic, facts_path)
    race_context = logic.setdefault("race_analysis", {})
    race_context["field_summary"] = _build_field_summary(logic.get("horses", {}))
    if enable_legacy_barrier_bias:
        race_context["enable_legacy_barrier_bias"] = True
    else:
        race_context.pop("enable_legacy_barrier_bias", None)
    for horse in (logic.get("horses") or {}).values():
        data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
        engine = RacingEngine(
            horse,
            race_context,
            facts_section=data.get("facts_section", ""),
            facts_path=facts_path,
        )
        horse["python_auto"] = engine.analyze_horse()
    return logic


def rows_from_recomputed(logic: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for horse_number, horse in (logic.get("horses") or {}).items():
        auto = horse.get("python_auto") if isinstance(horse.get("python_auto"), dict) else {}
        rows.append(
            {
                "horse_number": parse_int(horse_number) or 999,
                "horse_name": horse.get("horse_name", ""),
                "rank_score": float(auto.get("rank_score") or auto.get("ability_score") or 0.0),
                "ability_score": float(auto.get("ability_score") or 0.0),
                "barrier_bias_modifier": float(auto.get("barrier_bias_modifier") or 0.0),
            }
        )
    return rows


def ranked_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            -float(row.get("rank_score") or 0.0),
            -float(row.get("ability_score") or 0.0),
            int(row.get("horse_number") or 999),
        ),
    )


def summarize_race(rows: list[dict[str, Any]], actual_map: dict[int, dict[str, Any]]) -> dict[str, Any]:
    matched = []
    for row in rows:
        actual = match_actual(row, actual_map)
        if actual:
            matched.append({**row, "actual": actual})
    ranked = ranked_rows(matched)
    top3 = ranked[:3]
    hits = sum(1 for row in top3 if int(row["actual"]["pos"]) <= 3)
    winner_rank = next((idx for idx, row in enumerate(ranked, 1) if int(row["actual"]["pos"]) == 1), None)
    return {
        "eligible": len(matched) >= 4,
        "order": [int(row["horse_number"]) for row in ranked],
        "top3": [int(row["horse_number"]) for row in top3],
        "hits": hits,
        "winner_rank": winner_rank,
        "top3_win": any(int(row["actual"]["pos"]) == 1 for row in top3),
    }


def add_metric(summary: Counter, race_summary: dict[str, Any]) -> None:
    if not race_summary.get("eligible"):
        return
    hits = int(race_summary.get("hits") or 0)
    summary["races"] += 1
    summary["top3_place"] += hits
    summary[f"{hits}hit"] += 1
    if hits == 3:
        summary["gold"] += 1
    if hits >= 2:
        summary["good"] += 1
    if hits >= 1:
        summary["pass"] += 1
    if race_summary.get("top3_win"):
        summary["top3_win"] += 1
    winner_rank = race_summary.get("winner_rank")
    if winner_rank:
        summary["reciprocal_sum"] += 1.0 / float(winner_rank)


def finalize(summary: Counter, changed: int, examples: list[dict[str, Any]]) -> dict[str, Any]:
    races = int(summary.get("races") or 0)
    return {
        "races": races,
        "gold": int(summary.get("gold") or 0),
        "good": int(summary.get("good") or 0),
        "pass": int(summary.get("pass") or 0),
        "top3_win": int(summary.get("top3_win") or 0),
        "top3_place": int(summary.get("top3_place") or 0),
        "0hit": int(summary.get("0hit") or 0),
        "mrr": round(float(summary.get("reciprocal_sum") or 0.0) / races, 4) if races else 0.0,
        "changed_races": changed,
        "examples": examples[:10],
    }


def context_completeness(logic: dict[str, Any]) -> dict[str, bool]:
    race = logic.get("race_analysis") or {}
    meeting = race.get("meeting_intelligence") if isinstance(race.get("meeting_intelligence"), dict) else {}
    profile = race.get("track_profile") if isinstance(race.get("track_profile"), dict) else {}
    return {
        "venue": bool(meeting.get("venue")),
        "date": bool(meeting.get("date")),
        "going": bool(race.get("going") or (race.get("speed_map") or {}).get("going") or meeting.get("going")),
        "rail_position": bool(meeting.get("rail_position")),
        "weather_summary": bool(meeting.get("weather_summary")),
        "track_profile": bool(profile),
    }


def run_validation(include_current: bool, result_source: str, include_legacy_barrier: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    historical = load_historical_results(HISTORICAL_RESULTS_CSV) if result_source in {"historical", "both"} else {}
    groups = ("all", "canterbury", "tight_turn")
    variants = ("baseline", "context_recompute")
    if include_legacy_barrier:
        variants = variants + ("context_plus_legacy_barrier",)
    counters = {group: {variant: Counter() for variant in variants} for group in groups}
    changed = {group: {variant: 0 for variant in variants if variant != "baseline"} for group in groups}
    examples = {group: {variant: [] for variant in variants if variant != "baseline"} for group in groups}
    before_audit: dict[str, Counter] = defaultdict(Counter)
    after_audit: dict[str, Counter] = defaultdict(Counter)
    result_sources = Counter()
    errors: list[str] = []

    meetings = discover_meetings(include_current)
    print(f"Discovered {len(meetings)} meetings", flush=True)
    for index, meeting in enumerate(meetings, start=1):
        csv_rows_by_race = load_csv_rows(meeting)
        if not csv_rows_by_race:
            continue
        result_json = meeting_results_json(meeting)
        if result_source == "json" and not result_json:
            continue
        if index == 1 or index % 5 == 0:
            print(f"Recomputing meeting {index}/{len(meetings)}: {meeting.name}", flush=True)
        json_results = load_json_results(result_json) if result_json and result_source in {"json", "both"} else {}
        race_logic = {
            race_no: load_logic(meeting / f"Race_{race_no}_Logic.json")
            for race_no in csv_rows_by_race
            if (meeting / f"Race_{race_no}_Logic.json").exists()
        }
        sample_logic = next((logic for logic in race_logic.values() if logic), {})
        venue = detect_meeting_track(meeting, sample_logic) or meeting.name
        before_audit[venue].update(context_audit(meeting, race_logic))

        for race_no, baseline_rows in csv_rows_by_race.items():
            logic_path = meeting / f"Race_{race_no}_Logic.json"
            if not logic_path.exists():
                continue
            original_logic = race_logic.get(race_no) or {}
            actual_map = json_results.get(race_no)
            source = "json"
            if not actual_map:
                if result_source == "json":
                    continue
                actual_map = actuals_from_historical(historical, meeting, original_logic, race_no)
                source = "historical_csv"
            if not actual_map:
                continue

            try:
                context_logic = recompute_logic(logic_path, enable_legacy_barrier_bias=False)
                legacy_logic = recompute_logic(logic_path, enable_legacy_barrier_bias=True) if include_legacy_barrier else {}
            except Exception as exc:
                errors.append(f"{meeting.name} R{race_no}: {exc}")
                continue

            result_sources[source] += 1
            after_completeness = context_completeness(context_logic)
            after_audit[venue]["races"] += 1
            for key, value in after_completeness.items():
                if not value:
                    after_audit[venue][f"{key}_blank"] += 1
            context_values = [row["barrier_bias_modifier"] for row in rows_from_recomputed(context_logic)]
            if context_values and all(abs(v) < 1e-9 for v in context_values):
                after_audit[venue]["barrier_all_zero"] += 1

            summaries = {
                "baseline": summarize_race(baseline_rows, actual_map),
                "context_recompute": summarize_race(rows_from_recomputed(context_logic), actual_map),
            }
            if include_legacy_barrier:
                legacy_values = [row["barrier_bias_modifier"] for row in rows_from_recomputed(legacy_logic)]
                if legacy_values and any(abs(v) >= 1e-9 for v in legacy_values):
                    after_audit[venue]["legacy_barrier_nonzero"] += 1
                summaries["context_plus_legacy_barrier"] = summarize_race(rows_from_recomputed(legacy_logic), actual_map)
            if not summaries["baseline"].get("eligible"):
                continue
            race_groups = ["all"]
            if "canterbury" in venue_key(venue):
                race_groups.append("canterbury")
            if any(token in venue_key(venue) for token in TIGHT_TURN_VENUES):
                race_groups.append("tight_turn")
            for group in race_groups:
                for variant, race_summary in summaries.items():
                    add_metric(counters[group][variant], race_summary)
                base_top4 = summaries["baseline"]["order"][:4]
                for variant in variants:
                    if variant == "baseline":
                        continue
                    variant_top4 = summaries[variant]["order"][:4]
                    if variant_top4 != base_top4:
                        changed[group][variant] += 1
                        if len(examples[group][variant]) < 10:
                            examples[group][variant].append(
                                {
                                    "meeting": meeting.name,
                                    "race": race_no,
                                    "baseline_top4": base_top4,
                                    "variant_top4": variant_top4,
                                    "context": context_completeness(context_logic),
                                }
                            )

    results = {
        group: {
            variant: finalize(
                counters[group][variant],
                changed[group].get(variant, 0),
                examples[group].get(variant, []),
            )
            for variant in variants
        }
        for group in groups
    }
    meta = {
        "result_sources": dict(result_sources),
        "before_audit": {venue: dict(counter) for venue, counter in before_audit.items()},
        "after_audit": {venue: dict(counter) for venue, counter in after_audit.items()},
        "errors": errors[:50],
        "error_count": len(errors),
    }
    return results, meta


def delta(base: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    races = base.get("races") or 1
    return {
        "gold": candidate.get("gold", 0) - base.get("gold", 0),
        "good": candidate.get("good", 0) - base.get("good", 0),
        "pass": candidate.get("pass", 0) - base.get("pass", 0),
        "top3_win": candidate.get("top3_win", 0) - base.get("top3_win", 0),
        "top3_place": candidate.get("top3_place", 0) - base.get("top3_place", 0),
        "0hit": candidate.get("0hit", 0) - base.get("0hit", 0),
        "mrr": round(candidate.get("mrr", 0.0) - base.get("mrr", 0.0), 4),
        "place_pp": round((candidate.get("top3_place", 0) - base.get("top3_place", 0)) / (races * 3) * 100.0, 2),
    }


def build_report(results: dict[str, Any], meta: dict[str, Any]) -> str:
    lines = [
        "# AU Context Recompute Validation",
        "",
        "This report validates the context extraction rebuild by re-running the full Python engine from Logic + Facts. It does not write back meeting outputs.",
        "",
        "## Data",
        f"- Result sources: `{meta['result_sources']}`",
        f"- Recompute errors: `{meta['error_count']}`",
        "",
        "## Context Audit",
        "",
        "| Venue | Before races | Before going blank | Before profile blank | After races | After going blank | After profile blank | After barrier all-zero | Legacy barrier nonzero |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    venues = sorted(set(meta["before_audit"]) | set(meta["after_audit"]))
    for venue in venues:
        before = meta["before_audit"].get(venue, {})
        after = meta["after_audit"].get(venue, {})
        if max(before.get("races", 0), after.get("races", 0)) < 5:
            continue
        lines.append(
            f"| {venue} | {before.get('races', 0)} | {before.get('going_blank', 0)} | "
            f"{before.get('track_profile_blank', 0)} | {after.get('races', 0)} | "
            f"{after.get('going_blank', 0)} | {after.get('track_profile_blank', 0)} | "
            f"{after.get('barrier_all_zero', 0)} | {after.get('legacy_barrier_nonzero', 0)} |"
        )

    for group, variants in results.items():
        baseline = variants["baseline"]
        races = baseline.get("races", 0)
        lines += [
            "",
            f"## {group.replace('_', ' ').title()}",
            f"- Races: **{races}**",
            f"- Baseline: Gold `{baseline.get('gold',0)}`, Good `{baseline.get('good',0)}`, Pass `{baseline.get('pass',0)}`, Top3 win `{baseline.get('top3_win',0)}`, Top3 place `{baseline.get('top3_place',0)}/{races * 3 if races else 0}`",
            "",
            "| Variant | Gold | Good | Pass | Top3 Win | Top3 Place | 0-hit | MRR | Changed | Delta |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
        for name, summary in variants.items():
            d = delta(baseline, summary)
            lines.append(
                f"| {name} | {summary.get('gold',0)} | {summary.get('good',0)} | {summary.get('pass',0)} | "
                f"{summary.get('top3_win',0)} | {summary.get('top3_place',0)} | {summary.get('0hit',0)} | "
                f"{summary.get('mrr',0)} | {summary.get('changed_races',0)} | "
                f"G {d['gold']:+d}, Good {d['good']:+d}, Pass {d['pass']:+d}, Win {d['top3_win']:+d}, "
                f"Place {d['top3_place']:+d} ({d['place_pp']:+.2f}pp), 0H {d['0hit']:+d}, MRR {d['mrr']:+.4f} |"
            )
        for name, summary in variants.items():
            if name == "baseline" or not summary.get("examples"):
                continue
            lines += ["", f"### Changed Examples: {group} / {name}", ""]
            for item in summary["examples"][:5]:
                lines.append(
                    f"- {item['meeting']} R{item['race']}: `{item['baseline_top4']}` -> `{item['variant_top4']}`"
                )
    if meta["errors"]:
        lines += ["", "## Errors", ""]
        lines.extend(f"- {err}" for err in meta["errors"][:20])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AU context extraction with full engine recompute")
    parser.add_argument("--no-current", action="store_true", help="Exclude current root-level meetings")
    parser.add_argument(
        "--result-source",
        choices=("json", "historical", "both"),
        default="both",
        help="Which result source to validate against",
    )
    parser.add_argument("--include-legacy-barrier", action="store_true", help="Also validate the disabled legacy barrier-bias table")
    parser.add_argument("--output-md", default=str(OUTPUT_MD))
    parser.add_argument("--output-json", default=str(OUTPUT_JSON))
    args = parser.parse_args()

    results, meta = run_validation(
        include_current=not args.no_current,
        result_source=args.result_source,
        include_legacy_barrier=args.include_legacy_barrier,
    )
    Path(args.output_json).write_text(json.dumps({"meta": meta, "results": results}, indent=2), encoding="utf-8")
    Path(args.output_md).write_text(build_report(results, meta), encoding="utf-8")

    base = results["all"]["baseline"]
    print(
        f"Baseline all: races {base.get('races',0)} Gold {base.get('gold',0)} "
        f"Good {base.get('good',0)} Pass {base.get('pass',0)} Top3Win {base.get('top3_win',0)}"
    )
    for variant in [name for name in results["all"] if name != "baseline"]:
        d = delta(base, results["all"][variant])
        print(
            f"{variant}: Gold {d['gold']:+d} Good {d['good']:+d} Pass {d['pass']:+d} "
            f"Win {d['top3_win']:+d} Place {d['top3_place']:+d} 0H {d['0hit']:+d} MRR {d['mrr']:+.4f}"
        )
    print(f"Report: {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
