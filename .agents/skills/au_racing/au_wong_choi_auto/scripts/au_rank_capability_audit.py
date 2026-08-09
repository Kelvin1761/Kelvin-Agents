#!/usr/bin/env python3
"""Explain AU Top-1..5 performance and matrix ability errors by cohort."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))

from au_eval import default_scorer, load_races  # noqa: E402
from io_utils import write_json_atomic, write_text_atomic  # noqa: E402
from scoring import MATRIX_WEIGHTS  # noqa: E402


def ranked(race):
    return sorted(
        race["rows"],
        key=lambda row: (-default_scorer(row), int(row.get("horse_number") or 999)),
    )


def performance(races):
    usable = []
    slot = defaultdict(Counter)
    winner_rank = Counter()
    missing_top2_place_rank = Counter()
    totals = Counter()
    for race in races:
        order = ranked(race)
        actual_top3 = {index for index, row in enumerate(order)
                       if int(row["pos"]) <= 3}
        winners = {index for index, row in enumerate(order)
                   if int(row["pos"]) == 1}
        if len(actual_top3) < 3 or not winners:
            continue
        winner = min(winners)
        usable.append(race)
        winner_rank[winner + 1] += 1
        for index, row in enumerate(order[:5], 1):
            slot[index]["win"] += int(row["pos"]) == 1
            slot[index]["place"] += int(row["pos"]) <= 3
            slot[index]["races"] += 1
        top2_places = sum(index in actual_top3 for index in range(min(2, len(order))))
        totals["top1_win"] += 0 in winners
        totals["top1_place"] += 0 in actual_top3
        totals["winner_top2"] += bool(winners & {0, 1})
        totals["top2_both_place"] += top2_places == 2
        totals["winner_top3"] += bool(winners & {0, 1, 2})
        totals["winner_top4"] += bool(winners & {0, 1, 2, 3})
        totals["winner_top5"] += bool(winners & {0, 1, 2, 3, 4})
        totals["actual_top3_within_top3"] += actual_top3 <= {0, 1, 2}
        totals["actual_top3_within_top4"] += actual_top3 <= {0, 1, 2, 3}
        totals["actual_top3_within_top5"] += actual_top3 <= {0, 1, 2, 3, 4}
        totals["winner_rank3_or4"] += winner in {2, 3}
        totals["rank3_or4_place_when_top2_miss"] += (
            top2_places < 2 and bool(actual_top3 & {2, 3})
        )
        totals["top3_hits"] += len(actual_top3 & {0, 1, 2})
        totals["top4_hits"] += len(actual_top3 & {0, 1, 2, 3})
        totals["top5_hits"] += len(actual_top3 & {0, 1, 2, 3, 4})
        if top2_places < 2:
            for index in sorted(actual_top3):
                if 2 <= index < 5:
                    missing_top2_place_rank[index + 1] += 1

    n = len(usable)
    return {
        "races": n,
        "rates": {
            key: value / n if n else None
            for key, value in totals.items()
            if not key.endswith("_hits")
        },
        "mean_actual_top3_captured": {
            "top3": totals["top3_hits"] / n if n else None,
            "top4": totals["top4_hits"] / n if n else None,
            "top5": totals["top5_hits"] / n if n else None,
        },
        "model_slot_rates": {
            str(index): {
                "win": counts["win"] / counts["races"],
                "place": counts["place"] / counts["races"],
            }
            for index, counts in sorted(slot.items())
        },
        "winner_model_rank_counts": dict(sorted(winner_rank.items())),
        "rank3_to_5_actual_places_when_top2_not_both_place": dict(
            sorted(missing_top2_place_rank.items())
        ),
    }


def going_family(value):
    text = str(value or "").lower()
    if "heavy" in text:
        return "Heavy"
    if "soft" in text:
        return "Soft"
    if "synthetic" in text:
        return "Synthetic"
    if any(token in text for token in ("good", "firm")):
        return "Good/Firm"
    return "Unknown"


def distance_band(value):
    distance = int(value or 0)
    if distance <= 1200:
        return "<=1200m"
    if distance <= 1600:
        return "1300-1600m"
    return "1700m+"


def field_band(value):
    size = int(value or 0)
    if size <= 8:
        return "<=8"
    if size <= 12:
        return "9-12"
    return "13+"


def class_family(value):
    text = str(value or "").upper()
    if re.search(r"\b(G1|G2|G3|GROUP|LISTED|LR)\b", text):
        return "Stakes/Listed"
    if "MAIDEN" in text or "MDN" in text:
        return "Maiden"
    if "BM" in text or "BENCHMARK" in text:
        return "Benchmark"
    if "CLASS" in text or re.search(r"\bCL\s*\d", text):
        return "Class"
    return "Other"


def cohort_tables(races, min_races=20):
    slicers = {
        "going": lambda m: going_family(m.get("going")),
        "distance": lambda m: distance_band(m.get("distance")),
        "field_size": lambda m: field_band(m.get("field_size")),
        "class": lambda m: class_family(m.get("race_class")),
        "track": lambda m: str(m.get("track") or "Unknown"),
    }
    output = {}
    for label, slicer in slicers.items():
        groups = defaultdict(list)
        for race in races:
            groups[slicer(race.get("metadata") or {})].append(race)
        output[label] = {
            name: performance(members)
            for name, members in sorted(groups.items())
            if len(members) >= min_races or label != "track"
        }
    return output


def matrix_error_attribution(races):
    cases = {
        "winner_rank2_to5_minus_model_top1": defaultdict(list),
        "placed_rank3_to5_minus_false_top2": defaultdict(list),
        "placed_outside_top5_minus_false_top2": defaultdict(list),
    }
    counts = Counter()
    for race in races:
        order = ranked(race)
        winner = next((row for row in order if int(row["pos"]) == 1), None)
        if winner is not None:
            winner_index = order.index(winner)
            if 1 <= winner_index < 5:
                counts["winner_rank2_to5_minus_model_top1"] += 1
                for key in MATRIX_WEIGHTS:
                    cases["winner_rank2_to5_minus_model_top1"][key].append(
                        float(winner["matrix_scores"][key])
                        - float(order[0]["matrix_scores"][key])
                    )

        false_top2 = [row for row in order[:2] if int(row["pos"]) > 3]
        if not false_top2:
            continue
        false_means = {
            key: mean(float(row["matrix_scores"][key]) for row in false_top2)
            for key in MATRIX_WEIGHTS
        }
        for case, candidates in (
            ("placed_rank3_to5_minus_false_top2", order[2:5]),
            ("placed_outside_top5_minus_false_top2", order[5:]),
        ):
            placed = [row for row in candidates if int(row["pos"]) <= 3]
            if not placed:
                continue
            counts[case] += 1
            for key in MATRIX_WEIGHTS:
                cases[case][key].append(
                    mean(float(row["matrix_scores"][key]) for row in placed)
                    - false_means[key]
                )
    return {
        case: {
            "races": counts[case],
            "mean_matrix_delta": {
                key: mean(values) for key, values in dimensions.items() if values
            },
        }
        for case, dimensions in cases.items()
    }


def render_markdown(report):
    overall = report["overall"]
    rates = overall["rates"]
    slots = overall["model_slot_rates"]
    lines = [
        "# AU Rank / Ability Capability Audit",
        "",
        f"- Aligned races: {overall['races']}",
        f"- Top-1 win / place: {rates['top1_win']*100:.2f}% / "
        f"{rates['top1_place']*100:.2f}%",
        f"- Winner inside Top-2 / Top-3 / Top-5: "
        f"{rates['winner_top2']*100:.2f}% / {rates['winner_top3']*100:.2f}% / "
        f"{rates['winner_top5']*100:.2f}%",
        f"- Winner inside Top-4: {rates['winner_top4']*100:.2f}%",
        f"- Top-2 individual place rate: "
        f"{(slots['1']['place'] + slots['2']['place']) * 50:.2f}% "
        f"(Rank 1 {slots['1']['place']*100:.2f}% / Rank 2 {slots['2']['place']*100:.2f}%)",
        f"- Good (Top-2 both place): {rates['top2_both_place']*100:.2f}%",
        f"- Actual Top-3 fully inside model Top-3 / Top-4 / Top-5: "
        f"{rates['actual_top3_within_top3']*100:.2f}% / "
        f"{rates['actual_top3_within_top4']*100:.2f}% / "
        f"{rates['actual_top3_within_top5']*100:.2f}%",
        f"- Gold (all actual Top-3 inside model Top-4): "
        f"{rates['actual_top3_within_top4']*100:.2f}%",
        f"- Winner ranked #3/#4: {rates['winner_rank3_or4']*100:.2f}%",
        f"- Rank #3/#4 actual placer while Top-2 not both place: "
        f"{rates['rank3_or4_place_when_top2_miss']*100:.2f}%",
        f"- Mean actual Top-3 captured by model Top-3 / Top-4 / Top-5: "
        f"{overall['mean_actual_top3_captured']['top3']:.2f} / "
        f"{overall['mean_actual_top3_captured']['top4']:.2f} / "
        f"{overall['mean_actual_top3_captured']['top5']:.2f}",
        "",
        "## Model rank slot quality",
        "",
        "| Model rank | Win | Place |",
        "|---:|---:|---:|",
    ]
    for rank, row in slots.items():
        lines.append(f"| {rank} | {row['win']*100:.2f}% | {row['place']*100:.2f}% |")
    lines.extend([
        "",
        "## Matrix error attribution",
        "",
        "Positive means the missed true horse already scored higher on that "
        "dimension; negative means the matrix undervalued it there.",
        "",
    ])
    for case, row in report["matrix_error_attribution"].items():
        dims = " · ".join(
            f"{key} {value:+.2f}" for key, value in row["mean_matrix_delta"].items()
        )
        lines.append(f"- {case} (n={row['races']}): {dims}")
    lines.extend(["", "## Cohorts", ""])
    for slice_name, cohorts in report["cohorts"].items():
        lines.extend([
            f"### {slice_name}",
            "",
            "| Cohort | Races | Top1 win | Good | Gold | Winner@3 | Winner@5 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ])
        for name, row in cohorts.items():
            r = row["rates"]
            lines.append(
                f"| {name} | {row['races']} | {r['top1_win']*100:.1f}% | "
                f"{r['top2_both_place']*100:.1f}% | "
                f"{r['actual_top3_within_top4']*100:.1f}% | "
                f"{r['winner_top3']*100:.1f}% | {r['winner_top5']*100:.1f}% |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-json", type=Path, required=True)
    parser.add_argument("--min-track-races", type=int, default=20)
    parser.add_argument(
        "--output-json", type=Path,
        default=Path("/private/tmp/au_rank_capability_audit.json"),
    )
    parser.add_argument(
        "--output-md", type=Path,
        default=Path("/private/tmp/au_rank_capability_audit.md"),
    )
    args = parser.parse_args()
    races = load_races(args.dataset_json)
    report = {
        "design": {
            "dataset": str(args.dataset_json),
            "outcome_fields_are_evaluation_only": ["pos", "result_sp_label"],
        },
        "overall": performance(races),
        "cohorts": cohort_tables(races, args.min_track_races),
        "matrix_error_attribution": matrix_error_attribution(races),
    }
    write_json_atomic(args.output_json, report)
    write_text_atomic(args.output_md, render_markdown(report))
    print(render_markdown(report))
    print(f"JSON: {args.output_json}\nMarkdown: {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
