#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from au_archive_calibrator import ARCHIVE_ROOT, normalize_condition_bucket  # noqa: E402
from au_cached_walkforward_ml import (  # noqa: E402
    DATASET_CSV,
    as_float,
    date_folds,
    fmt_metrics,
    group_races,
    materialize_dataset,
    metrics_for_races,
    score_baseline,
)
from engine_core import _record_rows  # noqa: E402


OUTPUT_MD = PROJECT_ROOT / "2026-06-07 AU Soft Wet-Proof Cap Test.md"
PROMOTION_CANDIDATES = ("balanced_cap",)


def is_soft_race(race: list[dict]) -> bool:
    return normalize_condition_bucket(race[0].get("condition_bucket", "")) == "Soft"


def logic_path_for(row: dict) -> Path:
    return ARCHIVE_ROOT / str(row["meeting"]) / f"Race_{int(row['race'])}_Logic.json"


def horse_logic_lookup(logic: dict) -> dict[int, dict]:
    output = {}
    for horse_no, horse in (logic.get("horses") or {}).items():
        try:
            output[int(horse_no)] = horse
        except (TypeError, ValueError):
            continue
    return output


def parse_int(value, default=0) -> int:
    match = re.search(r"-?\d+", str(value or ""))
    return int(match.group(0)) if match else default


def is_wet_entry(cols: list[str]) -> bool:
    going = str(cols[5] if len(cols) > 5 else "")
    if any(token in going for token in ("Soft", "Heavy", "軟", "重")):
        return True
    number = parse_int(going, -1)
    return number >= 5


def placed(placing: str) -> bool:
    pos = parse_int(placing, 99)
    return 1 <= pos <= 3


def extract_wet_proof(horse: dict) -> dict:
    facts = str((horse.get("_data") or {}).get("facts_section") or "")
    wet_runs = 0
    wet_places = 0
    soft_runs = 0
    soft_places = 0
    heavy_runs = 0
    heavy_places = 0
    wide_or_unstable = 0
    for cols in _record_rows(facts):
        if len(cols) < 16 or "試閘" in cols[1]:
            continue
        if not is_wet_entry(cols):
            continue
        going = str(cols[5])
        wet_runs += 1
        if placed(cols[7]):
            wet_places += 1
        if "Soft" in going or "軟" in going or 5 <= parse_int(going, -1) <= 7:
            soft_runs += 1
            if placed(cols[7]):
                soft_places += 1
        if "Heavy" in going or "重" in going or parse_int(going, -1) >= 8:
            heavy_runs += 1
            if placed(cols[7]):
                heavy_places += 1
        notes = " ".join(cols[9:17])
        if any(token in notes for token in ("wide", "Wide", "caught wide", "慢出", "slow", "Wd", "外")):
            wide_or_unstable += 1
    return {
        "wet_runs": wet_runs,
        "wet_places": wet_places,
        "soft_runs": soft_runs,
        "soft_places": soft_places,
        "heavy_runs": heavy_runs,
        "heavy_places": heavy_places,
        "wide_or_unstable": wide_or_unstable,
    }


def attach_wet_proof(races: list[list[dict]]) -> list[list[dict]]:
    logic_cache: dict[Path, dict] = {}
    output = []
    for race in races:
        scored_race = []
        for row in race:
            item = dict(row)
            item["_wet_proof"] = {
                "wet_runs": 0,
                "wet_places": 0,
                "soft_runs": 0,
                "soft_places": 0,
                "heavy_runs": 0,
                "heavy_places": 0,
                "wide_or_unstable": 0,
            }
            if is_soft_race(race):
                logic_path = logic_path_for(row)
                if logic_path not in logic_cache:
                    logic_cache[logic_path] = json.loads(logic_path.read_text(encoding="utf-8"))
                horse = horse_logic_lookup(logic_cache[logic_path]).get(int(row["horse_number"]))
                if horse:
                    item["_wet_proof"] = extract_wet_proof(horse)
            scored_race.append(item)
        output.append(scored_race)
    return output


