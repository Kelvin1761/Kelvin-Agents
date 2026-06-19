#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import sys

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT,
    FEATURE_SCORE_KEYS,
    HISTORICAL_RESULTS_CSV,
    MATRIX_KEYS,
    load_historical_results,
    normalize_horse_name,
    normalize_track_name,
    parse_float,
    parse_int,
)
from au_zero_hit_race_audit import field_size_bucket, race_class_bucket  # noqa: E402
from hidden_signal_rescue import (  # noqa: E402
    VARIANT_LABELS,
    add_rank_metadata,
    apply_hidden_signal_variant,
)
from matrix_mapper import map_features_to_matrix_scores  # noqa: E402


OUTPUT_MD = ARCHIVE_ROOT / "AU_Hidden_Signal_Rescue_Backtest.md"
OUTPUT_JSON = ARCHIVE_ROOT / "AU_Hidden_Signal_Rescue_Backtest.json"
EAGLE_FARM_HOLDOUT = PROJECT_ROOT / "2026-06-13 Eagle Farm Race 1-9"
VARIANTS = (
    "v1_formline_merit",
    "v2_trial_jt_comeback",
    "v3_sectional_hardness_relief",
    "v4_combined_conservative",
)


def pct(n: int | float, d: int | float) -> str:
    return f"{(n / d * 100):.1f}%" if d else "0.0%"


def metric_bucket() -> dict[str, Any]:
    return {
        "races": 0,
        "champion": 0,
        "gold": 0,
        "good": 0,
        "pass": 0,
        "winner_top3": 0,
        "winner_top5": 0,
        "top3_places": 0,
        "top3_slots": 0,
        "hit_distribution": Counter(),
    }


def evaluate_ranked(ranked: list[dict[str, Any]], bucket: dict[str, Any]) -> None:
    top3 = ranked[:3]
    top5 = ranked[:5]
    top2 = ranked[:2]
    hits = sum(1 for row in top3 if int(row["actual_pos"]) <= 3)
    top2_hits = sum(1 for row in top2 if int(row["actual_pos"]) <= 3)
    bucket["races"] += 1
    bucket["top3_places"] += hits
    bucket["top3_slots"] += len(top3)
    bucket["hit_distribution"][hits] += 1
    if top3 and int(top3[0]["actual_pos"]) == 1:
        bucket["champion"] += 1
    if any(int(row["actual_pos"]) == 1 for row in top3):
        bucket["winner_top3"] += 1
    if any(int(row["actual_pos"]) == 1 for row in top5):
        bucket["winner_top5"] += 1
    if hits == 3:
        bucket["gold"] += 1
    if top2_hits == 2:
        bucket["good"] += 1
    if hits >= 2:
        bucket["pass"] += 1


def summarize(bucket: dict[str, Any]) -> dict[str, Any]:
    races = bucket["races"]
    slots = bucket["top3_slots"]
    return {
        "races": races,
        "champion": bucket["champion"],
        "champion_pct": pct(bucket["champion"], races),
        "gold": bucket["gold"],
        "gold_pct": pct(bucket["gold"], races),
        "good": bucket["good"],
        "good_pct": pct(bucket["good"], races),
        "pass": bucket["pass"],
        "pass_pct": pct(bucket["pass"], races),
        "winner_top3": bucket["winner_top3"],
        "winner_top3_pct": pct(bucket["winner_top3"], races),
        "winner_top5": bucket["winner_top5"],
        "winner_top5_pct": pct(bucket["winner_top5"], races),
        "top3_places": bucket["top3_places"],
        "top3_place_pct": pct(bucket["top3_places"], slots),
        "0hit": bucket["hit_distribution"][0],
        "1hit": bucket["hit_distribution"][1],
        "2hit": bucket["hit_distribution"][2],
        "3hit": bucket["hit_distribution"][3],
    }


def delta(base: dict[str, Any], item: dict[str, Any]) -> dict[str, int]:
    return {
        "gold": item["gold"] - base["gold"],
        "good": item["good"] - base["good"],
        "pass": item["pass"] - base["pass"],
        "0hit": item["hit_distribution"][0] - base["hit_distribution"][0],
        "1hit": item["hit_distribution"][1] - base["hit_distribution"][1],
        "top3_places": item["top3_places"] - base["top3_places"],
        "winner_top5": item["winner_top5"] - base["winner_top5"],
    }


def clean_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    out = dict(bucket)
    out["hit_distribution"] = dict(bucket["hit_distribution"])
    return out


