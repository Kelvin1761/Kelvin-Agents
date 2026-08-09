#!/usr/bin/env python3
"""Point-in-time gate for HKJC horse-specific successful rating intervals.

The experiment uses only official pre-race profile rows strictly earlier than
the card date.  It does not use odds, rank-boundary swaps, or result-informed
features.  Candidate evidence is blended into the full-field class-advantage
dimension and every runner is reranked.
"""

from __future__ import annotations

from collections import Counter
import importlib.util
import json
import math
import os
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "scratch" / "hkjc_ranking_dataset_current.csv"
EXTERNAL = ROOT / "scratch" / "hkjc_ranking_dataset_2026_07_15_current.csv"
PROFILE_CACHE = ROOT / "scratch" / "hkjc_local_position_profile_cache.json"
TRACKWORK_CACHE = ROOT / "scratch" / "hkjc_local_trackwork_quality_cache.json"
EXTERNAL_RATINGS = ROOT / "scratch" / "hkjc_0715_current_ratings.json"
JSON_OUT = ROOT / "scratch" / "hkjc_rating_interval_gate.json"
REPORT_OUT = ROOT / "scratch" / "hkjc_rating_interval_gate_report.md"
HQ_PATH = ROOT / "scratch" / "hkjc_high_quality_dimension_gate.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("hkjc_hq_gate", HQ_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


hq = _load_module()


def _weighted_mean(values: list[float], decay: float = 0.78) -> float | None:
    if not values:
        return None
    weights = [decay**index for index in range(len(values))]
    return sum(value * weight for value, weight in zip(values, weights)) / sum(weights)


def rating_interval_features(
    profile: dict,
    as_of: str,
    current_rating: float | None,
    current_bodyweight: float | None,
) -> dict[str, float | int | None]:
    if current_rating is None or pd.isna(current_rating):
        rating_missing = {
            "rating_history_samples": 0,
            "rating_success_samples": 0,
            "rating_win_samples": 0,
            "rating_success_headroom_raw": None,
            "rating_success_zone_raw": None,
            "rating_win_zone_raw": None,
            "rating_competitive_at_mark_raw": None,
        }
        rating_features = rating_missing
    else:
        entries = [
            entry
            for entry in profile.get("entries", [])
            if str(entry.get("date") or "") < as_of
            and isinstance(entry.get("rating"), int)
            and isinstance(entry.get("placing"), int)
        ]
        entries = sorted(entries, key=lambda entry: str(entry["date"]), reverse=True)[:12]
        successes = [entry for entry in entries if int(entry["placing"]) <= 3]
        wins = [entry for entry in entries if int(entry["placing"]) == 1]

        def zone_score(rows: list[dict]) -> float | None:
            if not rows:
                return None
            ratings = [float(entry["rating"]) for entry in rows]
            lower, upper = min(ratings), max(ratings)
            current = float(current_rating)
            distance = lower - current if current < lower else current - upper if current > upper else 0.0
            return max(0.0, 1.0 - distance / 12.0)

        at_mark = [
            entry for entry in entries
            if float(entry["rating"]) >= float(current_rating) - 2.0
        ]
        competitive_values = [
            1.0 if int(entry["placing"]) <= 3
            else 0.4 if int(entry["placing"]) <= 5 else 0.0
            for entry in at_mark
        ]
        rating_features = {
            "rating_history_samples": len(entries),
            "rating_success_samples": len(successes),
            "rating_win_samples": len(wins),
            "rating_at_mark_samples": len(at_mark),
            "rating_success_headroom_raw": (
                max(float(entry["rating"]) for entry in successes) - float(current_rating)
                if successes else None
            ),
            "rating_success_zone_raw": zone_score(successes),
            "rating_win_zone_raw": zone_score(wins),
            "rating_competitive_at_mark_raw": _weighted_mean(competitive_values),
        }

    weight_entries = [
        entry for entry in profile.get("entries", [])
        if str(entry.get("date") or "") < as_of
        and isinstance(entry.get("declared_weight"), int)
        and int(entry["declared_weight"]) > 0
    ]
    weight_entries = sorted(
        weight_entries, key=lambda entry: str(entry["date"]), reverse=True
    )[:12]
    successful_weights = [
        float(entry["declared_weight"])
        for entry in weight_entries
        if isinstance(entry.get("placing"), int) and int(entry["placing"]) <= 3
    ]
    recent_weights = [float(entry["declared_weight"]) for entry in weight_entries[:3]]
    if current_bodyweight is None or pd.isna(current_bodyweight):
        body_features = {
            "bodyweight_history_samples": 0,
            "bodyweight_success_samples": 0,
            "bodyweight_success_zone_raw": None,
            "bodyweight_recent_stability_raw": None,
        }
    else:
        current_weight = float(current_bodyweight)
        if successful_weights:
            lower, upper = min(successful_weights), max(successful_weights)
            zone_distance = (
                lower - current_weight if current_weight < lower
                else current_weight - upper if current_weight > upper else 0.0
            )
            zone_raw = max(0.0, 1.0 - zone_distance / 30.0)
        else:
            zone_raw = None
        recent_median = float(pd.Series(recent_weights).median()) if recent_weights else None
        body_features = {
            "bodyweight_history_samples": len(weight_entries),
            "bodyweight_success_samples": len(successful_weights),
            "bodyweight_success_zone_raw": zone_raw,
            "bodyweight_recent_stability_raw": (
                max(0.0, 1.0 - abs(current_weight - recent_median) / 30.0)
                if recent_median is not None else None
            ),
        }
    return {**rating_features, **body_features}


