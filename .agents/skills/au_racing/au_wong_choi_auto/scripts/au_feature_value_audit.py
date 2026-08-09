#!/usr/bin/env python3
"""Measure AU feature value, neutrality, stability and duplication by time fold."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, pstdev

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))

from io_utils import write_json_atomic, write_text_atomic
from scoring import ABILITY_FEATURE_KEYS, FEATURE_KEYS, REPORT_ONLY_FEATURE_KEYS


def going_family(value: str) -> str:
    text = str(value or "").lower()
    if "heavy" in text:
        return "Heavy"
    if "soft" in text:
        return "Soft"
    if "synthetic" in text:
        return "Synthetic"
    if "good" in text or "firm" in text:
        return "Good/Firm"
    return "Unknown"


def class_family(value: str) -> str:
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


def cohort_key(metadata: dict, slice_name: str) -> str:
    if slice_name == "going":
        return going_family(metadata.get("going"))
    if slice_name == "distance":
        distance = int(metadata.get("distance") or 0)
        return "<=1200m" if distance <= 1200 else ("1300-1600m" if distance <= 1600 else "1700m+")
    if slice_name == "field_size":
        size = int(metadata.get("field_size") or 0)
        return "<=8" if size <= 8 else ("9-12" if size <= 12 else "13+")
    if slice_name == "class":
        return class_family(metadata.get("race_class"))
    return str(metadata.get("track") or "Unknown")


def within_race_auc(
    races: list[dict],
    key: str,
    container: str = "feature_scores",
) -> float | None:
    wins = comparisons = 0.0
    for race in races:
        positive = [
            float(row[container].get(key, 60.0))
            for row in race["rows"]
            if int(row["actual_pos"]) <= 3
        ]
        negative = [
            float(row[container].get(key, 60.0))
            for row in race["rows"]
            if int(row["actual_pos"]) > 3
        ]
        for pos in positive:
            for neg in negative:
                comparisons += 1
                wins += 1 if pos > neg else (0.5 if pos == neg else 0.0)
    return wins / comparisons if comparisons else None


def date_folds(races: list[dict], count: int = 5) -> tuple[list[list[dict]], list[dict]]:
    dates = sorted({race["metadata"]["date"] for race in races})
    holdout_count = max(1, math.ceil(len(dates) * 0.15))
    holdout_dates = set(dates[-holdout_count:])
    dev_dates = dates[:-holdout_count]
    size = max(1, math.ceil(len(dev_dates) / count))
    folds = []
    for index in range(0, len(dev_dates), size):
        bucket = set(dev_dates[index : index + size])
        folds.append(
            [race for race in races if race["metadata"]["date"] in bucket]
        )
    holdout = [
        race for race in races if race["metadata"]["date"] in holdout_dates
    ]
    return folds, holdout


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    x_mean = mean(xs)
    y_mean = mean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    denominator = math.sqrt(
        sum((x - x_mean) ** 2 for x in xs)
        * sum((y - y_mean) ** 2 for y in ys)
    )
    return numerator / denominator if denominator else None


def build_audit(dataset: dict) -> dict:
    races = dataset["races"]
    folds, holdout = date_folds(races)
    rows = [row for race in races for row in race["rows"]]
    def signal_rows(keys, container):
        output = {}
        for key in keys:
            values = [float(row[container].get(key, 60.0)) for row in rows]
            positives = [
                float(row[container].get(key, 60.0))
                for row in rows
                if int(row["actual_pos"]) <= 3
            ]
            negatives = [
                float(row[container].get(key, 60.0))
                for row in rows
                if int(row["actual_pos"]) > 3
            ]
            fold_auc = [
                within_race_auc(fold, key, container) for fold in folds
            ]
            output[key] = {
                "within_race_auc_all": within_race_auc(
                    races,
                    key,
                    container,
                ),
                "within_race_auc_folds": fold_auc,
                "within_race_auc_terminal": within_race_auc(
                    holdout,
                    key,
                    container,
                ),
                "mean_actual_top3": mean(positives),
                "mean_non_top3": mean(negatives),
                "mean_gap": mean(positives) - mean(negatives),
                "mean": mean(values),
                "median": median(values),
                "stddev": pstdev(values),
                "min": min(values),
                "max": max(values),
                "exact_60_rate": sum(abs(value - 60.0) < 1e-9 for value in values)
                / len(values),
                "band_58_62_rate": sum(58.0 <= value <= 62.0 for value in values)
                / len(values),
                "neutral_rate_abs_lt_0_5": sum(
                    abs(value - 60.0) < 0.5 for value in values
                )
                / len(values),
                "weak_rate_abs_lt_2": sum(
                    abs(value - 60.0) < 2.0 for value in values
                )
                / len(values),
                "stable_positive_folds": sum(
                    auc is not None and auc >= 0.5 for auc in fold_auc
                ),
            }
        return output

    features = signal_rows(FEATURE_KEYS, "feature_scores")
    for key in FEATURE_KEYS:
        values = [float(row["feature_scores"].get(key, 60.0)) for row in rows]
        evidence = [
            row["feature_evidence_state"].get(key, "unknown")
            for row in rows
        ]
        features[key]["missing_or_fallback_rate"] = sum(
                state in {"missing", "fallback"} for state in evidence
            )
        features[key]["missing_or_fallback_rate"] /= len(evidence)
        features[key]["role"] = (
            "ranking" if key in ABILITY_FEATURE_KEYS else "report_only"
        )
        full_auc = features[key]["within_race_auc_all"]
        terminal_auc = features[key]["within_race_auc_terminal"]
        if full_auc is not None and terminal_auc is not None and full_auc < 0.5 and terminal_auc < 0.5:
            features[key]["status"] = (
                "inverse_active" if key in ABILITY_FEATURE_KEYS else "inverse_report_only"
            )
        elif full_auc is not None and full_auc < 0.52:
            features[key]["status"] = "weak"
        else:
            features[key]["status"] = "healthy"

    correlations = []
    for index, left in enumerate(FEATURE_KEYS):
        left_values = [
            float(row["feature_scores"].get(left, 60.0)) for row in rows
        ]
        for right in FEATURE_KEYS[index + 1 :]:
            right_values = [
                float(row["feature_scores"].get(right, 60.0)) for row in rows
            ]
            value = pearson(left_values, right_values)
            if value is not None and abs(value) >= 0.55:
                correlations.append(
                    {
                        "left": left,
                        "right": right,
                        "correlation": value,
                    }
                )
    correlations.sort(key=lambda row: abs(row["correlation"]), reverse=True)
    matrices = signal_rows(tuple(rows[0]["matrix_scores"]), "matrix_scores")
    cohort_auc = {}
    for slice_name in ("going", "distance", "field_size", "class", "track"):
        groups = defaultdict(list)
        for race in races:
            groups[cohort_key(race["metadata"], slice_name)].append(race)
        cohort_auc[slice_name] = {}
        for label, members in sorted(groups.items()):
            if len(members) < 20:
                continue
            cohort_auc[slice_name][label] = {
                "races": len(members),
                "features": {
                    key: within_race_auc(members, key, "feature_scores")
                    for key in FEATURE_KEYS
                },
                "matrices": {
                    key: within_race_auc(members, key, "matrix_scores")
                    for key in rows[0]["matrix_scores"]
                },
            }
    return {
        "design": dataset["design"],
        "fold_races": [len(fold) for fold in folds],
        "terminal_races": len(holdout),
        "features": features,
        "matrices": matrices,
        "cohort_auc": cohort_auc,
        "high_correlations_abs_ge_0_55": correlations,
    }


def render_markdown(audit: dict) -> str:
    lines = [
        "# AU Feature Value Audit",
        "",
        f"- Races / horses: {audit['design']['aligned_races']} / {audit['design']['horses']}",
        f"- Development time folds: {audit['fold_races']}",
        f"- Terminal holdout: {audit['terminal_races']} races",
        "",
        "| Feature | Role/status | Mean/median | SD | Range | =60 | 58-62 | Missing/fallback | AUC all/terminal |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    ordered = sorted(
        audit["features"].items(),
        key=lambda item: item[1]["within_race_auc_all"] or 0,
        reverse=True,
    )
    for key, row in ordered:
        lines.append(
            f"| {key} | {row['role']} / {row['status']} | "
            f"{row['mean']:.1f}/{row['median']:.1f} | {row['stddev']:.1f} | "
            f"{row['min']:.1f}-{row['max']:.1f} | "
            f"{row['exact_60_rate'] * 100:.1f}% | "
            f"{row['band_58_62_rate'] * 100:.1f}% | "
            f"{row['missing_or_fallback_rate'] * 100:.1f}% | "
            f"{row['within_race_auc_all']:.3f}/{row['within_race_auc_terminal']:.3f} |"
        )
    lines.extend(["", "## Strong correlations", ""])
    for row in audit["high_correlations_abs_ge_0_55"]:
        lines.append(
            f"- {row['left']} × {row['right']}: {row['correlation']:+.3f}"
        )
    lines.extend(
        [
            "",
            "## Matrix value",
            "",
            "| Matrix | AUC all | AUC folds | AUC terminal | Top3 gap |",
            "|---|---:|---|---:|---:|",
        ]
    )
    ordered_matrices = sorted(
        audit["matrices"].items(),
        key=lambda item: item[1]["within_race_auc_all"] or 0,
        reverse=True,
    )
    for key, row in ordered_matrices:
        folds = "/".join(
            "n/a" if value is None else f"{value:.3f}"
            for value in row["within_race_auc_folds"]
        )
        lines.append(
            f"| {key} | {row['within_race_auc_all']:.3f} | {folds} | "
            f"{row['within_race_auc_terminal']:.3f} | {row['mean_gap']:+.2f} |"
        )
    lines.extend(["", "## Matrix AUC by cohort", ""])
    active_matrices = [key for key in audit["matrices"] if key != "form_line"]
    for slice_name, cohorts in audit["cohort_auc"].items():
        lines.extend([
            f"### {slice_name}",
            "",
            "| Cohort | Races | " + " | ".join(active_matrices) + " |",
            "|---|---:|" + "---:|" * len(active_matrices),
        ])
        for label, row in cohorts.items():
            values = " | ".join(
                "n/a" if row["matrices"].get(key) is None
                else f"{row['matrices'][key]:.3f}"
                for key in active_matrices
            )
            lines.append(f"| {label} | {row['races']} | {values} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-json", type=Path, required=True)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("/private/tmp/au_feature_value_audit.json"),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("/private/tmp/au_feature_value_audit.md"),
    )
    args = parser.parse_args()
    dataset = json.loads(args.dataset_json.read_text(encoding="utf-8"))
    audit = build_audit(dataset)
    write_json_atomic(args.output_json, audit)
    write_text_atomic(args.output_md, render_markdown(audit))
    print(f"JSON: {args.output_json}")
    print(f"Markdown: {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
