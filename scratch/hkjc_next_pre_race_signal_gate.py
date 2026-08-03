#!/usr/bin/env python3
"""Gate the next batch of strictly pre-race HKJC competitiveness signals.

The production baseline includes the already-promoted 5% normalized-sectional
blend. Candidates operate on full matrix dimensions before the official outer
weights; there are no swaps, odds, result-derived inputs, or micro tie-breaks.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from collections import Counter
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
HQ_GATE = ROOT / "scratch" / "hkjc_high_quality_dimension_gate.py"
SHARED = ROOT / ".agents" / "skills" / "shared_racing"
ENGINE = (
    ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi_auto"
    / "scripts" / "racing_engine"
)
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(ENGINE))

from eval_metrics import race_metrics, summarize_races  # noqa: E402
from scoring import MATRIX_WEIGHTS  # noqa: E402


_spec = importlib.util.spec_from_file_location("hkjc_hq_gate", HQ_GATE)
hq = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(hq)

JSON_OUT = ROOT / "scratch" / "hkjc_next_pre_race_signal_gate.json"
REPORT_OUT = ROOT / "scratch" / "hkjc_next_pre_race_signal_gate_report.md"
BASE_SECTIONAL_ALPHA = 0.05


def prepare() -> pd.DataFrame:
    data = hq.prepare()
    archive = pd.read_csv(hq.ARCHIVE)
    archive["dataset"] = "archive"
    external = pd.read_csv(hq.EXTERNAL)
    external["dataset"] = "external"
    raw = pd.concat([archive, external], ignore_index=True)
    keys = ["dataset", "meeting_name", "race_number", "horse_number"]
    extra = [
        "card_rating",
        "raw_finish_time_adj",
        "raw_last_margin",
        "last6_mean_finish",
        "raw_formline_higher_win_count",
        "raw_formline_same_win_count",
        "raw_formline_lower_win_count",
    ]
    data = data.merge(
        raw[keys + extra],
        on=keys,
        how="left",
        validate="one_to_one",
    )
    for column in extra:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return data


def _relative(rows: pd.DataFrame, column: str, higher_is_better: bool) -> dict[int, float | None]:
    return hq.relative(rows, column, higher_is_better)


def build_signals(rows: pd.DataFrame) -> dict[str, dict[int, float | None]]:
    sectional = hq.signal_score(rows, "sectional_combo")
    finish_time = _relative(rows, "raw_finish_time_adj", False)
    last_margin = _relative(rows, "raw_last_margin", False)

    opponent_raw = rows.copy()
    opponent_raw["opponent_evidence"] = (
        opponent_raw["raw_formline_higher_win_count"].fillna(0)
        + opponent_raw["raw_formline_same_win_count"].fillna(0)
        + opponent_raw["raw_formline_lower_win_count"].fillna(0)
    )
    opponent_raw["opponent_quality_raw"] = (
        3 * opponent_raw["raw_formline_higher_win_count"].fillna(0)
        + opponent_raw["raw_formline_same_win_count"].fillna(0)
        - opponent_raw["raw_formline_lower_win_count"].fillna(0)
    ).where(opponent_raw["opponent_evidence"] > 0)
    opponent = _relative(opponent_raw, "opponent_quality_raw", True)

    speed_time: dict[int, float | None] = {}
    cold_ceiling: dict[int, float | None] = {}
    for row in rows.itertuples():
        horse = int(row.horse_number)
        sec = sectional.get(horse)
        ft = finish_time.get(horse)
        margin = last_margin.get(horse)
        speed_time[horse] = (
            None if sec is None or ft is None else 0.60 * sec + 0.40 * ft
        )

        # Cold-horse upside needs two independent positive confirmations. A
        # weak recent mean is only a selector, never a positive input itself.
        recent_mean = getattr(row, "last6_mean_finish")
        confirmations = [
            value for value in (sec, ft, margin)
            if value is not None and value >= 65.0
        ]
        cold_ceiling[horse] = (
            sum(confirmations) / len(confirmations)
            if not pd.isna(recent_mean) and recent_mean > 5.5 and len(confirmations) >= 2
            else None
        )

    return {
        "sectional": sectional,
        "finish_time": finish_time,
        "last_margin": last_margin,
        "opponent_quality": opponent,
        "speed_time_consensus": speed_time,
        "cold_ceiling": cold_ceiling,
    }


def attach_signals(data: pd.DataFrame) -> pd.DataFrame:
    """Calculate each race-relative signal once and reuse it for every spec."""
    output = attach_walkforward_race_strength(data.copy())
    signal_names = (
        "sectional",
        "finish_time",
        "last_margin",
        "opponent_quality",
        "speed_time_consensus",
        "cold_ceiling",
    )
    columns = {
        name: pd.Series(index=output.index, dtype=float)
        for name in signal_names
    }
    for _, rows in output.groupby(["meeting_name", "race_number"], sort=False):
        signals = build_signals(rows)
        for idx, row in rows.iterrows():
            horse = int(row["horse_number"])
            for name in signal_names:
                columns[name].loc[idx] = signals[name].get(horse)
    for name, values in columns.items():
        output[f"_signal_{name}"] = values
    return output


def attach_walkforward_race_strength(data: pd.DataFrame) -> pd.DataFrame:
    """Build strict prior-date opponent-strength and expectation residuals.

    Each completed race creates a performance observation from the field's
    pre-race official ratings and the horse's finish percentile. A later card
    can use only observations whose race date is strictly earlier.
    """
    output = data.copy()
    output["_finish_percentile"] = output.groupby(
        ["date", "meeting_name", "race_number"]
    )["finish_pos"].transform(
        lambda values: 1.0 - (
            pd.to_numeric(values, errors="coerce") - 1.0
        ) / max(len(values) - 1, 1)
    )
    output["_field_rating_mean"] = output.groupby(
        ["date", "meeting_name", "race_number"]
    )["card_rating"].transform("mean")
    output["_rating_percentile"] = output.groupby(
        ["date", "meeting_name", "race_number"]
    )["card_rating"].rank(pct=True, method="average")
    output["_completed_performance"] = (
        output["_field_rating_mean"]
        + 20.0 * (output["_finish_percentile"] - 0.5)
    )
    output["_completed_expectation_residual"] = (
        output["_finish_percentile"] - output["_rating_percentile"]
    )

    history: dict[str, list[tuple[str, float, float]]] = {}
    prior_performance = pd.Series(index=output.index, dtype=float)
    prior_residual = pd.Series(index=output.index, dtype=float)
    prior_samples = pd.Series(0, index=output.index, dtype=int)
    chronological = output.sort_values(
        ["date", "race_number", "horse_number"]
    )
    for idx, row in chronological.iterrows():
        key = str(row.get("horse_name") or "").strip()
        race_date = str(row.get("date") or "")
        prior = [
            item for item in history.get(key, []) if item[0] < race_date
        ][-4:]
        if prior:
            weights = [0.75 ** (len(prior) - 1 - pos) for pos in range(len(prior))]
            weight_sum = sum(weights)
            prior_performance.loc[idx] = sum(
                item[1] * weight for item, weight in zip(prior, weights)
            ) / weight_sum
            prior_residual.loc[idx] = sum(
                item[2] * weight for item, weight in zip(prior, weights)
            ) / weight_sum
            prior_samples.loc[idx] = len(prior)
        completed = row.get("_completed_performance")
        residual = row.get("_completed_expectation_residual")
        if key and not pd.isna(completed) and not pd.isna(residual):
            history.setdefault(key, []).append(
                (race_date, float(completed), float(residual))
            )

    output["_prior_race_strength_performance"] = prior_performance
    output["_prior_expectation_residual"] = prior_residual
    output["_prior_strength_samples"] = prior_samples
    for source, signal in (
        ("_prior_race_strength_performance", "race_strength_performance"),
        ("_prior_expectation_residual", "expectation_residual"),
    ):
        relative = pd.Series(index=output.index, dtype=float)
        for _, rows in output.groupby(["meeting_name", "race_number"]):
            percentile = rows[source].rank(pct=True, method="average")
            relative.loc[rows.index] = 45.0 + 30.0 * percentile
        reliability = prior_samples / (prior_samples + 2.0)
        output[f"_signal_{signal}"] = (
            60.0 + reliability * (relative - 60.0)
        ).where(prior_samples > 0)
    output["_signal_strength_residual_consensus"] = output[
        [
            "_signal_race_strength_performance",
            "_signal_expectation_residual",
        ]
    ].mean(axis=1, skipna=False)
    for signal in (
        "race_strength_performance",
        "expectation_residual",
        "strength_residual_consensus",
    ):
        output[f"_signal_{signal}_min2"] = output[
            f"_signal_{signal}"
        ].where(prior_samples >= 2)
    return output


def candidate_specs() -> dict[str, tuple[str, str, float, bool]]:
    output = {}
    for alpha in (0.025, 0.05, 0.075, 0.10):
        suffix = f"{alpha:.3f}".rstrip("0").rstrip(".")
        output[f"finish_time_to_sectional_{suffix}"] = (
            "sectional", "finish_time", alpha, False
        )
        output[f"speed_time_consensus_to_sectional_{suffix}"] = (
            "sectional", "speed_time_consensus", alpha, False
        )
    for alpha in (0.03, 0.05, 0.08, 0.10):
        suffix = f"{alpha:.2f}"
        output[f"cold_ceiling_to_stability_{suffix}"] = (
            "stability", "cold_ceiling", alpha, True
        )
        output[f"cold_ceiling_to_sectional_{suffix}"] = (
            "sectional", "cold_ceiling", alpha, True
        )
    # Explicit audit-only candidates: expected to fail if the richer class
    # weighting still has no standalone predictive value.
    for alpha in (0.03, 0.05):
        suffix = f"{alpha:.2f}"
        output[f"opponent_quality_to_formline_{suffix}"] = (
            "form_line", "opponent_quality", alpha, False
        )
    for alpha in (0.025, 0.05, 0.075, 0.10):
        suffix = f"{alpha:.3f}".rstrip("0").rstrip(".")
        output[f"race_strength_to_formline_{suffix}"] = (
            "form_line", "race_strength_performance", alpha, False
        )
        output[f"expectation_residual_to_formline_{suffix}"] = (
            "form_line", "expectation_residual", alpha, False
        )
        output[f"strength_residual_to_formline_{suffix}"] = (
            "form_line", "strength_residual_consensus", alpha, False
        )
    # Reliability variants are fixed a priori at >=2 completed prior races;
    # one run is too noisy to establish class-adjusted conversion ability.
    for alpha in (0.05, 0.075, 0.10):
        suffix = f"{alpha:.3f}".rstrip("0").rstrip(".")
        output[f"race_strength_min2_to_formline_{suffix}"] = (
            "form_line", "race_strength_performance_min2", alpha, False
        )
        output[f"expectation_residual_min2_to_formline_{suffix}"] = (
            "form_line", "expectation_residual_min2", alpha, False
        )
        output[f"strength_residual_min2_to_formline_{suffix}"] = (
            "form_line", "strength_residual_consensus_min2", alpha, False
        )
        output[f"race_strength_positive_to_formline_{suffix}"] = (
            "form_line", "race_strength_performance", alpha, True
        )
        output[f"expectation_residual_positive_to_formline_{suffix}"] = (
            "form_line", "expectation_residual", alpha, True
        )
        output[f"strength_residual_positive_to_formline_{suffix}"] = (
            "form_line", "strength_residual_consensus", alpha, True
        )
    return output


def score_race(
    rows: pd.DataFrame,
    candidate: tuple[str, str, float, bool] | None,
) -> list[dict]:
    ranked = []
    for record in rows.to_dict("records"):
        matrices = {
            name: float(record.get(f"matrix_{name}", 60.0) or 60.0)
            for name in MATRIX_WEIGHTS
        }
        horse = int(record["horse_number"])
        sectional = record.get("_signal_sectional")
        if sectional is not None and not pd.isna(sectional):
            matrices["sectional"] = (
                (1.0 - BASE_SECTIONAL_ALPHA) * matrices["sectional"]
                + BASE_SECTIONAL_ALPHA * sectional
            )
        if candidate is not None:
            dimension, signal_name, alpha, positive_only = candidate
            evidence = record.get(f"_signal_{signal_name}")
            if evidence is not None and not pd.isna(evidence):
                if positive_only:
                    matrices[dimension] += alpha * max(0.0, evidence - 60.0)
                else:
                    matrices[dimension] = (
                        (1.0 - alpha) * matrices[dimension] + alpha * evidence
                    )
        ability = sum(
            matrices[name] * weight for name, weight in MATRIX_WEIGHTS.items()
        )
        ranked.append({**record, "_ability": ability})
    return sorted(
        ranked,
        key=lambda row: (-row["_ability"], int(row["horse_number"])),
    )


def evaluate(
    groups: list[pd.DataFrame],
    candidate: tuple[str, str, float, bool] | None,
) -> tuple[dict, dict]:
    metrics_rows, details = [], {}
    for rows in groups:
        ranked = score_race(rows, candidate)
        picks = [int(row["horse_number"]) for row in ranked]
        positions = {
            int(row["horse_number"]): int(row["finish_pos"])
            for row in ranked
        }
        actual = [horse for horse, position in positions.items() if position <= 3]
        metric = race_metrics(
            picks, actual, actual_pos=positions, field_size=len(rows)
        )
        metrics_rows.append(metric)
        key = (ranked[0]["meeting_name"], int(ranked[0]["race_number"]))
        details[key] = {
            "top2_hits": metric["top2_hits"],
            "top2": picks[:2],
            "rank3": picks[2] if len(picks) >= 3 else None,
            "actual": actual,
        }
    summary = summarize_races(metrics_rows)
    distribution = Counter(row["top2_hits"] for row in metrics_rows)
    competitiveness = summary["competitiveness"]
    return {
        "races": len(metrics_rows),
        "zero_hit": distribution[0],
        "one_hit": distribution[1],
        "two_hit": distribution[2],
        "top2_total_hits": sum(row["top2_hits"] for row in metrics_rows),
        "top3_capture_at5": competitiveness["mean_top3_capture_at5"],
        "competitive_recall_at5": competitiveness["mean_competitive_recall_at5"],
        "ndcg_at5": competitiveness["mean_ndcg_at5"],
        "winner_in_top5": summary["rates"]["winner_in_top5"],
        "mrr": summary["mrr"],
    }, details


def _delta(candidate: dict, baseline: dict) -> dict:
    return {
        key: candidate[key] - baseline[key]
        for key in candidate if key != "races"
    }


def _passes(result: dict) -> bool:
    all_delta = result["all"]["delta"]
    holdout = result["temporal_holdout"]["delta"]
    adjusted = result["all_adjusted"]["delta"]
    weak = result["weak_zero_one"]["delta"]
    external = result["external"]["delta"]
    comparison = result["comparison"]
    no_regression = (
        all_delta["zero_hit"] <= 0
        and all_delta["top2_total_hits"] >= 0
        and all_delta["ndcg_at5"] >= -1e-12
        and holdout["top2_total_hits"] >= 0
        and holdout["ndcg_at5"] >= -1e-12
        and adjusted["ndcg_at5"] >= -1e-12
        and external["top2_total_hits"] >= 0
        and external["top3_capture_at5"] >= -1e-12
        and external["ndcg_at5"] >= -1e-12
        and external["winner_in_top5"] >= -1e-12
        and comparison["helped"] >= comparison["harmed"]
    )
    meaningful = (
        all_delta["top2_total_hits"] > 0
        or holdout["top2_total_hits"] > 0
        or weak["top2_total_hits"] > 0
        or all_delta["ndcg_at5"] >= 0.001
    )
    return bool(no_regression and meaningful)


def main() -> int:
    data = attach_signals(prepare())
    archive = data[data["dataset"].eq("archive")].copy()
    external = data[data["dataset"].eq("external")].copy()
    dates = sorted(archive["date"].astype(str).unique())
    cut = max(1, math.floor(len(dates) * 0.70))
    annotations = pd.read_csv(hq.ANNOTATIONS, encoding="utf-8-sig")
    abnormal = {
        (row.meeting, int(row.race_number))
        for row in annotations.itertuples()
        if any(bool(getattr(row, flag)) for flag in (
            "extreme_outsider", "major_incident", "interference", "injury", "abnormal"
        ))
    }

    def groups(frame: pd.DataFrame) -> list[pd.DataFrame]:
        return [
            rows.copy()
            for _, rows in frame.groupby(
                ["meeting_name", "race_number"], sort=True
            )
        ]

    split_frames = {
        "development": archive[archive["date"].astype(str).isin(dates[:cut])],
        "temporal_holdout": archive[archive["date"].astype(str).isin(dates[cut:])],
        "all": archive,
        "all_adjusted": archive[
            ~archive.apply(
                lambda row: (
                    row["meeting_name"], int(row["race_number"])
                ) in abnormal,
                axis=1,
            )
        ],
        "external": external,
    }
    split_groups = {name: groups(frame) for name, frame in split_frames.items()}
    baseline, baseline_details = {}, {}
    for split, race_groups in split_groups.items():
        baseline[split], baseline_details[split] = evaluate(race_groups, None)
    weak_keys = {
        key for key, item in baseline_details["all"].items()
        if item["top2_hits"] <= 1
    }
    split_groups["weak_zero_one"] = [
        rows for rows in split_groups["all"]
        if (
            rows.iloc[0]["meeting_name"], int(rows.iloc[0]["race_number"])
        ) in weak_keys
    ]
    baseline["weak_zero_one"], baseline_details["weak_zero_one"] = evaluate(
        split_groups["weak_zero_one"], None
    )

    results = {}
    for name, spec in candidate_specs().items():
        result, candidate_details = {}, {}
        for split, race_groups in split_groups.items():
            metrics, details = evaluate(race_groups, spec)
            result[split] = {
                "candidate": metrics,
                "delta": _delta(metrics, baseline[split]),
            }
            candidate_details[split] = details
        helped = harmed = rescues = 0
        for key, before in baseline_details["all"].items():
            after = candidate_details["all"][key]
            helped += after["top2_hits"] > before["top2_hits"]
            harmed += after["top2_hits"] < before["top2_hits"]
            rescues += (
                before["rank3"] in before["actual"]
                and before["rank3"] in after["top2"]
            )
        result["comparison"] = {
            "helped": helped,
            "harmed": harmed,
            "rank3_rescues": rescues,
        }
        result["pass"] = _passes(result)
        results[name] = result

    ranked = sorted(
        results,
        key=lambda name: (
            not results[name]["pass"],
            -results[name]["temporal_holdout"]["delta"]["top2_total_hits"],
            -results[name]["all_adjusted"]["delta"]["ndcg_at5"],
            -results[name]["all"]["delta"]["ndcg_at5"],
        ),
    )
    payload = {
        "method": {
            "production_baseline_sectional_blend": BASE_SECTIONAL_ALPHA,
            "full_field_rerank": True,
            "point_in_time_inputs_only": True,
            "micro_tiebreak_or_swap": False,
        },
        "coverage": {
            "archive_meetings": int(archive["meeting_name"].nunique()),
            "archive_races": int(archive.groupby(["meeting_name", "race_number"]).ngroups),
            "archive_runners": int(len(archive)),
            "external_races": int(external["race_number"].nunique()),
            "weak_zero_one_races": len(weak_keys),
            "finish_time_runners": int(archive["raw_finish_time_adj"].notna().sum()),
            "last_margin_runners": int(archive["raw_last_margin"].notna().sum()),
            "walkforward_strength_runners": int(
                archive["_signal_race_strength_performance"].notna().sum()
            ),
            "external_walkforward_strength_runners": int(
                external["_signal_race_strength_performance"].notna().sum()
            ),
        },
        "baseline": baseline,
        "results": results,
        "ranked_candidates": ranked,
        "passing_candidates": [name for name in ranked if results[name]["pass"]],
    }
    JSON_OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# HKJC Next Pre-Race Signal Gate",
        "",
        f"- Coverage: {payload['coverage']}",
        "- Baseline includes the promoted 5% exact class/course/distance normalized sectional blend.",
        "- Frozen pre-race inputs only; full-field matrix rerank; no odds, swaps, or micro tie-breaks.",
        f"- Passing candidates: {payload['passing_candidates'] or ['NONE']}",
        "",
        "| candidate | pass | all 0hit Δ | all top2 Δ | all NDCG Δ | holdout top2 Δ | holdout NDCG Δ | weak top2 Δ | external NDCG Δ | help/harm | R3 rescues |",
        "|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ranked:
        row = results[name]
        all_delta = row["all"]["delta"]
        holdout = row["temporal_holdout"]["delta"]
        weak = row["weak_zero_one"]["delta"]
        external_delta = row["external"]["delta"]
        comparison = row["comparison"]
        lines.append(
            f"| {name} | {'PASS' if row['pass'] else 'FAIL'} | "
            f"{all_delta['zero_hit']:+.0f} | {all_delta['top2_total_hits']:+.0f} | "
            f"{all_delta['ndcg_at5']:+.4f} | "
            f"{holdout['top2_total_hits']:+.0f} | {holdout['ndcg_at5']:+.4f} | "
            f"{weak['top2_total_hits']:+.0f} | {external_delta['ndcg_at5']:+.4f} | "
            f"{comparison['helped']}/{comparison['harmed']} | "
            f"{comparison['rank3_rescues']} |"
        )
    REPORT_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(REPORT_OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