def prepare() -> pd.DataFrame:
    data = hq.prepare()
    archive = pd.read_csv(ARCHIVE)
    archive["dataset"] = "archive"
    external = pd.read_csv(EXTERNAL)
    external["dataset"] = "external"
    name_to_id = (
        archive.dropna(subset=["horse_id"])
        .drop_duplicates("horse_name")
        .set_index("horse_name")["horse_id"]
        .to_dict()
    )
    external["horse_id"] = external["horse_id"].where(
        external["horse_id"].notna(), external["horse_name"].map(name_to_id)
    )
    external_ratings = json.loads(EXTERNAL_RATINGS.read_text(encoding="utf-8"))["ratings"]
    external["card_rating"] = external.apply(
        lambda row: external_ratings.get(f"{int(row.race_number)}-{int(row.horse_number)}"),
        axis=1,
    )
    raw = pd.concat([archive, external], ignore_index=True)
    keys = ["dataset", "meeting_name", "race_number", "horse_number"]
    data = data.merge(
        raw[keys + ["horse_id", "card_rating", "card_declared_bodyweight"]],
        on=keys,
        how="left",
        validate="one_to_one",
    )
    profiles = json.loads(PROFILE_CACHE.read_text(encoding="utf-8")).get("profiles", {})
    features = []
    for row in data.itertuples():
        horse_id = str(row.horse_id or "").strip()
        profile = profiles.get(horse_id, {})
        current_bodyweight = row.card_declared_bodyweight
        if current_bodyweight is None or pd.isna(current_bodyweight):
            # The frozen 07-15 temporary Logic snapshot omitted the racecard
            # bodyweight.  The same-day official profile row repeats the
            # declared pre-race bodyweight; use that field only, never its
            # placing/rating/position result.
            same_day = next(
                (
                    entry for entry in profile.get("entries", [])
                    if str(entry.get("date") or "") == str(row.date)
                    and isinstance(entry.get("declared_weight"), int)
                ),
                None,
            )
            current_bodyweight = (
                same_day.get("declared_weight") if same_day else None
            )
        features.append(
            rating_interval_features(
                profile, str(row.date), row.card_rating, current_bodyweight
            )
        )
    data = pd.concat([data, pd.DataFrame(features, index=data.index)], axis=1)
    data = attach_trial_features(data)
    return attach_relative_signals(data)


