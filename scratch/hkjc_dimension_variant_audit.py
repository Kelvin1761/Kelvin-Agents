#!/usr/bin/env python3
"""Audit outcome-blind HKJC dimension variants across every archive split.

This script diagnoses formulas; it does not create a final ranking.  Every
variant is calculated from pre-race primitives within a race, then evaluated
against competitive-tier, Top-3 and winner labels separately.  Formula names
and definitions are fixed before labels are consulted.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "scratch" / "hkjc_prerace_replay.csv"
DIMENSIONS = ROOT / "scratch" / "hkjc_rebuilt_dimensions.csv"
OUTPUT = ROOT / "scratch" / "hkjc_dimension_variant_audit.json"
REPORT = ROOT / "scratch" / "hkjc_dimension_variant_audit_report.md"

SPLITS = (
    "archive_development",
    "archive_temporal_holdout",
    "independent_recent",
    "external_2026_07_15",
)


def as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def as_int(value: Any, default: int = 0) -> int:
    number = as_float(value)
    return int(number) if number is not None else default


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def key(row: dict[str, Any]) -> tuple[str, str, int, int]:
    return (
        str(row["dataset"]),
        str(row["meeting"]),
        as_int(row["race_number"]),
        as_int(row["horse_number"]),
    )


def race_key(row: dict[str, Any]) -> tuple[str, str, int]:
    return key(row)[:3]


def normalized_rate(value: Any) -> float | None:
    rate = as_float(value)
    if rate is None:
        return None
    if abs(rate) > 1.0:
        rate /= 100.0
    return max(0.0, min(1.0, rate))


def relative(
    rows: list[dict[str, Any]],
    getter,
    *,
    higher_is_better: bool = True,
) -> dict[int, float]:
    values = {as_int(row["horse_number"]): getter(row) for row in rows}
    valid = {horse: value for horse, value in values.items() if value is not None}
    if len(valid) < 2:
        return {horse: 60.0 for horse in values}
    output = {}
    denominator = len(valid) - 1
    for horse, value in values.items():
        if value is None:
            output[horse] = 60.0
            continue
        others = [item for other, item in valid.items() if other != horse]
        worse = sum(item < value for item in others) if higher_is_better else sum(item > value for item in others)
        ties = sum(item == value for item in others)
        output[horse] = 50.0 + 20.0 * (worse + 0.5 * ties) / denominator
    return output


def weighted_available(parts: list[tuple[float | None, float]]) -> float | None:
    valid = [(value, weight) for value, weight in parts if value is not None]
    if not valid:
        return None
    total = sum(weight for _, weight in valid)
    return sum(float(value) * weight for value, weight in valid) / total


def bayes_rate(rate: float | None, starts: float | None, prior: float = 0.25, k: float = 20.0) -> float | None:
    if rate is None or starts is None or starts <= 0:
        return None
    return (rate * starts + prior * k) / (starts + k)


def variant_scores(
    rows: list[dict[str, Any]],
    dimensions: dict[tuple[str, str, int, int], dict[str, str]],
) -> dict[str, dict[int, float]]:
    horse_rows = {as_int(row["horse_number"]): row for row in rows}
    rating = relative(rows, lambda row: as_float(row.get("card_rating")))
    weight = relative(rows, lambda row: as_float(row.get("weight_carried")), higher_is_better=False)
    starts = relative(rows, lambda row: as_float(row.get("starts")))
    effective = relative(
        rows,
        lambda row: (
            as_float(row.get("card_rating")) - as_float(row.get("weight_carried"))
            if as_float(row.get("card_rating")) is not None
            and as_float(row.get("weight_carried")) is not None
            else None
        ),
    )
    season_place = relative(
        rows,
        lambda row: (
            (
                (as_float(row.get("season_wins")) or 0.0)
                + (as_float(row.get("season_seconds")) or 0.0)
                + (as_float(row.get("season_thirds")) or 0.0)
            )
            / max(as_float(row.get("season_starts")) or 0.0, 1.0)
            if (as_float(row.get("season_starts")) or 0.0) > 0
            else None
        ),
    )

    trainer_absolute_raw = {}
    trainer_combo_raw = {}
    trainer_edge_raw = {}
    form_weighted_raw = {}
    form_positive_raw = {}
    form_higher_raw = {}
    for horse, row in horse_rows.items():
        class_prior = normalized_rate(row.get("prior_class_distance_place_rate"))
        if class_prior is None:
            class_prior = 0.25
        components = []
        edge_components = []
        for prefix, part_weight in (
            ("prior_combo", 0.40),
            ("prior_jockey_cd", 0.35),
            ("prior_trainer_cd", 0.25),
        ):
            sample = as_float(row.get(f"{prefix}_starts"))
            rate = normalized_rate(row.get(f"{prefix}_place_rate"))
            smoothed = bayes_rate(rate, sample, class_prior, 20.0)
            components.append((smoothed, part_weight))
            edge_components.append(
                ((smoothed - class_prior) if smoothed is not None else None, part_weight)
            )
        trainer_absolute_raw[horse] = weighted_available(components)
        trainer_edge_raw[horse] = weighted_available(edge_components)
        trainer_combo_raw[horse] = bayes_rate(
            normalized_rate(row.get("prior_combo_place_rate")),
            as_float(row.get("prior_combo_starts")),
            class_prior,
            20.0,
        )

        higher = as_float(row.get("raw_formline_higher_win_count")) or 0.0
        same = as_float(row.get("raw_formline_same_win_count")) or 0.0
        lower = as_float(row.get("raw_formline_lower_win_count")) or 0.0
        total = higher + same + lower
        if total <= 0:
            form_weighted_raw[horse] = None
            form_positive_raw[horse] = None
            form_higher_raw[horse] = None
        else:
            reliability = total / (total + 3.0)
            form_weighted_raw[horse] = reliability * (3.0 * higher + same - lower) / total
            form_positive_raw[horse] = reliability * (3.0 * higher + same) / total
            form_higher_raw[horse] = reliability * higher / total

    def rel_from_map(values: dict[int, float | None]) -> dict[int, float]:
        proxy = [
            {"horse_number": horse, "_value": value}
            for horse, value in values.items()
        ]
        return relative(proxy, lambda row: row["_value"])

    trainer_absolute = rel_from_map(trainer_absolute_raw)
    trainer_combo = rel_from_map(trainer_combo_raw)
    trainer_edge = rel_from_map(trainer_edge_raw)
    form_weighted = rel_from_map(form_weighted_raw)
    form_positive = rel_from_map(form_positive_raw)
    form_higher = rel_from_map(form_higher_raw)

    variants: dict[str, dict[int, float]] = {
        "class_current_rebuilt": {},
        "class_rating_only": rating,
        "class_lower_weight_only": weight,
        "class_rating_weight_50_50": {
            horse: 0.50 * rating[horse] + 0.50 * weight[horse] for horse in horse_rows
        },
        "class_rating_weight_75_25": {
            horse: 0.75 * rating[horse] + 0.25 * weight[horse] for horse in horse_rows
        },
        "class_effective_rating_minus_weight": effective,
        "class_rating_experience": {
            horse: 0.80 * rating[horse] + 0.20 * starts[horse] for horse in horse_rows
        },
        "class_rating_season_place": {
            horse: 0.80 * rating[horse] + 0.20 * season_place[horse] for horse in horse_rows
        },
        "trainer_current_rebuilt": {},
        "trainer_absolute_stack": trainer_absolute,
        "trainer_combo_only": trainer_combo,
        "trainer_edge_stack": trainer_edge,
        "formline_current_rebuilt": {},
        "formline_weighted_relative": form_weighted,
        "formline_positive_relative": form_positive,
        "formline_higher_relative": form_higher,
    }
    for horse, row in horse_rows.items():
        dim = dimensions[key(row)]
        variants["class_current_rebuilt"][horse] = float(dim["dim_class_weight"])
        variants["trainer_current_rebuilt"][horse] = float(dim["dim_trainer_signal"])
        variants["formline_current_rebuilt"][horse] = float(dim["dim_form_line"])
    return variants


def pairwise_auc(records: list[tuple[float, int]]) -> tuple[float, int]:
    positives = [score for score, label in records if label]
    negatives = [score for score, label in records if not label]
    if not positives or not negatives:
        return 0.5, 0
    wins = ties = 0
    for positive in positives:
        for negative in negatives:
            wins += positive > negative
            ties += positive == negative
    pairs = len(positives) * len(negatives)
    return (wins + 0.5 * ties) / pairs, pairs


def evaluate(
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]],
    dimensions: dict[tuple[str, str, int, int], dict[str, str]],
) -> dict[str, Any]:
    storage: defaultdict[str, defaultdict[str, defaultdict[str, list[tuple[float, int]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for race_rows in grouped.values():
        split = race_rows[0]["split"]
        scores = variant_scores(race_rows, dimensions)
        field_size = len(race_rows)
        competitive_cutoff = min(5, max(3, math.ceil(field_size / 3)))
        for variant, horse_scores in scores.items():
            for row in race_rows:
                horse = as_int(row["horse_number"])
                finish = as_int(row["label_finish_position"], 99)
                storage[variant][split]["competitive"].append(
                    (horse_scores[horse], int(finish <= competitive_cutoff))
                )
                storage[variant][split]["top3"].append(
                    (horse_scores[horse], int(finish <= 3))
                )
                storage[variant][split]["winner"].append(
                    (horse_scores[horse], int(finish == 1))
                )

    output = {}
    for variant, split_rows in storage.items():
        output[variant] = {}
        for split in SPLITS:
            output[variant][split] = {}
            for target in ("competitive", "top3", "winner"):
                auc, pairs = pairwise_auc(split_rows[split][target])
                output[variant][split][target] = {
                    "auc": round(auc, 6),
                    "pairs": pairs,
                }
        non_external = [
            record
            for split in SPLITS[:-1]
            for record in split_rows[split]["competitive"]
        ]
        auc, pairs = pairwise_auc(non_external)
        output[variant]["archive_all"] = {"competitive": {
            "auc": round(auc, 6),
            "pairs": pairs,
        }}
    return output


def main() -> int:
    replay_rows = read_csv(REPLAY)
    grouped: defaultdict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in replay_rows:
        grouped[race_key(row)].append(row)
    dimensions = {key(row): row for row in read_csv(DIMENSIONS)}
    results = evaluate(dict(grouped), dimensions)

    families = {
        "class": [name for name in results if name.startswith("class_")],
        "trainer": [name for name in results if name.startswith("trainer_")],
        "formline": [name for name in results if name.startswith("formline_")],
    }
    selected = {}
    for family, variants in families.items():
        selected[family] = max(
            variants,
            key=lambda name: (
                results[name]["archive_development"]["competitive"]["auc"],
                results[name]["archive_development"]["top3"]["auc"],
            ),
        )

    payload = {
        "method": {
            "outcome_blind_formulas": True,
            "labels_used_only_for_audit": True,
            "race_relative_scores": True,
            "primary_target": "leading-third competitive tier, min 3 max 5",
        },
        "coverage": {
            "races": len(grouped),
            "meetings": len({item[1] for item in grouped}),
            "runners": len(replay_rows),
        },
        "development_selected": selected,
        "results": results,
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# HKJC Dimension Variant Audit",
        "",
        f"- Coverage: {payload['coverage']['meetings']} meetings / {payload['coverage']['races']} races / {payload['coverage']['runners']} runners",
        "- Primary target: leading-third competitive tier（最少3、最多5匹）",
        "",
        "| Family | Variant | Dev AUC | Temporal AUC | Recent AUC | 07-15 AUC | Archive AUC |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for family, variants in families.items():
        for variant in variants:
            item = results[variant]
            lines.append(
                f"| {family} | {variant} | "
                f"{item['archive_development']['competitive']['auc']:.3f} | "
                f"{item['archive_temporal_holdout']['competitive']['auc']:.3f} | "
                f"{item['independent_recent']['competitive']['auc']:.3f} | "
                f"{item['external_2026_07_15']['competitive']['auc']:.3f} | "
                f"{item['archive_all']['competitive']['auc']:.3f} |"
            )
    lines.extend(
        [
            "",
            "Development-selected variants:",
            *[f"- {family}: `{variant}`" for family, variant in selected.items()],
        ]
    )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"coverage": payload["coverage"], "selected": selected}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
