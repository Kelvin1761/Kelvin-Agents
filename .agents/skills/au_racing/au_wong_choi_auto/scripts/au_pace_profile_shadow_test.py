#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]

sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from au_sip_tester import evaluate_races, report_summary, delta_report  # type: ignore
from au_archive_calibrator import (  # type: ignore
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    choose_track_rows,
    detect_meeting_date,
    detect_meeting_track,
    load_historical_results,
    normalize_horse_name,
    parse_int,
)


def _resolve_target_meeting_dir(name: str) -> Path:
    direct = PROJECT_ROOT / name
    if direct.exists():
        return direct
    archive = PROJECT_ROOT / "Archive_Race_Analysis" / "AU_Racing" / name
    return archive


DEFAULT_TARGET_MEETINGS = [
    _resolve_target_meeting_dir("2026-05-30 Caulfield Race 1-9"),
    _resolve_target_meeting_dir("2026-05-30 Eagle Farm Race 1-9"),
    _resolve_target_meeting_dir("2026-05-30 Rosehill Gardens Race 1-10"),
]


def _pct(n: int, d: int) -> str:
    return f"{(n / d) * 100:.1f}%" if d else "0.0%"


def _condition_bucket(going: str) -> str:
    text = str(going or "").lower()
    if text.startswith(("good", "firm")):
        return "Good/Firm"
    if text.startswith("soft"):
        return "Soft"
    if text.startswith("heavy"):
        return "Heavy"
    return "Other"


def _race_class_bucket(text: str) -> str:
    value = str(text or "").lower()
    if "group 1" in value:
        return "Group 1"
    if "group 2" in value or "group 3" in value:
        return "Group 2/3"
    if "listed" in value:
        return "Listed"
    if "maiden" in value:
        return "Maiden"
    if "bm" in value:
        rating = parse_int(value, 0) or 0
        if rating >= 88:
            return "BM88+"
        if rating >= 72:
            return "BM72-84"
        return "BM58-70"
    return "Other"


def _field_size_bucket(size: int) -> str:
    if size <= 8:
        return "Field <=8"
    if size <= 12:
        return "Field 9-12"
    return "Field 13+"


def _results_lookup(results_file: Path) -> dict[int, dict[int, int]]:
    payload = json.loads(results_file.read_text(encoding="utf-8"))
    race_map: dict[int, dict[int, int]] = {}
    for race_key, rows in (payload.get("results") or {}).items():
        try:
            race_no = int(race_key)
        except (TypeError, ValueError):
            continue
        position_map = {}
        for row in rows:
            if row.get("is_scratched"):
                continue
            try:
                horse_no = int(row.get("competitor_number") or 0)
                pos = int(row.get("finish_position") or 99)
            except (TypeError, ValueError):
                continue
            position_map[horse_no] = pos
        race_map[race_no] = position_map
    return race_map