def attach_trial_features(data: pd.DataFrame) -> pd.DataFrame:
    cache = json.loads(TRACKWORK_CACHE.read_text(encoding="utf-8")).get("horses", {})
    event_rows: dict[tuple, list[tuple[str, float | None, float | None]]] = {}
    parsed_by_horse: dict[str, list[dict]] = {}
    for brand, payload in cache.items():
        parsed = []
        for entry in payload.get("entries", []):
            if entry.get("type") != "trial":
                continue
            details = str(entry.get("details") or "")
            group_match = re.search(r"第(\d+)組", details)
            distance_match = re.search(r"(\d{3,4})M", details, re.I)
            if not (group_match and distance_match):
                continue
            sections = [float(value) for value in entry.get("sectionals", [])]
            final_time = entry.get("final_time")
            final_time = float(final_time) if isinstance(final_time, (int, float)) else None
            last_section = sections[-1] if sections else None
            key = (
                str(entry.get("date") or ""), str(entry.get("location") or ""),
                int(group_match.group(1)), int(distance_match.group(1)),
            )
            item = {"date": key[0], "event": key, "final": final_time, "last": last_section}
            parsed.append(item)
            event_rows.setdefault(key, []).append((brand, final_time, last_section))
        parsed_by_horse[brand] = parsed

    event_quality: dict[tuple[tuple, str], tuple[float, int]] = {}
    for key, rows in event_rows.items():
        for index in (1, 2):
            values = [(row[0], row[index]) for row in rows if row[index] is not None]
            if len(values) < 2:
                continue
            ordered = sorted(value for _, value in values)
            for brand, value in values:
                better = sum(other > value for other in ordered)
                ties = sum(other == value for other in ordered) - 1
                percentile = (better + 0.5 * ties) / max(1, len(ordered) - 1)
                old = event_quality.get((key, brand))
                if old:
                    event_quality[(key, brand)] = ((old[0] + percentile) / 2.0, len(values))
                else:
                    event_quality[(key, brand)] = (percentile, len(values))

    trial_features = []
    for row in data.itertuples():
        as_of = pd.Timestamp(str(row.date))
        values = []
        for entry in parsed_by_horse.get(str(row.horse_id or ""), []):
            days = (as_of - pd.Timestamp(entry["date"])).days
            quality = event_quality.get((entry["event"], str(row.horse_id or "")))
            if 0 < days <= 60 and quality:
                values.append((days, quality[0], quality[1]))
        values.sort(key=lambda item: item[0])
        if values:
            recency_weights = [math.exp(-days / 30.0) for days, _, _ in values[:2]]
            raw_quality = sum(
                quality * weight for (_, quality, _), weight in zip(values[:2], recency_weights)
            ) / sum(recency_weights)
            trial_features.append({
                "trial_quality_raw": raw_quality,
                "trial_quality_samples": len(values[:2]),
                "trial_event_cohort": max(value[2] for value in values[:2]),
                "trial_recency_raw": max(0.0, 1.0 - values[0][0] / 60.0),
            })
        else:
            trial_features.append({
                "trial_quality_raw": None, "trial_quality_samples": 0,
                "trial_event_cohort": 0, "trial_recency_raw": None,
            })
    return pd.concat([data, pd.DataFrame(trial_features, index=data.index)], axis=1)


def attach_relative_signals(data: pd.DataFrame) -> pd.DataFrame:
    output = data.copy()
    configs = {
        "success_headroom": ("rating_success_headroom_raw", "rating_success_samples"),
        "success_zone": ("rating_success_zone_raw", "rating_success_samples"),
        "win_zone": ("rating_win_zone_raw", "rating_win_samples"),
        "competitive_at_mark": (
            "rating_competitive_at_mark_raw", "rating_at_mark_samples"
        ),
        "bodyweight_success_zone": (
            "bodyweight_success_zone_raw", "bodyweight_success_samples"
        ),
        "bodyweight_recent_stability": (
            "bodyweight_recent_stability_raw", "bodyweight_history_samples"
        ),
        "trial_quality": ("trial_quality_raw", "trial_event_cohort"),
        "trial_recency": ("trial_recency_raw", "trial_quality_samples"),
    }
    for signal in configs:
        output[f"_signal_{signal}"] = math.nan
    for _, rows in output.groupby(["meeting_name", "race_number"], sort=False):
        for signal, (column, samples_column) in configs.items():
            values = pd.to_numeric(rows[column], errors="coerce")
            samples = pd.to_numeric(rows[samples_column], errors="coerce").fillna(0.0)
            relative = values.rank(pct=True, method="average")
            evidence = 45.0 + 30.0 * relative
            reliability = samples / (samples + 3.0)
            shrunk = 60.0 + reliability * (evidence - 60.0)
            output.loc[rows.index, f"_signal_{signal}"] = shrunk.where(values.notna())
    success_samples = pd.to_numeric(
        output["rating_success_samples"], errors="coerce"
    ).fillna(0.0)
    base_zone = output["_signal_success_zone"]
    output["_signal_success_zone_min2"] = base_zone.where(success_samples >= 2)
    output["_signal_success_zone_min3"] = base_zone.where(success_samples >= 3)
    output["_signal_success_zone_uplift_min2"] = base_zone.where(success_samples >= 2)
    output["_signal_success_zone_asymmetric"] = base_zone.where(success_samples >= 2)
    output["_signal_trial_quality_uplift"] = output["_signal_trial_quality"]
    return output