def risk_flags(row: dict) -> list[str]:
    proof = row.get("_wet_proof") or {}
    flags = []
    ability = as_float(row.get("ability_score"), 0.0)
    track = as_float(row.get("mx_track"), 60.0)
    sectional = as_float(row.get("mx_sectional"), 60.0)
    stability = as_float(row.get("mx_stability"), 60.0)
    race_shape = as_float(row.get("mx_race_shape"), 60.0)
    barrier = int(row.get("horse_number") or 0)
    no_wet_place = int(proof.get("wet_places") or 0) == 0
    wet_exposed = int(proof.get("wet_runs") or 0) >= 1
    high_score = ability >= 66.0
    ordinary_track = track < 66.0
    speed_stability_only = (sectional >= 66.0 or stability >= 70.0) and track < 66.0 and race_shape < 66.0
    unstable = int(proof.get("wide_or_unstable") or 0) >= 1
    if high_score and wet_exposed and no_wet_place:
        flags.append("exposed_no_wet_place")
    if high_score and ordinary_track:
        flags.append("ordinary_track_high_score")
    if high_score and speed_stability_only:
        flags.append("speed_stability_only")
    if high_score and unstable:
        flags.append("unstable_profile")
    if barrier >= 13 and high_score:
        flags.append("wide_draw")
    return flags


def cap_delta(row: dict, variant: str) -> float:
    flags = set(risk_flags(row))
    if not flags:
        return 0.0
    if variant == "light_cap":
        if {"exposed_no_wet_place", "ordinary_track_high_score"} <= flags:
            return -0.8
        return 0.0
    if variant == "balanced_cap":
        delta = 0.0
        if "exposed_no_wet_place" in flags:
            delta -= 0.7
        if "ordinary_track_high_score" in flags:
            delta -= 0.4
        if "speed_stability_only" in flags:
            delta -= 0.5
        if "unstable_profile" in flags:
            delta -= 0.3
        return max(-1.4, delta)
    if variant == "strict_cap":
        delta = -0.5 * len(flags)
        return max(-2.0, delta)
    if variant == "top3_cap":
        if "exposed_no_wet_place" in flags and ("ordinary_track_high_score" in flags or "speed_stability_only" in flags):
            return -1.5
    return 0.0


def apply_variant(races: list[list[dict]], variant: str) -> list[list[dict]]:
    output = []
    for race in races:
        scored_race = []
        for row in race:
            item = dict(row)
            item["_score"] = as_float(row.get("ability_score"), 0.0)
            if is_soft_race(race):
                item["_score"] += cap_delta(row, variant)
            scored_race.append(item)
        output.append(scored_race)
    return output


def filter_soft(races: list[list[dict]]) -> list[list[dict]]:
    return [race for race in races if is_soft_race(race)]


def field_bucket(race: list[dict]) -> str:
    count = len(race)
    if count <= 8:
        return "Field <=8"
    if count <= 12:
        return "Field 9-12"
    return "Field 13+"


def venue_bucket(race: list[dict]) -> str:
    track = str(race[0].get("track") or "Unknown").strip()
    return track if track in {"Randwick", "Flemington"} else "Other"


def date_fold_bucket(race: list[dict]) -> str:
    date = str(race[0].get("date") or "")
    if date < "2026-03-01":
        return "early"
    if date < "2026-05-01":
        return "mid"
    return "late"


def bucket_delta_rows(base_races: list[list[dict]], candidate_races: list[list[dict]], bucket_fn) -> list[dict]:
    base_by_id = {(race[0]["meeting"], race[0]["race"]): race for race in base_races}
    candidate_by_id = {(race[0]["meeting"], race[0]["race"]): race for race in candidate_races}
    grouped_base: dict[str, list[list[dict]]] = defaultdict(list)
    grouped_candidate: dict[str, list[list[dict]]] = defaultdict(list)
    for race_id, base_race in base_by_id.items():
        candidate_race = candidate_by_id.get(race_id)
        if not candidate_race:
            continue
        bucket = bucket_fn(base_race)
        grouped_base[bucket].append(base_race)
        grouped_candidate[bucket].append(candidate_race)
    rows = []
    for bucket in sorted(grouped_base):
        base = metrics_for_races(grouped_base[bucket])
        candidate = metrics_for_races(grouped_candidate[bucket])
        rows.append(
            {
                "bucket": bucket,
                "base": base,
                "candidate": candidate,
                "top3_delta": candidate["top3_precision"] - base["top3_precision"],
                "winner_delta": candidate["winner_in_top3"] - base["winner_in_top3"],
                "miss_delta": candidate["miss"] - base["miss"],
                "pass_delta": candidate["pass"] - base["pass"],
            }
        )
    return rows