def load_target_meetings(meeting_dirs: list[Path]) -> list[dict]:
    races = []
    for meeting_dir in meeting_dirs:
        results_candidates = sorted(meeting_dir.glob("Race_Results_*.json"))
        if not results_candidates:
            continue
        results_by_race = _results_lookup(results_candidates[0])
        for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json"), key=lambda p: parse_int(p.stem.split("_")[1], 999)):
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_analysis = logic.get("race_analysis") or {}
            race_no = parse_int(race_analysis.get("race_number")) or parse_int(logic_path.stem.split("_")[1])
            actual_positions = results_by_race.get(race_no) or {}
            if not actual_positions:
                continue
            horses = []
            for horse_num, horse in (logic.get("horses") or {}).items():
                python_auto = horse.get("python_auto") or {}
                horse_number = parse_int(horse_num) or parse_int(horse.get("number")) or 999
                actual_pos = actual_positions.get(horse_number)
                if actual_pos is None:
                    continue
                horses.append(
                    {
                        "horse_number": horse_number,
                        "horse_name": str(horse.get("horse_name") or "").strip(),
                        "rank_score": float(python_auto.get("rank_score") or python_auto.get("ability_score") or 0.0),
                        "ability_score": float(python_auto.get("ability_score") or 0.0),
                        "actual_pos": int(actual_pos),
                        "condition_bucket": _condition_bucket(race_analysis.get("going", "")),
                        "risk_flags": list(python_auto.get("risk_flags") or []),
                        "matrix": python_auto.get("matrix") or {},
                        "matrix_scores": python_auto.get("matrix_scores") or {},
                        "feature_scores": python_auto.get("feature_scores") or {},
                        "barrier": parse_int(horse.get("barrier")),
                        "going": race_analysis.get("going", ""),
                        "meeting_track": meeting_dir.name,
                        "meeting_track_normalized": normalize_horse_name(meeting_dir.name),
                        "jockey": horse.get("jockey", ""),
                        "trainer": horse.get("trainer", ""),
                        "data": horse.get("_data") if isinstance(horse.get("_data"), dict) else {},
                        "speed_map": race_analysis.get("speed_map") if isinstance(race_analysis.get("speed_map"), dict) else {},
                    }
                )
            if len(horses) < 4:
                continue
            races.append(
                {
                    "meeting": meeting_dir.name,
                    "race_no": race_no,
                    "meeting_track": meeting_dir.name,
                    "meeting_track_normalized": normalize_horse_name(meeting_dir.name),
                    "race_class_bucket": _race_class_bucket(race_analysis.get("race_class")),
                    "field_size_bucket": _field_size_bucket(len(horses)),
                    "condition_bucket": horses[0]["condition_bucket"],
                    "going": race_analysis.get("going", ""),
                    "field_count": len(horses),
                    "horses": horses,
                    "speed_map": race_analysis.get("speed_map") if isinstance(race_analysis.get("speed_map"), dict) else {},
                }
            )
    return races


def load_archive_meetings() -> list[dict]:
    races = []
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)
    for meeting_dir in sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir()):
        logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"), key=lambda p: parse_int(p.stem.split("_")[1], 999))
        if not logic_files:
            continue
        sample_logic = json.loads(logic_files[0].read_text(encoding="utf-8"))
        meeting_date = detect_meeting_date(meeting_dir)
        meeting_track = detect_meeting_track(meeting_dir, sample_logic)
        if not meeting_date or not meeting_track:
            continue
        for logic_path in logic_files:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_analysis = logic.get("race_analysis") or {}
            race_no = parse_int(race_analysis.get("race_number")) or parse_int(logic_path.stem.split("_")[1])
            rows_for_race = choose_track_rows(historical_results.get((meeting_date, race_no), []), meeting_track)
            if not rows_for_race:
                continue
            race_lookup = {row["horse_slug"]: row for row in rows_for_race}
            horses = []
            for horse_num, horse in (logic.get("horses") or {}).items():
                python_auto = horse.get("python_auto") or {}
                result_row = race_lookup.get(normalize_horse_name(horse.get("horse_name")))
                if not result_row:
                    continue
                horses.append(
                    {
                        "horse_number": parse_int(horse_num) or 999,
                        "horse_name": str(horse.get("horse_name") or "").strip(),
                        "rank_score": float(python_auto.get("rank_score") or python_auto.get("ability_score") or 0.0),
                        "ability_score": float(python_auto.get("ability_score") or 0.0),
                        "actual_pos": int(result_row["pos"]),
                        "condition_bucket": _condition_bucket(result_row.get("condition") or ""),
                        "risk_flags": list(python_auto.get("risk_flags") or []),
                        "matrix": python_auto.get("matrix") or {},
                        "matrix_scores": python_auto.get("matrix_scores") or {},
                        "feature_scores": python_auto.get("feature_scores") or {},
                        "barrier": parse_int(horse.get("barrier")),
                        "going": race_analysis.get("going", ""),
                        "meeting_track": meeting_track,
                        "meeting_track_normalized": normalize_horse_name(meeting_track),
                        "jockey": horse.get("jockey", ""),
                        "trainer": horse.get("trainer", ""),
                        "data": horse.get("_data") if isinstance(horse.get("_data"), dict) else {},
                        "speed_map": race_analysis.get("speed_map") if isinstance(race_analysis.get("speed_map"), dict) else {},
                    }
                )
            if len(horses) < 4:
                continue
            races.append(
                {
                    "meeting": meeting_dir.name,
                    "race_no": race_no,
                    "meeting_track": meeting_track,
                    "meeting_track_normalized": normalize_horse_name(meeting_track),
                    "race_class_bucket": _race_class_bucket(race_analysis.get("race_class")),
                    "field_size_bucket": _field_size_bucket(len(horses)),
                    "condition_bucket": horses[0]["condition_bucket"],
                    "going": race_analysis.get("going", ""),
                    "field_count": len(horses),
                    "horses": horses,
                    "speed_map": race_analysis.get("speed_map") if isinstance(race_analysis.get("speed_map"), dict) else {},
                }
            )
    return races