def specs() -> dict[str, tuple[str, float, str]]:
    output = {}
    for signal in (
        "success_headroom", "success_zone", "win_zone", "competitive_at_mark"
    ):
        for alpha in (0.025, 0.05, 0.075, 0.10, 0.15):
            suffix = f"{alpha:.3f}".rstrip("0").rstrip(".")
            output[f"rating_{signal}_{suffix}"] = (signal, alpha, "class_advantage")
    for signal in (
        "success_zone_min2",
        "success_zone_min3",
        "success_zone_uplift_min2",
        "success_zone_asymmetric",
    ):
        for alpha in (0.05, 0.075, 0.10, 0.125, 0.15):
            suffix = f"{alpha:.3f}".rstrip("0").rstrip(".")
            output[f"rating_{signal}_{suffix}"] = (signal, alpha, "class_advantage")
    for signal in ("bodyweight_success_zone", "bodyweight_recent_stability"):
        for alpha in (0.025, 0.05, 0.075, 0.10, 0.15, 0.25, 0.50, 1.00):
            suffix = f"{alpha:.3f}".rstrip("0").rstrip(".")
            output[f"{signal}_{suffix}"] = (signal, alpha, "horse_health")
        for alpha in (0.025, 0.05, 0.075, 0.10, 0.15, 0.20):
            suffix = f"{alpha:.3f}".rstrip("0").rstrip(".")
            output[f"{signal}_to_stability_{suffix}"] = (
                signal, alpha, "stability"
            )
    for signal in ("trial_quality", "trial_quality_uplift", "trial_recency"):
        for alpha in (0.025, 0.05, 0.075, 0.10, 0.15, 0.20):
            suffix = f"{alpha:.3f}".rstrip("0").rstrip(".")
            output[f"{signal}_to_stability_{suffix}"] = (
                signal, alpha, "stability"
            )
    return output


def score_race(rows: pd.DataFrame, spec: tuple[str, float, str] | None) -> list[dict]:
    ranked = []
    for record in rows.to_dict("records"):
        matrices = {
            name: float(record.get(f"matrix_{name}", 60.0) or 60.0)
            for name in hq.MATRIX_WEIGHTS
        }
        if spec:
            signal, alpha, dimension = spec
            evidence = record.get(f"_signal_{signal}")
            if evidence is not None and not pd.isna(evidence):
                evidence = float(evidence)
                current = matrices[dimension]
                success_samples = int(record.get("rating_success_samples", 0) or 0)
                allowed = True
                if signal == "success_zone_uplift_min2":
                    allowed = evidence > current
                elif signal == "trial_quality_uplift":
                    allowed = evidence > current
                elif signal == "success_zone_asymmetric":
                    allowed = evidence >= current or success_samples >= 3
                if allowed:
                    matrices[dimension] = (
                        (1.0 - alpha) * current + alpha * evidence
                    )
        ability = sum(
            matrices[name] * weight for name, weight in hq.MATRIX_WEIGHTS.items()
        )
        ranked.append({**record, "_ability": ability})
    return sorted(ranked, key=lambda row: (-row["_ability"], int(row["horse_number"])))


