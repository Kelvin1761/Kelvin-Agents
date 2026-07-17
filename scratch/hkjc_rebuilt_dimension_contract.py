#!/usr/bin/env python3
"""Step-3 outcome-blind HKJC rebuilt-dimension contract.

The script consumes only the Step-2 primitive whitelist.  It does not read
finish labels, original ranks or original scores, and it does not calculate a
weighted ability/ranking.  All evidence reliability shrinks toward neutral 60.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from hkjc_prerace_replay_layer import IDENTITY_COLUMNS, PRIMITIVE_COLUMNS


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPLAY = ROOT / "scratch" / "hkjc_prerace_replay.csv"

DIMENSIONS = (
    "speed_engine",
    "stability",
    "distance_context",
    "class_weight",
    "trainer_signal",
    "readiness_risk",
    "form_line",
)

FORMULA_CONTRACT = {
    "global": {
        "neutral": 60.0,
        "shrinkage": "score = 60 + reliability * (raw_score - 60)",
        "relative_scale": "within-race percentile mapped to 50–70; ties averaged",
        "no_evidence": "score=60, reliability=0",
        "score_range": "0–100",
        "reliability_range": "0–1",
    },
    "speed_engine": {
        "inputs": ["raw_l400"],
        "formula": "70% existing L400 domain bands + 30% within-race lower-is-better percentile; then reliability 0.65",
        "excluded": ["going", "raw_finish_time_adj due development coverage 19.6%", "trackwork sectional", "distance bonus"],
        "cold_horse": "missing L400 remains neutral 60, not penalized",
    },
    "stability": {
        "inputs": ["last6_runs", "last6_mean_finish", "last6_best_finish", "last6_worst_finish", "last6_top3_count"],
        "formula": "50% mean-finish relative + 35% top3-rate relative + 15% finish-range relative; reliability=min(runs/4,1)",
        "excluded": ["form-line opponent strength", "trackwork", "margin narrative"],
        "cold_horse": "zero prior runs remains neutral 60",
    },
    "distance_context": {
        "inputs": [
            "same_distance_starts", "same_distance_wins", "same_distance_seconds", "same_distance_thirds",
            "same_venue_distance_starts", "same_venue_distance_wins", "same_venue_distance_seconds",
            "same_venue_distance_thirds", "prior_class_distance_place_rate",
        ],
        "formula": "same-distance place rate blended 65/35 with same-venue-distance when present; 4-run Bayesian shrink to class-distance prior, then within-race relative",
        "excluded": ["draw", "barrier", "going", "pace", "run style"],
        "cold_horse": "untried distance remains neutral instead of negative",
    },
    "class_weight": {
        "inputs": ["card_rating", "weight_carried", "starts"],
        "formula": "75% higher-rating within-race relative + 25% lower-weight relative; reliability from rating/weight availability and min(starts/4,1)",
        "excluded": ["distance evidence", "weight duplicated in readiness"],
        "cold_horse": "missing rating/weight component is omitted and weights renormalized",
    },
    "trainer_signal": {
        "inputs": [
            "prior_combo_starts", "prior_combo_place_rate", "prior_jockey_cd_starts",
            "prior_jockey_cd_place_rate", "prior_trainer_cd_starts", "prior_trainer_cd_place_rate",
            "prior_class_distance_place_rate",
        ],
        "formula": "combo/jockey-CD/trainer-CD weights 35/35/30; each place-rate delta vs class-distance baseline shrunk n/(n+20); 10-point place-rate delta maps to 8 score points",
        "excluded": ["ROI", "market", "confidence as positive edge", "draw prior", "run-style prior"],
        "cold_horse": "unmapped or zero-sample prior remains neutral",
    },
    "readiness_risk": {
        "inputs": ["days_since_last", "raw_weight_trend_span"],
        "formula": "structured rest/weight-span domain bands around neutral 60; reliability is available inputs / 2",
        "excluded": ["weight carried", "confidence coverage as ability", "trackwork amount due development coverage 35.8%", "narrative medical flags"],
        "cold_horse": "unknown readiness remains neutral",
    },
    "form_line": {
        "inputs": ["raw_formline_higher_win_count", "raw_formline_same_win_count", "raw_formline_lower_win_count"],
        "formula": "opponent strength=(3*higher + same - lower)/total; raw=60+6*strength; reliability=total/(total+3)",
        "excluded": ["same-distance evidence", "recent finishing positions", "margin trend"],
        "cold_horse": "no opponent follow-up evidence remains neutral",
    },
}


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def normalized_rate(value: Any) -> float | None:
    rate = as_float(value)
    if rate is None:
        return None
    if abs(rate) > 1.0:
        rate /= 100.0
    return clip(rate, 0.0, 1.0)


def shrink(raw_score: float, reliability: float) -> float:
    reliability = clip(reliability, 0.0, 1.0)
    return round(clip(60.0 + reliability * (raw_score - 60.0)), 4)


def weighted_available(parts: list[tuple[float | None, float]]) -> float | None:
    valid = [(value, weight) for value, weight in parts if value is not None]
    if not valid:
        return None
    total_weight = sum(weight for _, weight in valid)
    return sum(float(value) * weight for value, weight in valid) / total_weight


def relative_scores(values: dict[int, float | None], higher_is_better: bool) -> dict[int, float | None]:
    valid = {key: value for key, value in values.items() if value is not None}
    if len(valid) < 2:
        return {key: (60.0 if value is not None else None) for key, value in values.items()}
    output: dict[int, float | None] = {}
    denominator = len(valid) - 1
    for key, value in values.items():
        if value is None:
            output[key] = None
            continue
        others = [other for other_key, other in valid.items() if other_key != key]
        if higher_is_better:
            worse = sum(other < value for other in others)
        else:
            worse = sum(other > value for other in others)
        ties = sum(other == value for other in others)
        percentile = (worse + 0.5 * ties) / denominator
        output[key] = 50.0 + 20.0 * percentile
    return output


def l400_absolute_score(value: float) -> float:
    if value <= 22.4:
        return 68.62
    if value <= 23.0:
        return 64.55
    if value <= 23.6:
        return 63.03
    if value < 24.0:
        return 60.0
    if value < 24.6:
        return 59.27
    return 54.36


def place_rate(row: dict[str, Any], prefix: str) -> tuple[float | None, float]:
    starts = as_float(row.get(f"{prefix}_starts"))
    if starts is None or starts <= 0:
        return None, 0.0
    places = sum(as_float(row.get(f"{prefix}_{suffix}")) or 0.0 for suffix in ("wins", "seconds", "thirds"))
    return places / starts, starts


def preparation_score(row: dict[str, Any]) -> tuple[float, float, float]:
    days = as_float(row.get("days_since_last"))
    span = as_float(row.get("raw_weight_trend_span"))
    score = 60.0
    available = 0
    if days is not None:
        available += 1
        if days <= 7:
            score += 2.0 if span is not None and span <= 14.0 else -1.0
        elif days <= 21:
            score += 2.0
        elif days <= 45:
            score += 1.0
        elif days > 75:
            score -= 3.0
    if span is not None:
        available += 1
        if span <= 12:
            score += 3.0
        elif span <= 18:
            score += 1.5
        elif span <= 32:
            score -= 2.0
        else:
            score -= 4.0
    reliability = available / 2.0
    return score, shrink(score, reliability), reliability


def calculate_race(race_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_number = {int(float(row["horse_number"])): row for row in race_rows}

    def column_values(column: str, transform=None) -> dict[int, float | None]:
        output = {}
        for number, row in by_number.items():
            value = as_float(row.get(column))
            output[number] = transform(value, row) if value is not None and transform else value
        return output

    l400_rel = relative_scores(column_values("raw_l400"), higher_is_better=False)
    mean_finish_rel = relative_scores(column_values("last6_mean_finish"), higher_is_better=False)
    top3_rate_rel = relative_scores(
        column_values(
            "last6_top3_count",
            lambda value, row: value / max(as_float(row.get("last6_runs")) or 0.0, 1.0),
        ),
        higher_is_better=True,
    )
    range_rel = relative_scores(
        {
            number: (
                (as_float(row.get("last6_worst_finish")) or 0.0)
                - (as_float(row.get("last6_best_finish")) or 0.0)
                if as_float(row.get("last6_worst_finish")) is not None
                and as_float(row.get("last6_best_finish")) is not None
                else None
            )
            for number, row in by_number.items()
        },
        higher_is_better=False,
    )
    rating_rel = relative_scores(column_values("card_rating"), higher_is_better=True)
    weight_rel = relative_scores(column_values("weight_carried"), higher_is_better=False)

    distance_smoothed: dict[int, float | None] = {}
    distance_reliability: dict[int, float] = {}
    for number, row in by_number.items():
        class_prior = normalized_rate(row.get("prior_class_distance_place_rate"))
        baseline = class_prior if class_prior is not None else 0.25
        same_rate, same_starts = place_rate(row, "same_distance")
        venue_rate, venue_starts = place_rate(row, "same_venue_distance")
        if same_rate is None:
            distance_smoothed[number] = None
            distance_reliability[number] = 0.0
            continue
        same_smoothed = (same_rate * same_starts + baseline * 4.0) / (same_starts + 4.0)
        if venue_rate is not None:
            venue_smoothed = (venue_rate * venue_starts + baseline * 4.0) / (venue_starts + 4.0)
            distance_smoothed[number] = 0.65 * same_smoothed + 0.35 * venue_smoothed
        else:
            distance_smoothed[number] = same_smoothed
        distance_reliability[number] = same_starts / (same_starts + 4.0)
    distance_rel = relative_scores(distance_smoothed, higher_is_better=True)

    output = []
    for number, row in by_number.items():
        record = {column: row[column] for column in IDENTITY_COLUMNS if column in row}

        raw_l400 = as_float(row.get("raw_l400"))
        if raw_l400 is None:
            speed_raw = 60.0
            speed_reliability = 0.0
            speed_score = 60.0
        else:
            speed_raw = 0.70 * l400_absolute_score(raw_l400) + 0.30 * float(l400_rel[number])
            speed_reliability = 0.65
            speed_score = shrink(speed_raw, speed_reliability)

        runs = as_float(row.get("last6_runs")) or 0.0
        stability_raw = weighted_available(
            [
                (mean_finish_rel[number], 0.50),
                (top3_rate_rel[number], 0.35),
                (range_rel[number], 0.15),
            ]
        )
        stability_reliability = min(runs / 4.0, 1.0) if runs > 0 else 0.0
        stability_score = shrink(stability_raw or 60.0, stability_reliability)

        dist_rel = distance_rel[number]
        dist_reliability = distance_reliability[number]
        distance_score = shrink(dist_rel or 60.0, dist_reliability)

        class_raw = weighted_available([(rating_rel[number], 0.75), (weight_rel[number], 0.25)])
        class_fields = sum(as_float(row.get(column)) is not None for column in ("card_rating", "weight_carried"))
        career_starts = as_float(row.get("starts"))
        history_reliability = min(career_starts / 4.0, 1.0) if career_starts is not None else 0.5
        class_reliability = (class_fields / 2.0) * (0.75 + 0.25 * history_reliability)
        class_score = shrink(class_raw or 60.0, class_reliability)

        baseline = normalized_rate(row.get("prior_class_distance_place_rate"))
        if baseline is None:
            baseline = 0.25
        trainer_delta = 0.0
        trainer_reliability = 0.0
        trainer_weight_total = 0.0
        for prefix, weight in (("prior_combo", 0.35), ("prior_jockey_cd", 0.35), ("prior_trainer_cd", 0.30)):
            starts = as_float(row.get(f"{prefix}_starts"))
            rate = normalized_rate(row.get(f"{prefix}_place_rate"))
            if starts is None or rate is None or starts <= 0:
                continue
            reliability = starts / (starts + 20.0)
            trainer_delta += weight * reliability * (rate - baseline)
            trainer_reliability += weight * reliability
            trainer_weight_total += weight
        if trainer_weight_total:
            trainer_delta /= trainer_weight_total
            trainer_reliability /= trainer_weight_total
        trainer_score = round(clip(60.0 + 80.0 * trainer_delta), 4)

        readiness_raw, readiness_score, readiness_reliability = preparation_score(row)

        higher = as_float(row.get("raw_formline_higher_win_count"))
        same = as_float(row.get("raw_formline_same_win_count"))
        lower = as_float(row.get("raw_formline_lower_win_count"))
        if higher is None and same is None and lower is None:
            formline_reliability = 0.0
            formline_score = 60.0
            formline_raw = 60.0
        else:
            higher = higher or 0.0
            same = same or 0.0
            lower = lower or 0.0
            total = higher + same + lower
            if total <= 0:
                formline_reliability = 0.0
                formline_raw = 60.0
                formline_score = 60.0
            else:
                strength = (3.0 * higher + same - lower) / total
                formline_raw = clip(60.0 + 6.0 * strength)
                formline_reliability = total / (total + 3.0)
                formline_score = shrink(formline_raw, formline_reliability)

        dimension_values = {
            "speed_engine": (speed_raw, speed_reliability, speed_score),
            "stability": (stability_raw or 60.0, stability_reliability, stability_score),
            "distance_context": (dist_rel or 60.0, dist_reliability, distance_score),
            "class_weight": (class_raw or 60.0, class_reliability, class_score),
            "trainer_signal": (60.0 + 80.0 * trainer_delta, trainer_reliability, trainer_score),
            "readiness_risk": (readiness_raw, readiness_reliability, readiness_score),
            "form_line": (formline_raw, formline_reliability, formline_score),
        }
        for dimension, (raw_value, reliability, score) in dimension_values.items():
            record[f"raw_{dimension}"] = round(float(raw_value), 4)
            record[f"reliability_{dimension}"] = round(float(reliability), 4)
            record[f"dim_{dimension}"] = round(float(score), 4)
        reliabilities = [dimension_values[dimension][1] for dimension in DIMENSIONS]
        record["rebuild_reliability_mean"] = round(statistics.mean(reliabilities), 4)
        record["rebuild_uncertainty"] = round(1.0 - record["rebuild_reliability_mean"], 4)
        record["supported_upside_count"] = sum(
            dimension_values[dimension][2] >= 64.0 and dimension_values[dimension][1] >= 0.50
            for dimension in DIMENSIONS
        )
        output.append(record)
    return output


def build_scores(replay_path: Path) -> list[dict[str, Any]]:
    rows = list(csv.DictReader(replay_path.open(encoding="utf-8-sig", newline="")))
    # Outcome and original-model columns are deliberately discarded here.
    sanitized = [
        {column: row.get(column) for column in (*IDENTITY_COLUMNS, *PRIMITIVE_COLUMNS)}
        for row in rows
    ]
    races: defaultdict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in sanitized:
        races[(row["dataset"], row["meeting"], row["race_number"])].append(row)
    output = []
    for key in sorted(races):
        output.extend(calculate_race(races[key]))
    return output


def pearson(rows: list[dict[str, Any]], left: str, right: str) -> float:
    xs = [float(row[left]) for row in rows]
    ys = [float(row[right]) for row in rows]
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denominator = math.sqrt(sum((x - mean_x) ** 2 for x in xs) * sum((y - mean_y) ** 2 for y in ys))
    return round(numerator / denominator, 4) if denominator else 0.0


def distribution(rows: list[dict[str, Any]], dimension: str) -> dict[str, Any]:
    scores = [float(row[f"dim_{dimension}"]) for row in rows]
    reliabilities = [float(row[f"reliability_{dimension}"]) for row in rows]
    return {
        "rows": len(rows),
        "mean": round(statistics.mean(scores), 4),
        "stdev": round(statistics.pstdev(scores), 4),
        "minimum": round(min(scores), 4),
        "maximum": round(max(scores), 4),
        "neutral_60_rate": round(sum(abs(score - 60.0) < 1e-9 for score in scores) / len(scores) * 100, 1),
        "mean_reliability": round(statistics.mean(reliabilities), 4),
        "low_reliability_rate": round(sum(value < 0.25 for value in reliabilities) / len(reliabilities) * 100, 1),
    }


def validate(rows: list[dict[str, Any]]) -> list[str]:
    errors = []
    if len(rows) != 3054:
        errors.append(f"row count {len(rows)} != 3054")
    forbidden_output_tokens = ("label_", "reference_", "odds", "market", "roi", "edge", "draw", "going", "pace", "barrier")
    output_columns = set(rows[0]) if rows else set()
    for column in output_columns:
        if any(token in column.lower() for token in forbidden_output_tokens):
            errors.append(f"forbidden output column {column}")
    for row in rows:
        for dimension in DIMENSIONS:
            score = float(row[f"dim_{dimension}"])
            reliability = float(row[f"reliability_{dimension}"])
            if not 0.0 <= score <= 100.0:
                errors.append(f"score out of range {dimension}")
            if not 0.0 <= reliability <= 1.0:
                errors.append(f"reliability out of range {dimension}")
            if reliability == 0.0 and abs(score - 60.0) > 1e-9:
                errors.append(f"zero evidence not neutral {dimension}")
        if not 0.0 <= float(row["rebuild_uncertainty"]) <= 1.0:
            errors.append("uncertainty out of range")
        if errors:
            break
    return errors


def write_outputs(rows: list[dict[str, Any]], errors: list[str], output_prefix: Path) -> None:
    csv_path = output_prefix.with_suffix(".csv")
    json_path = output_prefix.with_suffix(".json")
    report_path = output_prefix.with_name(output_prefix.name + "_report").with_suffix(".md")
    fields = list(rows[0]) if rows else []
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    splits = ["overall", *sorted({row["split"] for row in rows})]
    distributions = {
        split: {
            dimension: distribution(rows if split == "overall" else [row for row in rows if row["split"] == split], dimension)
            for dimension in DIMENSIONS
        }
        for split in splits
    }
    correlations = []
    for index, left in enumerate(DIMENSIONS):
        for right in DIMENSIONS[index + 1 :]:
            correlations.append(
                {
                    "left": left,
                    "right": right,
                    "correlation": pearson(rows, f"dim_{left}", f"dim_{right}"),
                }
            )
    correlations.sort(key=lambda row: -abs(row["correlation"]))
    payload = {
        "method": {
            "outcome_blind": True,
            "uses_finish_labels": False,
            "uses_original_rank_or_score": False,
            "calculates_weighted_ability": False,
            "calculates_ranking": False,
            "missing_is_neutral_60": True,
            "public_12_feature_schema_unchanged": True,
        },
        "formula_contract": FORMULA_CONTRACT,
        "distributions": distributions,
        "dimension_correlations": correlations,
        "validation_errors": errors,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# HKJC Dimension重建 Step 3 — Outcome-blind公式契約",
        "",
        "## 硬約束",
        "",
        "- 只讀Step 2 primitive白名單；程式入口即時丟棄賽果label、原模型rank及原分數。",
        "- 無going、draw、barrier、track bias、pace、run style、odds、市場、ROI、edge。",
        "- 缺資料一律60；可靠度只控制向60收縮，唔會本身加能力分。",
        "- 本步無ability權重、無Top 2排名、無AUC或命中率，避免睇結果定公式。",
        "",
        "## 七個重建dimension",
        "",
        "| Dimension | 核心輸入 | 收縮／主要規則 |",
        "|---|---|---|",
    ]
    for dimension in DIMENSIONS:
        contract = FORMULA_CONTRACT[dimension]
        lines.append(
            f"| {dimension} | {', '.join(contract['inputs'])} | {contract['formula']}；{contract['cold_horse']} |"
        )
    lines.extend(
        [
            "",
            "## 分數分布（不含賽果）",
            "",
            "| Dimension | Mean | SD | 中性60 | 平均可靠度 | 低可靠度<0.25 | Min–Max |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for dimension in DIMENSIONS:
        row = distributions["overall"][dimension]
        lines.append(
            f"| {dimension} | {row['mean']:.2f} | {row['stdev']:.2f} | {row['neutral_60_rate']:.1f}% | "
            f"{row['mean_reliability']:.2f} | {row['low_reliability_rate']:.1f}% | {row['minimum']:.1f}–{row['maximum']:.1f} |"
        )
    lines.extend(
        [
            "",
            "## 跨split分數／可靠度（不含賽果）",
            "",
            "每格係 `平均分／平均可靠度`；用嚟確認coverage漂移主要反映喺可靠度，而唔係製造跨版本分數偏移。",
            "",
            "| Dimension | Development | Temporal | 近期獨立 | 07-15 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    split_order = (
        "archive_development",
        "archive_temporal_holdout",
        "independent_recent",
        "external_2026_07_15",
    )
    for dimension in DIMENSIONS:
        cells = [
            f"{distributions[split][dimension]['mean']:.2f}/{distributions[split][dimension]['mean_reliability']:.2f}"
            for split in split_order
        ]
        lines.append(f"| {dimension} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} |")
    lines.extend(
        [
            "",
            "## Dimension重疊警報",
            "",
            "| Dimension A | Dimension B | Correlation |",
            "|---|---|---:|",
        ]
    )
    for row in correlations[:10]:
        lines.append(f"| {row['left']} | {row['right']} | {row['correlation']:+.3f} |")
    lines.extend(
        [
            "",
            "## Step 3狀態",
            "",
            f"- 產生{len(rows)}匹outcome-blind dimension rows；validation errors：{len(errors)}。",
            "- 初出／資料薄弱馬保留neutral upside；`supported_upside_count`只計可靠度≥0.50而分數≥64嘅支持訊號。",
            "- 現有完成時間調整、操練量及敘事flag只記coverage，今版不進能力公式。",
            "- 尚未用賽果做單項診斷、ablation、權重、排名或第三選升格測試；正式Auto engine不變。",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "csv": str(csv_path),
                "json": str(json_path),
                "report": str(report_path),
                "rows": len(rows),
                "validation_errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=ROOT / "scratch" / "hkjc_rebuilt_dimensions",
    )
    args = parser.parse_args()
    rows = build_scores(args.replay)
    errors = validate(rows)
    write_outputs(rows, errors, args.output_prefix)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