def bucket_gate(base_soft: dict, base_overall: dict, candidate: dict) -> tuple[str, list[str]]:
    soft = candidate["soft"]
    overall = candidate["overall"]
    rows = candidate.get("bucket_rows") or []
    reasons = []
    if soft["top3_precision"] <= base_soft["top3_precision"]:
        reasons.append("Soft Top3 precision did not improve")
    if soft["miss"] >= base_soft["miss"]:
        reasons.append("Soft Miss did not reduce")
    if overall["miss"] > base_overall["miss"]:
        reasons.append("Overall Miss increased")
    if soft["winner_in_top3"] < base_soft["winner_in_top3"]:
        reasons.append("Soft winner-in-top3 dropped")
    positive = sum(1 for row in rows if row["top3_delta"] >= 0 and row["miss_delta"] <= 0 and (row["top3_delta"] > 0 or row["miss_delta"] < 0))
    negative = sum(1 for row in rows if row["top3_delta"] < 0 or row["miss_delta"] > 0)
    if positive < 2:
        reasons.append("Fewer than two positive Soft buckets")
    if negative > 0:
        reasons.append("At least one Soft bucket worsened")
    return ("PASSED" if not reasons else "FAILED", reasons)


def risk_summary(races: list[list[dict]]) -> list[dict]:
    soft_rows = [row for race in filter_soft(races) for row in race]
    by_flag: dict[str, list[dict]] = defaultdict(list)
    for row in soft_rows:
        for flag in risk_flags(row):
            by_flag[flag].append(row)
    rows = []
    for flag, flagged in sorted(by_flag.items()):
        top3 = sum(1 for row in flagged if int(row.get("actual_pos") or 99) <= 3)
        rows.append(
            {
                "flag": flag,
                "runners": len(flagged),
                "top3": top3,
                "top3_rate": top3 / len(flagged) if flagged else 0.0,
            }
        )
    return sorted(rows, key=lambda row: row["runners"], reverse=True)


def delta(base: dict, candidate: dict) -> str:
    return (
        f"Gold {candidate['gold'] - base['gold']:+d}, Good {candidate['good'] - base['good']:+d}, "
        f"Pass {candidate['pass'] - base['pass']:+d}, Miss {candidate['miss'] - base['miss']:+d}, "
        f"Top3 {(candidate['top3_precision'] - base['top3_precision']) * 100:+.1f}pp, "
        f"W-in-T3 {(candidate['winner_in_top3'] - base['winner_in_top3']) * 100:+.1f}pp"
    )