def _soft_profile_cap(horses: list[dict], race: dict) -> list[dict]:
    for h in horses:
        feature_scores = h.get("feature_scores") or {}
        confidence = float(feature_scores.get("confidence_score", 60))
        consistency = float(feature_scores.get("consistency_score", 60))
        formline = float(feature_scores.get("formline_score", 60))
        form = float(feature_scores.get("form_score", 60))
        sectional = float(feature_scores.get("sectional_score", 60))
        pace = float(feature_scores.get("pace_map_score", 60))
        distance = float(feature_scores.get("distance_score", 60))
        class_score = float(feature_scores.get("class_score", 60))

        soft_flags = sum(score >= 72 for score in (confidence, consistency, formline))
        hard_weak_flags = sum(score <= 60 for score in (form, sectional, pace, distance))
        hard_medium_flags = sum(score < 64 for score in (form, sectional, pace, distance, class_score))
        penalty = 0.0

        if soft_flags >= 2 and hard_weak_flags >= 2:
            penalty -= 1.8
        elif soft_flags >= 2 and hard_medium_flags >= 3:
            penalty -= 1.0

        if confidence >= 86 and consistency >= 74 and pace <= 58 and sectional <= 60:
            penalty -= 0.8

        if penalty:
            h["rank_score"] = h["rank_score"] + penalty
    return horses


def _pace_bucket(speed_map: dict) -> str:
    return str(speed_map.get("predicted_pace") or "")


def _pace_conf(speed_map: dict) -> str:
    return str(speed_map.get("pace_confidence") or "")


def _horse_style_group(horse_number: int, speed_map: dict) -> str:
    for key in ("leaders", "pressers", "on_pace", "mid_pack", "closers"):
        values = speed_map.get(key) or []
        if horse_number in values:
            return key
    return "unknown"


def _pace_clear_only_rerank(horses: list[dict], race: dict) -> list[dict]:
    speed_map = race.get("speed_map") or {}
    if _pace_conf(speed_map) != "Clear":
        return horses

    pace = _pace_bucket(speed_map)
    for h in horses:
        style_group = _horse_style_group(h["horse_number"], speed_map)
        feature_scores = h.get("feature_scores") or {}
        sectional = float(feature_scores.get("sectional_score", 60))
        pace_map = float(feature_scores.get("pace_map_score", 60))
        bonus = 0.0

        if pace in {"極慢", "慢"}:
            if style_group in {"leaders", "pressers", "on_pace"}:
                bonus += 0.8
            if style_group == "closers":
                bonus -= 0.8
        elif pace in {"快", "極快"}:
            if style_group == "closers":
                bonus += 0.8
            if style_group in {"leaders", "pressers"}:
                bonus -= 0.8

        if bonus > 0 and (sectional >= 68 or pace_map >= 66):
            bonus += 0.3
        if bonus < 0 and sectional >= 74:
            bonus += 0.2

        if bonus:
            h["rank_score"] = h["rank_score"] + bonus
    return horses


