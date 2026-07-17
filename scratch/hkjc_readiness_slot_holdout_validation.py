#!/usr/bin/env python3
"""Step 6 holdout validation for the frozen HKJC readiness-slot candidate."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from hkjc_rebuilt_matrix_candidates import (
    baseline_selections,
    compare_candidate,
    development_races,
    selection_metrics,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE = ROOT / "scratch" / "hkjc_uncertainty_slot_candidates.csv"
DEFAULT_REPLAY = ROOT / "scratch" / "hkjc_prerace_replay.csv"
DEFAULT_OUTPUT = ROOT / "scratch" / "hkjc_readiness_slot_holdout_validation"
CANDIDATE_NAME = "readiness_slot_only"
RANK_COLUMN = f"rank_{CANDIDATE_NAME}"
SCORE_COLUMN = f"score_{CANDIDATE_NAME}"
VALIDATION_SPLITS = (
    "archive_temporal_holdout",
    "independent_recent",
    "external_2026_07_15",
)
EXPECTED_RACES = {
    "archive_development": 88,
    "archive_temporal_holdout": 39,
    "independent_recent": 109,
    "external_2026_07_15": 9,
}


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_frozen_candidate(
    path: Path,
) -> tuple[
    dict[tuple[str, str, int], list[int]],
    dict[tuple[str, str, int], dict[int, dict[str, Any]]],
    list[str],
]:
    grouped: defaultdict[tuple[str, str, int], dict[int, dict[str, Any]]] = defaultdict(dict)
    errors = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            race = (row["dataset"], row["meeting"], as_int(row["race_number"]))
            number = as_int(row["horse_number"])
            grouped[race][number] = {
                "rank": as_int(row[RANK_COLUMN]),
                "score": as_float(row[SCORE_COLUMN]),
                "is_debut": bool(as_int(row["is_debut"])),
                "horse_name": row.get("horse_name", ""),
            }
    selections = {}
    for race, horses in grouped.items():
        ranks = sorted(item["rank"] for item in horses.values())
        if ranks != list(range(1, len(horses) + 1)):
            errors.append(f"invalid rank permutation: {race}")
        selections[race] = [
            number for number, item in sorted(horses.items(), key=lambda pair: pair[1]["rank"])[:2]
        ]
    return selections, dict(grouped), errors


def load_reference(path: Path) -> dict[tuple[str, str, int, int], dict[str, Any]]:
    reference = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            item = (
                row["dataset"],
                row["meeting"],
                as_int(row["race_number"]),
                as_int(row["horse_number"]),
            )
            reference[item] = {
                "split": row["split"],
                "finish": as_int(row["label_finish_position"]),
                "is_top3": bool(as_int(row["label_is_top3"])),
                "is_winner": bool(as_int(row["label_is_winner"])),
                "original_rank": as_int(row["reference_original_rank"]),
            }
    return reference


def split_races(
    reference: dict[tuple[str, str, int, int], dict[str, Any]],
) -> dict[str, dict[tuple[str, str, int], dict[int, dict[str, Any]]]]:
    grouped: defaultdict[str, dict[tuple[str, str, int], dict[int, dict[str, Any]]]] = defaultdict(dict)
    all_races = development_races(reference)
    for race, horses in all_races.items():
        split = next(iter(horses.values()))["split"]
        grouped[split][race] = horses
    return dict(grouped)


def compact(metric: dict[str, Any]) -> dict[str, Any]:
    return {name: value for name, value in metric.items() if name != "per_race"}


def evaluate_split(
    races: dict[tuple[str, str, int], dict[int, dict[str, Any]]],
    frozen_selections: dict[tuple[str, str, int], list[int]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    baseline = selection_metrics(baseline_selections(races), races)
    candidate_selections = {race: frozen_selections[race] for race in races}
    candidate = selection_metrics(candidate_selections, races)
    comparison = compare_candidate(baseline, candidate, races)
    return baseline, candidate, comparison


def combined_races(
    split_map: dict[str, dict[tuple[str, str, int], dict[int, dict[str, Any]]]],
    splits: tuple[str, ...],
) -> dict[tuple[str, str, int], dict[int, dict[str, Any]]]:
    output = {}
    for split in splits:
        output.update(split_map[split])
    return output


def boundary_ties(
    races: dict[tuple[str, str, int], dict[int, dict[str, Any]]],
    frozen_rows: dict[tuple[str, str, int], dict[int, dict[str, Any]]],
) -> dict[str, Any]:
    ties = 0
    for race in races:
        ranked = sorted(frozen_rows[race].values(), key=lambda item: item["rank"])
        ties += int(abs(ranked[1]["score"] - ranked[2]["score"]) < 1e-9)
    return {
        "races": len(races),
        "boundary_ties": ties,
        "boundary_tie_rate": round(ties / len(races) * 100.0, 1),
    }


def non_harm_gate(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    zero_delta = candidate["distribution"]["0"] - baseline["distribution"]["0"]
    hit_delta = candidate["total_top2_hits"] - baseline["total_top2_hits"]
    winner_delta = candidate["winner_top2"] - baseline["winner_top2"]
    return {
        "passes": zero_delta <= 0 and hit_delta >= 0 and winner_delta >= 0,
        "zero_hit_delta": zero_delta,
        "top2_hit_delta": hit_delta,
        "winner_top2_delta": winner_delta,
    }


def meeting_profile(
    races: dict[tuple[str, str, int], dict[int, dict[str, Any]]],
    frozen_selections: dict[tuple[str, str, int], list[int]],
) -> list[dict[str, Any]]:
    by_meeting: defaultdict[str, dict[tuple[str, str, int], dict[int, dict[str, Any]]]] = defaultdict(dict)
    for race, horses in races.items():
        by_meeting[race[1]][race] = horses
    rows = []
    for meeting, meeting_races in sorted(by_meeting.items()):
        baseline, candidate, comparison = evaluate_split(meeting_races, frozen_selections)
        gate = non_harm_gate(baseline, candidate)
        rows.append(
            {
                "meeting": meeting,
                "races": len(meeting_races),
                "baseline_zero": baseline["distribution"]["0"],
                "candidate_zero": candidate["distribution"]["0"],
                "zero_delta": gate["zero_hit_delta"],
                "hit_delta": gate["top2_hit_delta"],
                "winner_delta": gate["winner_top2_delta"],
                "top2_changes": comparison["top2_set_changes"],
                "rank3_rescue_net": comparison["rank3_rescue_net"],
                "non_harm": gate["passes"],
            }
        )
    return rows


def build_race_rows(
    split_map: dict[str, dict[tuple[str, str, int], dict[int, dict[str, Any]]]],
    frozen_selections: dict[tuple[str, str, int], list[int]],
    frozen_rows: dict[tuple[str, str, int], dict[int, dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows = []
    for split in VALIDATION_SPLITS:
        races = split_map[split]
        baseline_picks = baseline_selections(races)
        for race, horses in sorted(races.items()):
            baseline = baseline_picks[race]
            candidate = frozen_selections[race]
            baseline_hits = sum(horses[number]["is_top3"] for number in baseline)
            candidate_hits = sum(horses[number]["is_top3"] for number in candidate)
            baseline_winner = int(any(horses[number]["is_winner"] for number in baseline))
            candidate_winner = int(any(horses[number]["is_winner"] for number in candidate))
            rank3 = next(number for number, label in horses.items() if label["original_rank"] == 3)
            promoted = rank3 in set(candidate) - set(baseline)
            excluded = set(baseline) - set(candidate)
            effective = int(promoted and horses[rank3]["is_top3"] and any(not horses[n]["is_top3"] for n in excluded))
            harmful = int(promoted and not horses[rank3]["is_top3"] and any(horses[n]["is_top3"] for n in excluded))
            rows.append(
                {
                    "split": split,
                    "meeting": race[1],
                    "race_number": race[2],
                    "baseline_picks": "/".join(str(number) for number in baseline),
                    "baseline_pick_names": "/".join(frozen_rows[race][number]["horse_name"] for number in baseline),
                    "candidate_picks": "/".join(str(number) for number in candidate),
                    "candidate_pick_names": "/".join(frozen_rows[race][number]["horse_name"] for number in candidate),
                    "top2_changed": int(set(baseline) != set(candidate)),
                    "baseline_hits": baseline_hits,
                    "candidate_hits": candidate_hits,
                    "hit_delta": candidate_hits - baseline_hits,
                    "baseline_winner": baseline_winner,
                    "candidate_winner": candidate_winner,
                    "winner_delta": candidate_winner - baseline_winner,
                    "zero_to_positive": int(baseline_hits == 0 and candidate_hits > 0),
                    "one_to_two": int(baseline_hits == 1 and candidate_hits == 2),
                    "one_to_zero": int(baseline_hits == 1 and candidate_hits == 0),
                    "original_rank3": rank3,
                    "rank3_is_top3": int(horses[rank3]["is_top3"]),
                    "rank3_promoted": int(promoted),
                    "effective_rank3_rescue": effective,
                    "harmful_rank3_promotion": harmful,
                }
            )
    return rows


def validate(
    reference: dict[tuple[str, str, int, int], dict[str, Any]],
    split_map: dict[str, dict[tuple[str, str, int], dict[int, dict[str, Any]]]],
    frozen_selections: dict[tuple[str, str, int], list[int]],
    frozen_errors: list[str],
) -> list[str]:
    errors = list(frozen_errors)
    if len(reference) != 3054:
        errors.append(f"reference rows {len(reference)} != 3054")
    for split, expected in EXPECTED_RACES.items():
        actual = len(split_map.get(split, {}))
        if actual != expected:
            errors.append(f"{split} races {actual} != {expected}")
    missing = sorted(race for split in split_map.values() for race in split if race not in frozen_selections)
    if missing:
        errors.append(f"missing frozen selections: {len(missing)}")
    for split, races in split_map.items():
        for race, horses in races.items():
            if len([label for label in horses.values() if label["is_top3"]]) != 3:
                errors.append(f"top3 label count: {race}")
            ranks = sorted(label["original_rank"] for label in horses.values())
            if ranks[:3] != [1, 2, 3]:
                errors.append(f"original rank coverage: {race}")
    return sorted(set(errors))


def write_outputs(
    output_prefix: Path,
    candidate_path: Path,
    split_results: dict[str, dict[str, Any]],
    combined_result: dict[str, Any],
    profiles: dict[str, list[dict[str, Any]]],
    venue_results: dict[str, dict[str, Any]],
    race_rows: list[dict[str, Any]],
    final_gate: dict[str, Any],
    errors: list[str],
) -> dict[str, str]:
    race_path = output_prefix.with_name(output_prefix.name + "_races").with_suffix(".csv")
    json_path = output_prefix.with_suffix(".json")
    report_path = output_prefix.with_name(output_prefix.name + "_report").with_suffix(".md")
    with race_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(race_rows[0]))
        writer.writeheader()
        writer.writerows(race_rows)
    payload = {
        "method": {
            "candidate": CANDIDATE_NAME,
            "frozen_candidate_file": str(candidate_path),
            "frozen_candidate_sha256": file_sha256(candidate_path),
            "formula_changes_after_development": False,
            "validation_splits": list(VALIDATION_SPLITS),
            "formal_auto_changed": False,
        },
        "split_results": split_results,
        "combined_validation": combined_result,
        "meeting_profiles": profiles,
        "venue_results": venue_results,
        "final_gate": final_gate,
        "validation_errors": errors,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    labels = {
        "archive_development": "Development（舊基準）",
        "archive_temporal_holdout": "Temporal holdout",
        "independent_recent": "近期獨立",
        "external_2026_07_15": "07-15 Happy Valley",
    }
    lines = [
        "# HKJC Readiness Health-Slot — Step 6跨時段驗證",
        "",
        "## 方法鎖定",
        "",
        f"- 只驗證Step 5d已凍結候選 `{CANDIDATE_NAME}`；候選CSV SHA-256：`{file_sha256(candidate_path)}`。",
        "- 全245場候選排名早於本步結果載入已凍結；無改公式、weights、threshold或排序規則。",
        "- Temporal、近期及07-15分開過non-harm gate；合併結果不能遮蓋任何一段轉差。",
        "- 正式Auto保持不變。",
        "",
        "## 分段結果",
        "",
        "| 樣本 | 場數 | 原0/1/2 | 候選0/1/2 | Δhits | Δ頭馬 | Δ0 | 0→正數 | 1→2 | 1→0 | 第三選有效/有害/淨值 | Top2變動 | Non-harm |",
        "|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for split in ("archive_development", *VALIDATION_SPLITS):
        result = split_results[split]
        baseline = result["baseline"]
        candidate = result["candidate"]
        comparison = result["comparison"]
        gate = result["gate"]
        base_dist = baseline["distribution"]
        cand_dist = candidate["distribution"]
        lines.append(
            f"| {labels[split]} | {baseline['races']} | {base_dist['0']}/{base_dist['1']}/{base_dist['2']} | "
            f"{cand_dist['0']}/{cand_dist['1']}/{cand_dist['2']} | {gate['top2_hit_delta']:+d} | "
            f"{gate['winner_top2_delta']:+d} | {gate['zero_hit_delta']:+d} | {comparison['zero_to_positive']} | "
            f"{comparison['one_to_two']} | {comparison['one_to_zero']} | "
            f"{comparison['effective_rank3_rescues']}/{comparison['harmful_rank3_promotions']}/{comparison['rank3_rescue_net']:+d} | "
            f"{comparison['top2_set_changes']} | {'是' if gate['passes'] else '否'} |"
        )
    combined = combined_result
    base_dist = combined["baseline"]["distribution"]
    cand_dist = combined["candidate"]["distribution"]
    comparison = combined["comparison"]
    gate = combined["gate"]
    lines.extend(
        [
            f"| **合併驗證** | {combined['baseline']['races']} | {base_dist['0']}/{base_dist['1']}/{base_dist['2']} | "
            f"{cand_dist['0']}/{cand_dist['1']}/{cand_dist['2']} | {gate['top2_hit_delta']:+d} | "
            f"{gate['winner_top2_delta']:+d} | {gate['zero_hit_delta']:+d} | {comparison['zero_to_positive']} | "
            f"{comparison['one_to_two']} | {comparison['one_to_zero']} | "
            f"{comparison['effective_rank3_rescues']}/{comparison['harmful_rank3_promotions']}/{comparison['rank3_rescue_net']:+d} | "
            f"{comparison['top2_set_changes']} | {'是' if gate['passes'] else '否'} |",
            "",
            "## 逐賽日方向",
            "",
            "| 樣本 | 賽日 | 場數 | Δhits | Δ頭馬 | Δ0 | Top2變動 | 第三選淨救援 | Non-harm |",
            "|---|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for split in VALIDATION_SPLITS:
        for profile in profiles[split]:
            lines.append(
                f"| {labels[split]} | {profile['meeting']} | {profile['races']} | {profile['hit_delta']:+d} | "
                f"{profile['winner_delta']:+d} | {profile['zero_delta']:+d} | {profile['top2_changes']} | "
                f"{profile['rank3_rescue_net']:+d} | {'是' if profile['non_harm'] else '否'} |"
            )
    lines.extend(
        [
            "",
            "## 場地分拆（合併驗證）",
            "",
            "| 場地 | 場數 | Δhits | Δ頭馬 | Δ0 | 第三選有效/有害/淨值 | Top2變動 | Non-harm |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for venue in ("HappyValley", "ShaTin"):
        result = venue_results[venue]
        gate = result["gate"]
        comparison = result["comparison"]
        lines.append(
            f"| {'跑馬地' if venue == 'HappyValley' else '沙田'} | {result['baseline']['races']} | "
            f"{gate['top2_hit_delta']:+d} | {gate['winner_top2_delta']:+d} | {gate['zero_hit_delta']:+d} | "
            f"{comparison['effective_rank3_rescues']}/{comparison['harmful_rank3_promotions']}/{comparison['rank3_rescue_net']:+d} | "
            f"{comparison['top2_set_changes']} | {'是' if gate['passes'] else '否'} |"
        )
    july_changes = [row for row in race_rows if row["split"] == "external_2026_07_15" and row["top2_changed"]]
    lines.extend(
        [
            "",
            "## 07-15變動場次",
            "",
            "| 場次 | 原Top2 | 候選Top2 | Δhits | Δ頭馬 | 第三選升格 | 有效／有害 |",
            "|---:|---|---|---:|---:|---:|---|",
        ]
    )
    if july_changes:
        for row in july_changes:
            lines.append(
                f"| {row['race_number']} | {row['baseline_picks']} {row['baseline_pick_names']} | "
                f"{row['candidate_picks']} {row['candidate_pick_names']} | "
                f"{row['hit_delta']:+d} | {row['winner_delta']:+d} | {row['rank3_promoted']} | "
                f"{row['effective_rank3_rescue']}/{row['harmful_rank3_promotion']} |"
            )
    else:
        lines.append("| — | — | — | 0 | 0 | 0 | 0/0 |")
    lines.extend(
        [
            "",
            "## Step 6決策",
            "",
            f"- 各驗證段non-harm一致：{'是' if final_gate['all_segments_non_harm'] else '否'}。",
            f"- 合併驗證signal：{final_gate['combined_signal_path']}。",
            f"- 結論：{final_gate['decision']}。",
            f"- Validation errors：{len(errors)}；正式Auto保持不變。",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"races": str(race_path), "json": str(json_path), "report": str(report_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--replay", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--output-prefix", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    frozen_selections, frozen_rows, frozen_errors = load_frozen_candidate(args.candidate)
    reference = load_reference(args.replay)
    split_map = split_races(reference)
    errors = validate(reference, split_map, frozen_selections, frozen_errors)

    split_results = {}
    for split in ("archive_development", *VALIDATION_SPLITS):
        baseline, candidate, comparison = evaluate_split(split_map[split], frozen_selections)
        split_results[split] = {
            "baseline": compact(baseline),
            "candidate": compact(candidate),
            "comparison": comparison,
            "gate": non_harm_gate(baseline, candidate),
            "tie_stats": boundary_ties(split_map[split], frozen_rows),
        }
    validation_races = combined_races(split_map, VALIDATION_SPLITS)
    baseline, candidate, comparison = evaluate_split(validation_races, frozen_selections)
    combined_gate = non_harm_gate(baseline, candidate)
    combined_result = {
        "baseline": compact(baseline),
        "candidate": compact(candidate),
        "comparison": comparison,
        "gate": combined_gate,
        "tie_stats": boundary_ties(validation_races, frozen_rows),
    }
    segment_gates = {split: split_results[split]["gate"] for split in VALIDATION_SPLITS}
    all_segments_non_harm = all(gate["passes"] for gate in segment_gates.values())
    common = (
        combined_gate["passes"]
        and comparison["top2_set_changes"] >= 5
        and combined_result["tie_stats"]["boundary_tie_rate"] <= 5.0
    )
    primary = common and combined_gate["zero_hit_delta"] < 0
    secondary = common and combined_gate["zero_hit_delta"] == 0 and comparison["rank3_rescue_net"] > 0
    signal_path = "LOWER_ZERO_HIT" if primary else ("RANK3_RESCUE" if secondary else "FAIL")
    advances = all_segments_non_harm and (primary or secondary) and not errors
    final_gate = {
        "all_segments_non_harm": all_segments_non_harm,
        "segment_gates": segment_gates,
        "combined_common": common,
        "combined_signal_path": signal_path,
        "advances_to_auto_shadow": advances,
        "decision": "ADVANCE_TO_AUTO_SHADOW" if advances else "REJECT_OR_HOLD",
    }
    profiles = {split: meeting_profile(split_map[split], frozen_selections) for split in VALIDATION_SPLITS}
    venue_results = {}
    for venue in ("HappyValley", "ShaTin"):
        venue_races = {
            race: horses
            for race, horses in validation_races.items()
            if venue in race[1]
        }
        venue_baseline, venue_candidate, venue_comparison = evaluate_split(venue_races, frozen_selections)
        venue_results[venue] = {
            "baseline": compact(venue_baseline),
            "candidate": compact(venue_candidate),
            "comparison": venue_comparison,
            "gate": non_harm_gate(venue_baseline, venue_candidate),
        }
    race_rows = build_race_rows(split_map, frozen_selections, frozen_rows)
    outputs = write_outputs(
        args.output_prefix,
        args.candidate,
        split_results,
        combined_result,
        profiles,
        venue_results,
        race_rows,
        final_gate,
        errors,
    )
    print(json.dumps({**outputs, "final_gate": final_gate, "validation_errors": errors}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