def render_report(races: list[list[dict]], results: list[dict]) -> str:
    baseline = next(row for row in results if row["name"] == "baseline")
    ranked = sorted(
        [row for row in results if row["name"] != "baseline"],
        key=lambda row: (
            row["soft"]["top3_precision"] - baseline["soft"]["top3_precision"],
            -(row["soft"]["miss"] - baseline["soft"]["miss"]),
            row["soft"]["winner_in_top3"] - baseline["soft"]["winner_in_top3"],
        ),
        reverse=True,
    )
    passed = [
        row
        for row in ranked
        if row["soft"]["top3_precision"] > baseline["soft"]["top3_precision"]
        and row["soft"]["miss"] < baseline["soft"]["miss"]
        and row["overall"]["miss"] <= baseline["overall"]["miss"]
        and row["soft"]["winner_in_top3"] >= baseline["soft"]["winner_in_top3"]
    ]
    soft_rows = [row for race in filter_soft(races) for row in race]
    flagged = [row for row in soft_rows if risk_flags(row)]
    lines = [
        "# AU Soft Wet-Proof Cap Test",
        "",
        "## Dataset",
        "",
        f"- Soft validation races: **{len(filter_soft(races))}**",
        f"- Soft runners: **{len(soft_rows)}**",
        f"- Flagged runners: **{len(flagged)}** ({(len(flagged) / len(soft_rows) * 100 if soft_rows else 0):.1f}%)",
        f"- Cache: `{DATASET_CSV}`",
        "",
        "## Risk Flag Hit Rates",
        "",
        "| Flag | Runners | Actual Top3 | Top3 Rate |",
        "|---|---:|---:|---:|",
    ]
    for row in risk_summary(races):
        lines.append(f"| `{row['flag']}` | {row['runners']} | {row['top3']} | {row['top3_rate'] * 100:.1f}% |")
    lines.extend([
        "",
        "## Variant Results",
        "",
        "| Variant | Soft Result | Soft Delta | Overall Delta |",
        "|---|---|---|---|",
        f"| baseline | {fmt_metrics(baseline['soft'])} | - | - |",
    ])
    for row in ranked:
        lines.append(f"| `{row['name']}` | {fmt_metrics(row['soft'])} | {delta(baseline['soft'], row['soft'])} | {delta(baseline['overall'], row['overall'])} |")
    lines.extend([
        "",
        "## Gate",
        "",
        "PASSED" if passed else "FAILED",
        "",
    ])
    if passed:
        lines.append("- Candidate(s): " + ", ".join(f"`{row['name']}`" for row in passed))
    else:
        lines.append("- No wet-proof cap is clean enough to bake.")
    for row in results:
        if row["name"] in PROMOTION_CANDIDATES:
            lines.extend([
                "",
                f"## Bucket Gate: {row['name']}",
                "",
                f"- Gate: **{row.get('bucket_gate', 'N/A')}**",
            ])
            if row.get("bucket_reasons"):
                lines.append(f"- Reasons: {'; '.join(row['bucket_reasons'])}")
            lines.extend([
                "",
                "| Bucket | Base | Candidate | Delta |",
                "|---|---|---|---|",
            ])
            for bucket_row in row.get("bucket_rows", []):
                lines.append(
                    f"| {bucket_row['bucket']} | {fmt_metrics(bucket_row['base'])} | {fmt_metrics(bucket_row['candidate'])} | "
                    f"Top3 {bucket_row['top3_delta'] * 100:+.1f}pp / W-in-T3 {bucket_row['winner_delta'] * 100:+.1f}pp / "
                    f"Miss {bucket_row['miss_delta']:+d} / Pass {bucket_row['pass_delta']:+d} |"
                )
    lines.extend([
        "",
        "## Recommendation",
        "",
        "- Keep this as shadow only unless a cap reduces Miss without reducing Top3 precision across more archive/live Soft races.",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Soft wet-proof confidence caps.")
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT_MD)
    args = parser.parse_args()

    rows = materialize_dataset(rebuild=args.rebuild_cache)
    races = group_races(rows)
    folds = date_folds(races)
    validation_races = [race for _, valid in folds for race in valid]
    validation_races = attach_wet_proof(validation_races)
    baseline_scored = score_baseline(validation_races, "ability_score")
    baseline_soft = filter_soft(baseline_scored)
    results = [{"name": "baseline", "overall": metrics_for_races(baseline_scored), "soft": metrics_for_races(baseline_soft)}]
    for variant in ("light_cap", "balanced_cap", "strict_cap", "top3_cap"):
        scored = apply_variant(validation_races, variant)
        soft_scored = filter_soft(scored)
        row = {
            "name": variant,
            "overall": metrics_for_races(scored),
            "soft": metrics_for_races(soft_scored),
            "bucket_rows": [],
            "bucket_gate": "N/A",
            "bucket_reasons": [],
        }
        if variant in PROMOTION_CANDIDATES:
            bucket_rows = []
            for label, fn in (("venue", venue_bucket), ("field", field_bucket), ("date", date_fold_bucket)):
                for bucket_row in bucket_delta_rows(baseline_soft, soft_scored, fn):
                    bucket_rows.append({**bucket_row, "bucket": f"{label}:{bucket_row['bucket']}"})
            row["bucket_rows"] = bucket_rows
            row["bucket_gate"], row["bucket_reasons"] = bucket_gate(
                metrics_for_races(baseline_soft),
                metrics_for_races(baseline_scored),
                row,
            )
        results.append(row)
    args.output.write_text(render_report(validation_races, results), encoding="utf-8")
    print(f"Report: {args.output}")
    for row in results:
        print(f"{row['name']}: {fmt_metrics(row['soft'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