def rank_label(row: dict[str, Any]) -> str:
    extra = ""
    modifier = float(row.get("hidden_signal_rescue_modifier") or 0.0)
    if modifier:
        extra = f", +{modifier:.2f} {row.get('hidden_signal_variant', '')}"
    return f"#{row['horse_number']} {row['horse_name']} (rank {row.get('model_rank')}, pos {row['actual_pos']}, score {float(row.get('shadow_score', row.get('rank_score', 0))):.2f}{extra})"


def load_archive_races() -> list[list[dict[str, Any]]]:
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)
    races = []
    meetings = sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir())
    for index, meeting_dir in enumerate(meetings, start=1):
        if index == 1 or index % 10 == 0:
            print(f"Loading archive meeting {index}/{len(meetings)}: {meeting_dir.name}", flush=True)
        local_results, local_meta = _load_local_results(meeting_dir)
        meeting_date = _meeting_date(meeting_dir)
        meeting_track = _meeting_track(meeting_dir)
        for scoring_path in sorted(meeting_dir.glob("Race_*_Auto_Scoring.csv"), key=lambda path: parse_int(path.stem.split("_")[1], 999) or 999):
            race_no = parse_int(scoring_path.stem.split("_")[1])
            if not race_no:
                continue
            actual = local_results.get(race_no)
            if not actual:
                actual = _historical_positions(
                    historical_results.get((meeting_date, race_no), []),
                    meeting_track,
                )
            if not actual:
                continue
            meta = local_meta.get(race_no, {})
            race_rows = _load_scoring_race(
                scoring_path,
                meeting=meeting_dir.name,
                race_no=race_no,
                actual_positions=actual,
                race_class=str(meta.get("event_class") or ""),
                condition=_condition_bucket(str(meta.get("track_condition") or "")),
            )
            if len([row for row in race_rows if int(row["actual_pos"]) <= 3]) >= 3:
                races.append(race_rows)
    return races


def _load_scoring_race(
    scoring_path: Path,
    *,
    meeting: str,
    race_no: int,
    actual_positions: dict[int, int] | dict[str, int],
    race_class: str,
    condition: str,
) -> list[dict[str, Any]]:
    rows = []
    with scoring_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            horse_no = parse_int(row.get("horse_number"))
            if horse_no is None:
                continue
            actual_pos = actual_positions.get(horse_no)
            if actual_pos is None:
                actual_pos = actual_positions.get(normalize_horse_name(row.get("horse_name") or ""))
            if actual_pos is None:
                continue
            feature_scores = {
                key: parse_float(row.get(key), 60.0) or 60.0
                for key in FEATURE_SCORE_KEYS
            }
            rows.append(
                {
                    "meeting": meeting,
                    "race": race_no,
                    "race_class": race_class,
                    "condition_bucket": condition or "Unknown",
                    "horse_number": horse_no,
                    "horse_name": str(row.get("horse_name") or "").strip(),
                    "actual_pos": actual_pos,
                    "rank_score": parse_float(row.get("rank_score"), None)
                    if row.get("rank_score") not in (None, "")
                    else parse_float(row.get("ability_score"), 0.0) or 0.0,
                    "ability_score": parse_float(row.get("ability_score"), 0.0) or 0.0,
                    "feature_scores": feature_scores,
                    "matrix_scores": {
                        key: float(value)
                        for key, value in map_features_to_matrix_scores(feature_scores).items()
                        if key in MATRIX_KEYS
                    },
                    "risk_flags": [],
                }
            )
    return rows