def evaluate(groups: list[pd.DataFrame], spec) -> tuple[dict, dict]:
    metrics, details = [], {}
    for rows in groups:
        ranked = score_race(rows, spec)
        picks = [int(row["horse_number"]) for row in ranked]
        positions = {int(row["horse_number"]): int(row["finish_pos"]) for row in ranked}
        actual = [horse for horse, position in positions.items() if position <= 3]
        metric = hq.race_metrics(picks, actual, actual_pos=positions, field_size=len(rows))
        metrics.append(metric)
        key = (ranked[0]["meeting_name"], int(ranked[0]["race_number"]))
        details[key] = {
            "top2_hits": metric["top2_hits"],
            "top2": picks[:2],
            "rank3": picks[2] if len(picks) >= 3 else None,
            "actual": actual,
        }
    summary = hq.summarize_races(metrics)
    distribution = Counter(row["top2_hits"] for row in metrics)
    comp = summary["competitiveness"]
    return {
        "races": len(metrics),
        "zero_hit": distribution[0],
        "one_hit": distribution[1],
        "two_hit": distribution[2],
        "top2_total_hits": sum(row["top2_hits"] for row in metrics),
        "top3_capture_at5": comp["mean_top3_capture_at5"],
        "competitive_recall_at5": comp["mean_competitive_recall_at5"],
        "ndcg_at5": comp["mean_ndcg_at5"],
        "winner_in_top5": summary["rates"]["winner_in_top5"],
        "mrr": summary["mrr"],
    }, details


def _delta(candidate: dict, baseline: dict) -> dict:
    return {key: candidate[key] - baseline[key] for key in candidate if key != "races"}


def run_gate(data: pd.DataFrame, candidate_specs=None) -> dict:
    archive = data[data.dataset.eq("archive")].copy()
    external = data[data.dataset.eq("external")].copy()
    dates = sorted(archive.date.astype(str).unique())
    cut = max(1, math.floor(len(dates) * 0.70))
    annotations = pd.read_csv(hq.ANNOTATIONS, encoding="utf-8-sig")
    abnormal = {
        (row.meeting, int(row.race_number))
        for row in annotations.itertuples()
        if any(bool(getattr(row, flag)) for flag in (
            "extreme_outsider", "major_incident", "interference", "injury", "abnormal"
        ))
    }

    def groups(frame):
        return [rows.copy() for _, rows in frame.groupby(
            ["meeting_name", "race_number"], sort=True
        )]

    frames = {
        "development": archive[archive.date.astype(str).isin(dates[:cut])],
        "temporal_holdout": archive[archive.date.astype(str).isin(dates[cut:])],
        "all": archive,
        "all_adjusted": archive[~archive.apply(
            lambda row: (row.meeting_name, int(row.race_number)) in abnormal, axis=1
        )],
        "external": external,
    }
    split_groups = {name: groups(frame) for name, frame in frames.items()}
    baseline, baseline_details = {}, {}
    for split, race_groups in split_groups.items():
        baseline[split], baseline_details[split] = evaluate(race_groups, None)
    weak_keys = {
        key for key, detail in baseline_details["all"].items()
        if detail["top2_hits"] <= 1
    }
    split_groups["weak_zero_one"] = [
        rows for rows in split_groups["all"]
        if (rows.iloc[0].meeting_name, int(rows.iloc[0].race_number)) in weak_keys
    ]
    baseline["weak_zero_one"], baseline_details["weak_zero_one"] = evaluate(
        split_groups["weak_zero_one"], None
    )

    results, gates = {}, {}
    for name, spec in (candidate_specs or specs()).items():
        result, candidate_details = {}, {}
        for split, race_groups in split_groups.items():
            metrics, details = evaluate(race_groups, spec)
            result[split] = {"candidate": metrics, "delta": _delta(metrics, baseline[split])}
            candidate_details[split] = details
        helped = harmed = rescues = 0
        for key, before in baseline_details["all"].items():
            after = candidate_details["all"][key]
            helped += after["top2_hits"] > before["top2_hits"]
            harmed += after["top2_hits"] < before["top2_hits"]
            rescues += before["rank3"] in before["actual"] and before["rank3"] in after["top2"]
        result["comparison"] = {
            "helped": helped, "harmed": harmed, "rank3_rescues": rescues
        }
        results[name] = result
        hold = result["temporal_holdout"]["delta"]
        adjusted = result["all_adjusted"]["delta"]
        external_delta = result["external"]["delta"]
        comp = result["comparison"]
        single_success_unconfirmed = (
            name.startswith("rating_success_zone_")
            and not any(marker in name for marker in ("_min2_", "_min3_", "_asymmetric_", "_uplift_"))
        )
        gates[name] = bool(
            hold["top2_total_hits"] >= 0
            and hold["ndcg_at5"] >= -0.0005
            and adjusted["ndcg_at5"] > 0.0
            and result["all"]["delta"]["zero_hit"] <= 0
            and result["weak_zero_one"]["delta"]["top2_total_hits"] > 0
            and external_delta["top2_total_hits"] >= 0
            and external_delta["ndcg_at5"] >= -0.001
            and comp["helped"] > comp["harmed"]
            and comp["rank3_rescues"] > 0
            and not single_success_unconfirmed
        )
    ranked = sorted(results, key=lambda name: (
        -results[name]["temporal_holdout"]["delta"]["top2_total_hits"],
        -results[name]["all_adjusted"]["delta"]["ndcg_at5"],
        -results[name]["weak_zero_one"]["delta"]["top2_total_hits"],
    ))
    passing = [name for name in ranked if gates[name]]
    return {
        "method": {
            "source": "HKJC local horse profile successful rating intervals",
            "point_in_time": "entries strictly earlier than card date",
            "odds": False,
            "full_field_rerank": True,
        },
        "coverage": {
            "archive_meetings": int(archive.meeting_name.nunique()),
            "archive_races": int(archive.groupby(["meeting_name", "race_number"]).ngroups),
            "archive_runners": len(archive),
            "archive_rating_history": int(archive.rating_history_samples.gt(0).sum()),
            "archive_success_zone": int(archive.rating_success_samples.gt(0).sum()),
            "external_races": int(external.race_number.nunique()),
            "external_success_zone": int(external.rating_success_samples.gt(0).sum()),
            "weak_zero_one_races": len(weak_keys),
        },
        "baseline": baseline,
        "results": results,
        "ranked_candidates": ranked,
        "gates": gates,
        "passing_candidates": passing,
        "recommendation": passing[0] if passing else "HOLD_ALL",
    }