def _near_miss_hard_context_promotion(horses: list[dict], race: dict) -> list[dict]:
    ranked = sorted(horses, key=lambda h: (-h["rank_score"], h["horse_number"]))
    top3_numbers = {h["horse_number"] for h in ranked[:3]}
    speed_map = race.get("speed_map") or {}
    pace_conf = _pace_conf(speed_map)

    for h in horses:
        if h["horse_number"] in top3_numbers:
            continue
        legacy_rank = 1 + sum(
            1
            for other in ranked
            if (other["rank_score"], -other["horse_number"]) > (h["rank_score"], -h["horse_number"])
        )
        if legacy_rank not in {4, 5, 6}:
            continue

        feature_scores = h.get("feature_scores") or {}
        matrix_scores = h.get("matrix_scores") or {}
        form = float(feature_scores.get("form_score", 60))
        sectional = float(feature_scores.get("sectional_score", 60))
        pace_map = float(feature_scores.get("pace_map_score", 60))
        distance = float(feature_scores.get("distance_score", 60))
        class_score = float(feature_scores.get("class_score", 60))
        jt_fit = float(feature_scores.get("jockey_horse_fit_score", 60))
        formline = float(feature_scores.get("formline_score", 60))
        race_shape = float(matrix_scores.get("race_shape", 60))
        jockey_trainer = float(matrix_scores.get("jockey_trainer", 60))

        bonus = 0.0
        strong_hard = sum(score >= 68 for score in (sectional, distance, class_score, form, formline))
        if strong_hard >= 3:
            bonus += 0.75
        if sectional >= 72 and distance >= 66:
            bonus += 0.35
        if class_score >= 68 and formline >= 68:
            bonus += 0.35
        if pace_conf == "Clear" and race_shape >= 68 and pace_map >= 66:
            bonus += 0.45
        if jockey_trainer >= 72 and jt_fit >= 70:
            bonus += 0.25

        if bonus:
            h["rank_score"] = h["rank_score"] + bonus
    return horses


def variant_combined(horses: list[dict], race: dict) -> list[dict]:
    horses = _soft_profile_cap(horses, race)
    horses = _pace_clear_only_rerank(horses, race)
    horses = _near_miss_hard_context_promotion(horses, race)
    return horses


VARIANTS = {
    "soft_profile_cap": _soft_profile_cap,
    "pace_clear_only_rerank": _pace_clear_only_rerank,
    "near_miss_hard_context_promotion": _near_miss_hard_context_promotion,
    "combined": variant_combined,
}


def _print_summary(title: str, summary: dict, delta: dict | None = None) -> None:
    print(f"\n## {title}")
    print(
        f"races={summary['races']} champion={summary['champion']} gold={summary['gold']} "
        f"good={summary['good']} pass={summary['pass']} top3_place={summary['top3_place']} "
        f"0hit={summary['0hit']} 1hit={summary['1hit']}"
    )
    if delta:
        print(
            "delta "
            f"gold={delta['gold_delta']:+.1f} good={delta['good_delta']:+.1f} "
            f"pass={delta['pass_delta']:+.1f} place={delta['place_delta']:+.1f} "
            f"0hit={delta['0hit_delta']:+d} 1hit={delta['1hit_delta']:+d}"
        )


def _meeting_breakdown(races: list[dict], adjust_fn=None) -> list[dict]:
    rows = []
    by_meeting: dict[str, list[dict]] = defaultdict(list)
    for race in races:
        by_meeting[race["meeting"]].append(race)
    for meeting, meeting_races in sorted(by_meeting.items()):
        overall, _, _, _ = evaluate_races(meeting_races, meeting, adjust_fn)
        rows.append(report_summary(overall, meeting))
    return rows