def _load_local_results(meeting_dir: Path) -> tuple[dict[int, dict[int, int]], dict[int, dict[str, Any]]]:
    json_paths = sorted(path for path in meeting_dir.glob("Race_Results_*.json") if "Reflector" not in path.name)
    if not json_paths:
        return {}, {}
    try:
        data = json.loads(json_paths[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, {}
    results: dict[int, dict[int, int]] = {}
    for race_key, rows in (data.get("results") or {}).items():
        race_no = parse_int(race_key)
        if not race_no:
            continue
        results[race_no] = {}
        for row in rows:
            horse_no = parse_int(row.get("competitor_number"))
            finish = parse_int(row.get("finish_position"), 99)
            if horse_no is None or row.get("is_scratched") or not finish or finish >= 99:
                continue
            results[race_no][horse_no] = finish
    meta = {}
    for race_key, item in (data.get("events") or {}).items():
        race_no = parse_int(race_key)
        if race_no:
            meta[race_no] = item if isinstance(item, dict) else {}
    return results, meta


def _historical_positions(rows: list[dict[str, Any]], meeting_track: str) -> dict[str, int]:
    if not rows:
        return {}
    target = normalize_track_name(meeting_track)
    track_rows = [row for row in rows if row.get("track_slug") == target] or rows
    return {normalize_horse_name(row.get("horse") or ""): int(row["pos"]) for row in track_rows if row.get("pos")}


def _meeting_date(meeting_dir: Path) -> str:
    match = re.match(r"(\d{4}-\d{2}-\d{2})", meeting_dir.name)
    return match.group(1) if match else ""


def _meeting_track(meeting_dir: Path) -> str:
    name = re.sub(r"^\d{4}-\d{2}-\d{2}\s+", "", meeting_dir.name)
    name = re.sub(r"\s+Race\s+\d+-\d+$", "", name)
    return name.strip()


def load_eagle_farm_holdout() -> list[list[dict[str, Any]]]:
    if not EAGLE_FARM_HOLDOUT.exists():
        return []
    results_files = sorted(EAGLE_FARM_HOLDOUT.glob("Race_Results_Eagle_Farm_2026-06-13.json"))
    if not results_files:
        return []
    results_data = json.loads(results_files[0].read_text(encoding="utf-8"))
    result_map: dict[int, dict[int, int]] = {}
    for race_key, rows in (results_data.get("results") or {}).items():
        race_no = parse_int(race_key)
        if not race_no:
            continue
        result_map[race_no] = {}
        for row in rows:
            horse_no = parse_int(row.get("competitor_number"))
            finish = parse_int(row.get("finish_position"), 99)
            if horse_no is None or row.get("is_scratched") or not finish or finish >= 99:
                continue
            result_map[race_no][horse_no] = finish

    races = []
    for scoring_path in sorted(EAGLE_FARM_HOLDOUT.glob("Race_*_Auto_Scoring.csv"), key=lambda path: parse_int(path.stem.split("_")[1], 999) or 999):
        race_no = parse_int(scoring_path.stem.split("_")[1])
        if not race_no or race_no not in result_map:
            continue
        event_meta = (results_data.get("events") or {}).get(str(race_no), {})
        race_rows = _load_scoring_race(
            scoring_path,
            meeting=EAGLE_FARM_HOLDOUT.name,
            race_no=race_no,
            actual_positions=result_map[race_no],
            race_class=str(event_meta.get("event_class") or ""),
            condition=_condition_bucket(str(event_meta.get("track_condition") or "")),
        )
        if len([row for row in race_rows if int(row["actual_pos"]) <= 3]) >= 3:
            races.append(race_rows)
    return races


def _condition_bucket(text: str) -> str:
    lower = str(text or "").lower()
    if lower.startswith(("good", "firm")):
        return "Good/Firm"
    if lower.startswith("soft"):
        return "Soft"
    if lower.startswith("heavy"):
        return "Heavy"
    return "Other"


def evaluate_dataset(races: list[list[dict[str, Any]]]) -> dict[str, Any]:
    labels = ["Baseline", *[VARIANT_LABELS[name] for name in VARIANTS]]
    results = {label: metric_bucket() for label in labels}
    by_condition = defaultdict(lambda: {label: metric_bucket() for label in labels})
    by_class = defaultdict(lambda: {label: metric_bucket() for label in labels})
    by_field = defaultdict(lambda: {label: metric_bucket() for label in labels})
    candidate_stats = {VARIANT_LABELS[name]: Counter() for name in VARIANTS}
    reason_counts = {VARIANT_LABELS[name]: Counter() for name in VARIANTS}
    examples = []

    for race_rows in races:
        baseline = add_rank_metadata(race_rows)
        versions = {"Baseline": baseline}
        decisions = {}
        for variant in VARIANTS:
            ranked, candidates = apply_hidden_signal_variant(race_rows, variant)
            label = VARIANT_LABELS[variant]
            versions[label] = ranked
            decisions[label] = candidates
            candidate_stats[label]["races_with_candidate"] += int(bool(candidates))
            candidate_stats[label]["candidate_count"] += len(candidates)
            for candidate in candidates:
                actual = next((row for row in ranked if int(row["horse_number"]) == int(candidate["horse_number"])), {})
                if int(actual.get("actual_pos") or 99) <= 3:
                    candidate_stats[label]["candidate_actual_top3"] += 1
                for reason in candidate.get("reasons", []):
                    reason_counts[label][reason] += 1

        condition = str(baseline[0].get("condition_bucket") or "Unknown")
        class_bucket = race_class_bucket(baseline[0].get("race_class"))
        field_bucket = field_size_bucket(len(baseline))
        baseline_hits = _top3_hits(baseline)

        for label, ranked in versions.items():
            evaluate_ranked(ranked, results[label])
            evaluate_ranked(ranked, by_condition[condition][label])
            evaluate_ranked(ranked, by_class[class_bucket][label])
            evaluate_ranked(ranked, by_field[field_bucket][label])
            if label != "Baseline":
                hits = _top3_hits(ranked)
                if hits != baseline_hits and len(examples) < 40:
                    examples.append(
                        {
                            "label": label,
                            "meeting": baseline[0].get("meeting"),
                            "race": baseline[0].get("race"),
                            "baseline_hits": baseline_hits,
                            "shadow_hits": hits,
                            "condition": condition,
                            "class": class_bucket,
                            "field": field_bucket,
                            "baseline_top3": [rank_label(row) for row in baseline[:3]],
                            "shadow_top3": [rank_label(row) for row in ranked[:3]],
                        }
                    )

    return {
        "results": results,
        "by_condition": by_condition,
        "by_class": by_class,
        "by_field": by_field,
        "candidate_stats": candidate_stats,
        "reason_counts": reason_counts,
        "examples": examples,
    }


def _top3_hits(ranked: list[dict[str, Any]]) -> int:
    return sum(1 for row in ranked[:3] if int(row["actual_pos"]) <= 3)


def promotion_gate(archive: dict[str, Any], holdout: dict[str, Any]) -> dict[str, Any]:
    label = VARIANT_LABELS["v4_combined_conservative"]
    archive_base = archive["results"]["Baseline"]
    archive_v4 = archive["results"][label]
    holdout_base = holdout["results"]["Baseline"]
    holdout_v4 = holdout["results"][label]
    checks = {
        "archive_pass_not_lower": archive_v4["pass"] >= archive_base["pass"],
        "archive_top3_places_not_lower": archive_v4["top3_places"] >= archive_base["top3_places"],
        "archive_0hit_not_higher": archive_v4["hit_distribution"][0] <= archive_base["hit_distribution"][0],
        "archive_winner_top5_tolerance": archive_v4["winner_top5"] >= archive_base["winner_top5"] - 1,
        "holdout_pass_not_lower": holdout_v4["pass"] >= holdout_base["pass"],
        "holdout_top3_places_not_lower": holdout_v4["top3_places"] >= holdout_base["top3_places"],
        "holdout_winner_top5_not_lower": holdout_v4["winner_top5"] >= holdout_base["winner_top5"],
    }
    return {"passed": all(checks.values()), "checks": checks}


def render_summary_table(results: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, bucket in results.items():
        s = summarize(bucket)
        lines.append(
            f"| {label} | {s['races']} | {s['champion_pct']} | {s['gold']} ({s['gold_pct']}) | "
            f"{s['good']} ({s['good_pct']}) | {s['pass']} ({s['pass_pct']}) | "
            f"{s['winner_top3_pct']} | {s['winner_top5_pct']} | {s['top3_place_pct']} | "
            f"{s['0hit']} | {s['1hit']} | {s['2hit']} | {s['3hit']} |"
        )
    return lines


def render_delta_table(results: dict[str, dict[str, Any]]) -> list[str]:
    baseline = results["Baseline"]
    lines = [
        "| Version | Gold Δ | Good Δ | Pass Δ | 0-hit Δ | 1-hit Δ | Top3 places Δ | Winner Top5 Δ |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, bucket in results.items():
        if label == "Baseline":
            continue
        d = delta(baseline, bucket)
        lines.append(
            f"| {label} | {d['gold']:+d} | {d['good']:+d} | {d['pass']:+d} | "
            f"{d['0hit']:+d} | {d['1hit']:+d} | {d['top3_places']:+d} | {d['winner_top5']:+d} |"
        )
    return lines


def render_segment(title: str, segment_data: dict[str, dict[str, dict[str, Any]]]) -> list[str]:
    lines = ["", f"## {title}", ""]
    for segment, results in sorted(segment_data.items()):
        lines.extend([f"### {segment}", "", *render_summary_table(results), ""])
    return lines


def render_candidate_quality(candidate_stats: dict[str, Counter], reason_counts: dict[str, Counter]) -> list[str]:
    lines = [
        "## Candidate Quality",
        "",
        "| Version | Races With Candidate | Candidates | Candidate Actual Top3 |",
        "|---|---:|---:|---:|",
    ]
    for label, stats in candidate_stats.items():
        lines.append(
            f"| {label} | {stats['races_with_candidate']} | {stats['candidate_count']} | "
            f"{stats['candidate_actual_top3']} ({pct(stats['candidate_actual_top3'], stats['candidate_count'])}) |"
        )
    for label, counts in reason_counts.items():
        lines.extend(["", f"Top reasons - {label}:"])
        if not counts:
            lines.append("- None")
        for reason, count in counts.most_common(8):
            lines.append(f"- {reason}: **{count}**")
    return lines


def render_examples(examples: list[dict[str, Any]], title: str) -> list[str]:
    lines = ["", f"## {title}", ""]
    if not examples:
        return lines + ["- No changed Top3 examples.", ""]
    for item in examples[:20]:
        direction = "IMPROVED" if item["shadow_hits"] > item["baseline_hits"] else "WORSE"
        lines.extend(
            [
                f"### {direction} - {item['label']} - {item['meeting']} R{item['race']}",
                f"- Context: {item['condition']} / {item['class']} / {item['field']}",
                f"- Hits: {item['baseline_hits']} -> {item['shadow_hits']}",
                "- Baseline Top3:",
                *[f"  - {line}" for line in item["baseline_top3"]],
                "- Shadow Top3:",
                *[f"  - {line}" for line in item["shadow_top3"]],
                "",
            ]
        )
    return lines


def write_outputs(archive: dict[str, Any], holdout: dict[str, Any], gate: dict[str, Any]) -> None:
    lines = [
        "# AU Hidden-Signal Rescue Backtest",
        "",
        "Market-free shadow test. Live `rank_score`, `final_rank_score`, and official rankings are unchanged.",
        "",
        "## Archive Metrics",
        "",
        *render_summary_table(archive["results"]),
        "",
        "## Archive Delta vs Baseline",
        "",
        *render_delta_table(archive["results"]),
        "",
        "## Eagle Farm 2026-06-13 Holdout",
        "",
        *render_summary_table(holdout["results"]),
        "",
        "## Eagle Farm Delta vs Baseline",
        "",
        *render_delta_table(holdout["results"]),
        "",
        "## Promotion Gate",
        "",
        f"- V4 gate: **{'PASS' if gate['passed'] else 'FAIL'}**",
    ]
    for name, ok in gate["checks"].items():
        lines.append(f"- {'PASS' if ok else 'FAIL'} `{name}`")
    if gate["passed"]:
        lines.extend([
            "",
            "Recommendation: V4 passed the promotion gate and is eligible for report-only activation.",
        ])
    else:
        lines.extend([
            "",
            "Recommendation: V4 failed the promotion gate. Keep report-only modifiers disabled and continue shadow research.",
        ])
    lines.extend(["", *render_candidate_quality(archive["candidate_stats"], archive["reason_counts"])])
    lines.extend(render_segment("Archive Segment - Condition", archive["by_condition"]))
    lines.extend(render_segment("Archive Segment - Class", archive["by_class"]))
    lines.extend(render_segment("Archive Segment - Field Size", archive["by_field"]))
    lines.extend(render_examples(archive["examples"], "Archive Changed Examples"))
    lines.extend(render_examples(holdout["examples"], "Eagle Farm Changed Examples"))
    OUTPUT_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    payload = {
        "archive": _jsonable(archive),
        "eagle_farm_holdout": _jsonable(holdout),
        "promotion_gate": gate,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Counter):
        return dict(value)
    if isinstance(value, defaultdict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def main() -> int:
    archive_races = load_archive_races()
    holdout_races = load_eagle_farm_holdout()
    if not archive_races:
        raise SystemExit("No archive races found for hidden-signal rescue backtest.")
    if not holdout_races:
        raise SystemExit("No Eagle Farm 2026-06-13 holdout races found.")
    archive = evaluate_dataset(archive_races)
    holdout = evaluate_dataset(holdout_races)
    gate = promotion_gate(archive, holdout)
    write_outputs(archive, holdout, gate)
    print(f"Archive races: {archive['results']['Baseline']['races']}")
    print(f"Eagle Farm holdout races: {holdout['results']['Baseline']['races']}")
    print(f"Promotion gate: {'PASS' if gate['passed'] else 'FAIL'}")
    print(f"Report: {OUTPUT_MD}")
    print(f"JSON: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
