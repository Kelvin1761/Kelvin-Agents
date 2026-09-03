#!/usr/bin/env python3
"""Attribute AU cold-last and missed-favourite errors before proposing fixes.

The audit freezes production ranks first.  SP and finishing position are then
used only to label retrospective errors.  For every labelled runner it
decomposes the score gap against the rank-4 cutoff and runs one-variable
counterfactuals at matrix and Performance Quality leaf level.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from au_racing_engine import matrix_mapper  # noqa: E402
from au_eval import default_scorer, load_races  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402

MATRIX_KEYS = tuple(MATRIX_WEIGHTS)
STABILITY_PERFORMANCE_SHARE = 0.40
CONTROL_FEATURE_KEYS = (
    "form_score", "trial_score", "sectional_score", "pace_figure_score",
    "rating_score", "consistency_score", "performance_quality_score",
)


def _rank_lookup(race: dict, scores: dict[int, float]) -> dict[int, int]:
    ranked = sorted(
        race["rows"],
        key=lambda row: (-scores[int(row["horse_number"])], int(row["horse_number"])),
    )
    return {
        int(row["horse_number"]): rank for rank, row in enumerate(ranked, 1)
    }


def _base_scores(race: dict) -> dict[int, float]:
    return {
        int(row["horse_number"]): float(default_scorer(row))
        for row in race["rows"]
    }


def _cohort_members(races: list[dict], scorer) -> dict[str, dict[str, dict]]:
    """Freeze score-only ranks before applying retrospective labels."""
    output = {"cold_last": {}, "favourite_missed": {}}
    for race_index, race in enumerate(races):
        rows = race["rows"]
        scores = {
            int(row["horse_number"]): float(scorer(row)) for row in rows
        }
        ranks = _rank_lookup(race, scores)
        last = max(int(row["pos"]) for row in rows)
        prices = [
            float(row["result_sp_label"])
            for row in rows if row.get("result_sp_label") is not None
        ]
        favourite = min(prices) if prices else None
        for row in rows:
            number = int(row["horse_number"])
            actual = int(row["pos"])
            price = row.get("result_sp_label")
            key = f"{race_index}:{number}"
            item = {"race_index": race_index, "rank": ranks[number], "row": row}
            if (
                price is not None and float(price) >= 21.0
                and actual == last and ranks[number] <= 3
            ):
                output["cold_last"][key] = item
            if (
                favourite is not None and price is not None
                and float(price) == favourite and actual <= 3
                and ranks[number] >= 5
            ):
                output["favourite_missed"][key] = item
    return output


def _transition_counts(before: dict, after: dict) -> dict:
    output = {}
    for cohort in before:
        old = set(before[cohort])
        new = set(after[cohort])
        output[cohort] = {
            "before": len(old),
            "after": len(new),
            "net_change": len(new) - len(old),
            "original_failures_fixed": len(old - new),
            "new_failures_created": len(new - old),
            "original_failures_remaining": len(old & new),
        }
    return output


def _score_with_performance_quality(row: dict, value: float) -> float:
    features = dict(row["features"])
    features["performance_quality_score"] = float(value)
    matrices = matrix_mapper.map_features_to_matrix_scores(features)
    return sum(
        matrices.get(key, 60.0) * weight
        for key, weight in MATRIX_WEIGHTS.items()
    ) + float(row.get("wet") or 0.0)


def _gaps(row: dict) -> list[str]:
    return sorted(
        key for key, state in (row.get("feature_evidence_state") or {}).items()
        if state in {"missing", "fallback"}
    )


def _field_means(race: dict, container: str) -> dict[str, float]:
    keys = set().union(*(row.get(container, {}) for row in race["rows"]))
    return {
        key: mean(float(row.get(container, {}).get(key, 60.0)) for row in race["rows"])
        for key in keys
    }


def _primary_label(
    cohort: str,
    primary_matrix: str,
    gaps: set[str],
    pq_direct: bool,
) -> str:
    if pq_direct:
        return "performance_quality_relative_distortion"
    if primary_matrix == "stability" and "performance_quality_score" in gaps:
        return "stability_form_consistency_bundle"
    if primary_matrix == "pace_perf" and gaps & {
        "sectional_score", "pace_figure_score", "distance_score"
    }:
        return "pace_performance_evidence_gap"
    if primary_matrix == "class_weight" and gaps & {
        "rating_score", "weight_score", "class_score"
    }:
        return "class_weight_evidence_gap"
    if primary_matrix == "jockey_trainer" and "jockey_horse_fit_score" in gaps:
        return "jockey_trainer_fit_evidence_gap"
    if primary_matrix == "track" and "track_score" in gaps:
        return "track_evidence_gap"
    direction = "overrated" if cohort == "cold_last" else "underrated"
    return f"{primary_matrix}_{direction}"


def _record_for(
    race_index: int,
    race: dict,
    row: dict,
    cohort: str,
) -> dict:
    base_scores = _base_scores(race)
    ranks = _rank_lookup(race, base_scores)
    number = int(row["horse_number"])
    cutoff = next(
        member for member in race["rows"]
        if ranks[int(member["horse_number"])] == 4
    )
    cutoff_number = int(cutoff["horse_number"])
    matrix_means = _field_means(race, "matrix_scores")
    feature_means = _field_means(race, "features")

    signed = []
    for key in MATRIX_KEYS:
        value = float((row.get("matrix_scores") or {}).get(key, 60.0))
        cutoff_value = float((cutoff.get("matrix_scores") or {}).get(key, 60.0))
        signed.append({
            "matrix": key,
            "runner": round(value, 3),
            "cutoff": round(cutoff_value, 3),
            "weighted_gap": round((value - cutoff_value) * MATRIX_WEIGHTS[key], 6),
        })
    signed.sort(
        key=lambda item: item["weighted_gap"],
        reverse=(cohort == "cold_last"),
    )
    primary_matrix = signed[0]["matrix"]

    single_matrix_sufficient = []
    for key in MATRIX_KEYS:
        changed = dict(base_scores)
        current = float((row.get("matrix_scores") or {}).get(key, 60.0))
        changed[number] += (matrix_means[key] - current) * MATRIX_WEIGHTS[key]
        new_rank = _rank_lookup(race, changed)[number]
        if (cohort == "cold_last" and new_rank > 3) or (
            cohort == "favourite_missed" and new_rank <= 4
        ):
            single_matrix_sufficient.append(key)

    current_pq = float(row["features"].get("performance_quality_score", 60.0))
    field_pq = float(feature_means.get("performance_quality_score", 60.0))
    field_scores = dict(base_scores)
    field_scores[number] = _score_with_performance_quality(row, field_pq)
    pq_field_rank = _rank_lookup(race, field_scores)[number]
    pq_direct = (
        (cohort == "cold_last" and pq_field_rank > 3)
        or (cohort == "favourite_missed" and pq_field_rank <= 4)
    )
    neutral_scores = dict(base_scores)
    neutral_scores[number] = _score_with_performance_quality(row, 60.0)
    pq_neutral_rank = _rank_lookup(race, neutral_scores)[number]
    gaps = set(_gaps(row))
    metadata = race.get("metadata") or {}
    return {
        "race_id": (
            f"{metadata.get('date')}|{metadata.get('track')}|"
            f"R{metadata.get('race_number')}"
        ),
        "race_index": race_index,
        "horse_number": number,
        "horse_name": row.get("horse_name"),
        "model_rank": ranks[number],
        "actual_pos": int(row["pos"]),
        "sp": row.get("result_sp_label"),
        "cutoff_horse": cutoff.get("horse_name"),
        "cutoff_score_gap": round(base_scores[number] - base_scores[cutoff_number], 6),
        "primary_matrix": primary_matrix,
        "primary_attribution": _primary_label(
            cohort, primary_matrix, gaps, pq_direct
        ),
        "matrix_gap_contributions": signed,
        "single_matrix_field_mean_sufficient": single_matrix_sufficient,
        "evidence_gaps": sorted(gaps),
        "performance_quality": {
            "state": (row.get("feature_evidence_state") or {}).get(
                "performance_quality_score", "missing"
            ),
            "provenance": (row.get("score_provenance") or {}).get(
                "performance_quality_score", ""
            ),
            "current": round(current_pq, 3),
            "field_mean": round(field_pq, 3),
            "field_delta": round(current_pq - field_pq, 3),
            "effective_score_vs_neutral": round(
                (current_pq - 60.0)
                * STABILITY_PERFORMANCE_SHARE
                * MATRIX_WEIGHTS["stability"],
                6,
            ),
            "rank_if_field_mean": pq_field_rank,
            "rank_if_neutral": pq_neutral_rank,
            "field_mean_counterfactual_fixes_case": pq_direct,
        },
    }


def _summary(records: list[dict]) -> dict:
    pq = [record["performance_quality"] for record in records]
    return {
        "count": len(records),
        "primary_attributions": dict(Counter(
            record["primary_attribution"] for record in records
        )),
        "primary_matrices": dict(Counter(
            record["primary_matrix"] for record in records
        )),
        "single_matrix_sufficient": dict(Counter(
            key
            for record in records
            for key in record["single_matrix_field_mean_sufficient"]
        )),
        "missing_or_fallback_features": dict(Counter(
            gap for record in records for gap in record["evidence_gaps"]
        )),
        "performance_quality_fallback": sum(
            item["state"] in {"missing", "fallback"} for item in pq
        ),
        "performance_quality_direct_counterfactual_fixes": sum(
            item["field_mean_counterfactual_fixes_case"] for item in pq
        ),
        "performance_quality_mean": round(mean(item["current"] for item in pq), 3),
        "performance_quality_field_delta_mean": round(
            mean(item["field_delta"] for item in pq), 3
        ),
        "performance_quality_effective_vs_neutral_mean": round(
            mean(item["effective_score_vs_neutral"] for item in pq), 3
        ),
        "cutoff_score_gap_mean": round(
            mean(record["cutoff_score_gap"] for record in records), 3
        ),
    }


def _neutral_fallback_scorer(row: dict) -> float:
    state = (row.get("feature_evidence_state") or {}).get(
        "performance_quality_score"
    )
    if state not in {"missing", "fallback"}:
        return float(default_scorer(row))
    return _score_with_performance_quality(row, 60.0)


def _formal_band(row: dict) -> str:
    count = int((row.get("raw_pre_race") or {}).get("formal_count") or 0)
    if count == 0:
        return "0"
    if count <= 2:
        return "1-2"
    if count <= 4:
        return "3-4"
    return "5+"


def _going_bucket(race: dict) -> str:
    going = str((race.get("metadata") or {}).get("going") or "").lower()
    for bucket in ("heavy", "soft", "good", "synthetic"):
        if bucket in going:
            return bucket
    return "other"


def _control_summary(items: list[dict]) -> dict:
    count = len(items)
    gaps = Counter(
        gap
        for item in items
        for gap in _gaps(item["row"])
    )
    formal = Counter(_formal_band(item["row"]) for item in items)
    going = Counter(item["going"] for item in items)
    formal_going = Counter(
        f"{_formal_band(item['row'])}|{item['going']}" for item in items
    )
    ability_keys = tuple(key for key in MATRIX_KEYS if key != "race_shape")
    corroboration = Counter(
        sum(item["matrix_deltas"].get(key, 0.0) > 0 for key in ability_keys)
        for item in items
    )
    by_formal_band = {}
    for band in ("0", "1-2", "3-4", "5+"):
        members = [item for item in items if _formal_band(item["row"]) == band]
        if members:
            by_formal_band[band] = {
                key: round(mean(item["matrix_deltas"].get(key, 0.0) for item in members), 3)
                for key in MATRIX_KEYS
            }
    return {
        "count": count,
        "matrix_field_delta_means": {
            key: round(mean(item["matrix_deltas"].get(key, 0.0) for item in items), 3)
            for key in MATRIX_KEYS
        },
        "feature_means": {
            key: round(mean(float(item["row"]["features"].get(key, 60.0)) for item in items), 3)
            for key in CONTROL_FEATURE_KEYS
        },
        "gap_rates": {
            key: round(value / count, 4) for key, value in gaps.items()
        },
        "performance_quality_fallback_rate": round(
            sum(
                (item["row"].get("feature_evidence_state") or {}).get(
                    "performance_quality_score"
                ) in {"missing", "fallback"}
                for item in items
            ) / count,
            4,
        ),
        "formal_count_bands": dict(formal),
        "formal_count_band_rates": {
            key: round(value / count, 4) for key, value in formal.items()
        },
        "formal_going_counts": dict(formal_going),
        "ability_corroboration_counts": {
            str(key): value for key, value in sorted(corroboration.items())
        },
        "matrix_field_delta_by_formal_band": by_formal_band,
        "coverage_mean": round(mean(
            float((item["row"].get("data_coverage") or {}).get("coverage_pct") or 0)
            for item in items
        ), 3),
        "going": dict(going),
    }


def matched_controls(races: list[dict]) -> dict:
    groups = {
        "cold_failure": [], "cold_success": [],
        "favourite_failure": [], "favourite_success": [],
    }
    for race in races:
        rows = race["rows"]
        scores = _base_scores(race)
        ranks = _rank_lookup(race, scores)
        last = max(int(row["pos"]) for row in rows)
        prices = [
            float(row["result_sp_label"])
            for row in rows if row.get("result_sp_label") is not None
        ]
        favourite = min(prices) if prices else None
        matrix_means = _field_means(race, "matrix_scores")
        for row in rows:
            number = int(row["horse_number"])
            rank = ranks[number]
            actual = int(row["pos"])
            price = row.get("result_sp_label")
            item = {
                "row": row,
                "going": _going_bucket(race),
                "matrix_deltas": {
                    key: float(row["matrix_scores"].get(key, 60.0)) - matrix_means[key]
                    for key in MATRIX_KEYS
                },
            }
            if price is not None and float(price) >= 21.0 and rank <= 3:
                if actual == last:
                    groups["cold_failure"].append(item)
                elif actual <= 3:
                    groups["cold_success"].append(item)
            if (
                favourite is not None
                and price is not None
                and float(price) == favourite
                and actual <= 3
            ):
                if rank >= 5:
                    groups["favourite_failure"].append(item)
                elif rank <= 4:
                    groups["favourite_success"].append(item)
    summary = {key: _control_summary(items) for key, items in groups.items()}
    contrasts = {}
    for label, failed, success in (
        ("cold_failure_minus_success", "cold_failure", "cold_success"),
        ("favourite_failure_minus_success", "favourite_failure", "favourite_success"),
    ):
        contrasts[label] = {
            "matrix_field_delta": {
                key: round(
                    summary[failed]["matrix_field_delta_means"][key]
                    - summary[success]["matrix_field_delta_means"][key],
                    3,
                )
                for key in MATRIX_KEYS
            },
            "feature_mean": {
                key: round(
                    summary[failed]["feature_means"][key]
                    - summary[success]["feature_means"][key],
                    3,
                )
                for key in CONTROL_FEATURE_KEYS
            },
            "performance_quality_fallback_rate": round(
                summary[failed]["performance_quality_fallback_rate"]
                - summary[success]["performance_quality_fallback_rate"],
                4,
            ),
            "coverage_mean": round(
                summary[failed]["coverage_mean"] - summary[success]["coverage_mean"],
                3,
            ),
        }
    return {"groups": summary, "contrasts": contrasts}


def analyze(races: list[dict]) -> dict:
    cohorts = _cohort_members(races, default_scorer)
    records = {"cold_last": [], "favourite_missed": []}
    for cohort, members in cohorts.items():
        for item in members.values():
            race_index = int(item["race_index"])
            records[cohort].append(_record_for(
                race_index, races[race_index], item["row"], cohort
            ))
    neutral = _transition_counts(
        cohorts, _cohort_members(races, _neutral_fallback_scorer)
    )
    return {
        "design": {
            "rank_input": "production pre-race features only",
            "sp_role": "post-rank cohort label only",
            "actual_position_role": "post-rank cohort label only",
            "comparison": "failed runner versus production rank-4 cutoff",
            "counterfactual": "one matrix/leaf moved to field mean; all others frozen",
        },
        "races": len(races),
        "summary": {
            cohort: _summary(items) for cohort, items in records.items()
        },
        "neutral_fallback_global_transition": {
            cohort: item for cohort, item in neutral.items()
        },
        "matched_controls": matched_controls(races),
        "records": records,
    }


def render_markdown(report: dict) -> str:
    labels = {
        "cold_last": "冷門包尾：Model Top3 + SP≥21 + 實際包尾",
        "favourite_missed": "熱門漏捉：市場頭馬入前三、Model 第5+",
    }
    lines = [
        "# AU Failure Cause Attribution",
        "",
        f"- Races: **{report['races']}**",
        "- 先固定 production rank；SP／賽果只用嚟標籤錯例，從不進 scorer。",
        "- `missing/fallback` 只係資料狀態；要 field-mean 單變量反事實真係令錯例消失，先計直接歸因。",
    ]
    for cohort, item in report["summary"].items():
        neutral = report["neutral_fallback_global_transition"][cohort]
        lines.extend([
            "",
            f"## {labels[cohort]}",
            "",
            f"- Cases: **{item['count']}**；Performance Quality fallback: "
            f"**{item['performance_quality_fallback']}**。",
            f"- PQ 單獨拉到場內平均可直接修正："
            f"**{item['performance_quality_direct_counterfactual_fixes']}**。",
            f"- 全場 fallback 一律改 60：修正 {neutral['original_failures_fixed']}、"
            f"新造 {neutral['new_failures_created']}，淨數 {neutral['before']}→{neutral['after']}。",
            "",
            "### Dominant attribution",
            "",
            "| Attribution | Cases |",
            "|---|---:|",
        ])
        for key, count in sorted(
            item["primary_attributions"].items(), key=lambda pair: -pair[1]
        ):
            lines.append(f"| {key} | {count} |")
        lines.extend([
            "",
            "### Matrix gap versus rank-4 cutoff",
            "",
            "| Race | Horse | Rank | Cutoff gap | Primary | PQ state | PQ→field rank |",
            "|---|---|---:|---:|---|---|---:|",
        ])
        for record in report["records"][cohort]:
            pq = record["performance_quality"]
            lines.append(
                f"| {record['race_id']} | {record['horse_name']} | "
                f"{record['model_rank']} | {record['cutoff_score_gap']:+.2f} | "
                f"{record['primary_attribution']} | {pq['state']} | "
                f"{pq['rank_if_field_mean']} |"
            )
    lines.extend([
        "",
        "## Matched-control contrast",
        "",
        "| Contrast | PQ fallback Δ | Coverage Δ | Stability | Pace/perf | Race shape | J/T | Class/weight | Track |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for label, item in report["matched_controls"]["contrasts"].items():
        matrix = item["matrix_field_delta"]
        lines.append(
            f"| {label} | {item['performance_quality_fallback_rate'] * 100:+.1f}pp | "
            f"{item['coverage_mean']:+.1f}pp | {matrix['stability']:+.2f} | "
            f"{matrix['pace_perf']:+.2f} | {matrix['race_shape']:+.2f} | "
            f"{matrix['jockey_trainer']:+.2f} | {matrix['class_weight']:+.2f} | "
            f"{matrix['track']:+.2f} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--output-json", type=Path,
        default=Path("/private/tmp/au_failure_cause_attribution.json"),
    )
    parser.add_argument(
        "--output-md", type=Path,
        default=Path("/private/tmp/au_failure_cause_attribution.md"),
    )
    args = parser.parse_args()
    report = analyze(load_races(args.dataset))
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.output_md.write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))
    print(args.output_json)
    print(args.output_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