def _render_md_table(rows: list[dict]) -> list[str]:
    lines = [
        "| Meeting | Races | Champion | Gold | Good | Pass | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['label']} | {row['races']} | {row['champion']} | {row['gold']} | {row['good']} | {row['pass']} | "
            f"{row['top3_place']} | {row['0hit']} | {row['1hit']} | {row['2hit']} | {row['3hit']} |"
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="AU pace/profile shadow test")
    parser.add_argument("--variant", choices=[*VARIANTS.keys(), "all"], default="all")
    parser.add_argument("--output-md", help="Optional markdown report path")
    args = parser.parse_args()

    print("📦 Loading archive races...")
    archive_races = load_archive_meetings()
    print(f"   loaded {len(archive_races)} archive races")

    print("📦 Loading target meetings...")
    target_races = load_target_meetings(DEFAULT_TARGET_MEETINGS)
    print(f"   loaded {len(target_races)} target races")

    variants = VARIANTS if args.variant == "all" else {args.variant: VARIANTS[args.variant]}

    baseline_archive, _, _, _ = evaluate_races(archive_races, "archive_baseline")
    baseline_target, _, _, _ = evaluate_races(target_races, "target_baseline")
    archive_summary = report_summary(baseline_archive, "Archive Baseline")
    target_summary = report_summary(baseline_target, "05-30 Baseline")
    _print_summary("Archive Baseline", archive_summary)
    _print_summary("05-30 Baseline", target_summary)

    md_lines = [
        "# AU Pace / Profile Shadow Test",
        "",
        "## Baseline",
        "",
        f"- Archive races: `{archive_summary['races']}`",
        f"- Target races: `{target_summary['races']}`",
        "",
    ]

    for name, fn in variants.items():
        archive_variant, _, _, _ = evaluate_races(archive_races, name, fn)
        target_variant, _, _, _ = evaluate_races(target_races, name, fn)
        archive_variant_summary = report_summary(archive_variant, name)
        target_variant_summary = report_summary(target_variant, name)
        archive_delta = delta_report(baseline_archive, archive_variant)
        target_delta = delta_report(baseline_target, target_variant)

        _print_summary(f"{name} / archive", archive_variant_summary, archive_delta)
        _print_summary(f"{name} / 05-30", target_variant_summary, target_delta)

        md_lines.extend(
            [
                f"## {name}",
                "",
                "### Archive",
                "",
                f"- Champion: `{archive_summary['champion']}` -> `{archive_variant_summary['champion']}`",
                f"- Gold: `{archive_summary['gold']}` -> `{archive_variant_summary['gold']}`",
                f"- Good: `{archive_summary['good']}` -> `{archive_variant_summary['good']}`",
                f"- Pass: `{archive_summary['pass']}` -> `{archive_variant_summary['pass']}`",
                f"- Top3 Place: `{archive_summary['top3_place']}` -> `{archive_variant_summary['top3_place']}`",
                f"- Delta: gold `{archive_delta['gold_delta']:+.1f}`, good `{archive_delta['good_delta']:+.1f}`, pass `{archive_delta['pass_delta']:+.1f}`, place `{archive_delta['place_delta']:+.1f}`, 0-hit `{archive_delta['0hit_delta']:+d}`",
                "",
                "### 05-30 Triple Header",
                "",
                f"- Champion: `{target_summary['champion']}` -> `{target_variant_summary['champion']}`",
                f"- Gold: `{target_summary['gold']}` -> `{target_variant_summary['gold']}`",
                f"- Good: `{target_summary['good']}` -> `{target_variant_summary['good']}`",
                f"- Pass: `{target_summary['pass']}` -> `{target_variant_summary['pass']}`",
                f"- Top3 Place: `{target_summary['top3_place']}` -> `{target_variant_summary['top3_place']}`",
                f"- Delta: gold `{target_delta['gold_delta']:+.1f}`, good `{target_delta['good_delta']:+.1f}`, pass `{target_delta['pass_delta']:+.1f}`, place `{target_delta['place_delta']:+.1f}`, 0-hit `{target_delta['0hit_delta']:+d}`",
                "",
                "### 05-30 Meeting Breakdown",
                "",
            ]
        )
        md_lines.extend(_render_md_table(_meeting_breakdown(target_races, fn)))
        md_lines.append("")

    if args.output_md:
        Path(args.output_md).write_text("\n".join(md_lines), encoding="utf-8")
        print(f"\n📝 wrote {args.output_md}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