def write_report(payload: dict, report_out: Path = REPORT_OUT) -> None:
    lines = [
        "# HKJC Rating-Interval Gate", "",
        f"- Coverage: {payload['coverage']}",
        "- Official local profile rows strictly earlier than each card date; no odds, swaps, or micro tie-breaks.",
        f"- Passing candidates: {payload['passing_candidates'] or ['NONE']}", "",
        "| candidate | pass | all 0hit Δ | all top2 Δ | all NDCG Δ | holdout top2 Δ | holdout NDCG Δ | weak top2 Δ | external top2 Δ | external NDCG Δ | help/harm | R3 rescues |",
        "|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in payload["ranked_candidates"]:
        result = payload["results"][name]
        comp = result["comparison"]
        lines.append(
            f"| {name} | {'PASS' if payload['gates'][name] else 'FAIL'} "
            f"| {result['all']['delta']['zero_hit']:+d} "
            f"| {result['all']['delta']['top2_total_hits']:+d} "
            f"| {result['all']['delta']['ndcg_at5']:+.4f} "
            f"| {result['temporal_holdout']['delta']['top2_total_hits']:+d} "
            f"| {result['temporal_holdout']['delta']['ndcg_at5']:+.4f} "
            f"| {result['weak_zero_one']['delta']['top2_total_hits']:+d} "
            f"| {result['external']['delta']['top2_total_hits']:+d} "
            f"| {result['external']['delta']['ndcg_at5']:+.4f} "
            f"| {comp['helped']}/{comp['harmed']} | {comp['rank3_rescues']} |"
        )
    report_out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    candidate_specs = specs()
    family = os.environ.get("HKJC_GATE_FAMILY", "all")
    if family == "bodyweight":
        candidate_specs = {
            name: spec for name, spec in candidate_specs.items()
            if "bodyweight" in name
        }
    elif family == "trial":
        candidate_specs = {
            name: spec for name, spec in candidate_specs.items()
            if name.startswith("trial_")
        }
    elif family == "rating":
        candidate_specs = {
            name: spec for name, spec in candidate_specs.items()
            if name.startswith("rating_success_zone")
        }
    payload = run_gate(prepare(), candidate_specs)
    if family == "all":
        json_out, report_out = JSON_OUT, REPORT_OUT
    else:
        json_out = ROOT / "scratch" / f"hkjc_{family}_quality_gate.json"
        report_out = ROOT / "scratch" / f"hkjc_{family}_quality_gate_report.md"
    json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(payload, report_out)
    print(report_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
