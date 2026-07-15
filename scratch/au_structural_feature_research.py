#!/usr/bin/env python3
"""Market-free structural ranking research for AU Wong Choi.

This harness is shadow-only. It joins the deterministic scoring archive to
pre-race Logic data, creates structural candidate dimensions, evaluates them
with chronological folds, and preserves the final 20% as a combination holdout.
It never mutates Logic files or the production scoring engine.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from statistics import mean, median

import numpy as np
from sklearn.linear_model import LogisticRegression


ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "scratch"
ENGINE = ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.extend([str(SCRATCH), str(ENGINE), str(ENGINE / "racing_engine")])

from au_ranking_structural_review import (  # noqa: E402
    bootstrap_delta,
    exact_mcnemar,
    field_bucket,
    load_or_build,
    race_values,
)
from scoring import FEATURE_KEYS, MATRIX_WEIGHTS  # noqa: E402


ARCHIVE = ROOT / "Wong Choi Horse Race Analysis/AU_Racing"
REPORT = ARCHIVE / "AU_Structural_Feature_Research_2026-07-13.md"
JSON_REPORT = ARCHIVE / "AU_Structural_Feature_Research_2026-07-13.json"
ALPHAS = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0)
PAIRWISE_CS = (0.03, 0.1, 0.3, 1.0)
RAW_CANDIDATES = (
    "performance_efficiency",
    "performance_efficiency_guarded",
    "preparation_readiness",
    "rolling_trainer",
    "rolling_connections",
    "formline_rebuild",
)
ALL_CANDIDATES = RAW_CANDIDATES + (
    "shape_interaction",
    "pairwise_7d_recombine",
    "ordinal_pairwise_7d",
)


def as_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clean_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def clip(value: float, low: float = -3.0, high: float = 3.0) -> float:
    return min(high, max(low, value))


def zmap(values: list[float | None]) -> list[float]:
    available = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if len(available) < 3:
        return [0.0] * len(values)
    centre = median(available)
    deviations = [abs(value - centre) for value in available]
    mad = median(deviations)
    scale = 1.4826 * mad
    if scale < 1e-8:
        avg = mean(available)
        scale = math.sqrt(mean((value - avg) ** 2 for value in available))
        centre = avg
    if scale < 1e-8:
        return [0.0] * len(values)
    return [0.0 if value is None else clip((float(value) - centre) / scale) for value in values]


def avg_present(values: list[float | None], default: float = 0.0) -> float:
    present = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return mean(present) if present else default


def parse_consumption(value: str) -> float | None:
    match = re.search(r"([0-9.]+)\s*/\s*5(?:\.0)?", str(value or ""))
    return as_float(match.group(1)) if match else None


def parse_formline_ratio(value: str) -> float | None:
    match = re.search(r"強組比例:\s*([0-9.]+)\s*/\s*([0-9.]+)", str(value or ""))
    if not match:
        return None
    numerator, denominator = as_float(match.group(1), 0.0), as_float(match.group(2), 0.0)
    return numerator / denominator if denominator else None


def parse_stage_place_rate(value: str) -> float | None:
    records = re.findall(r"(?:^|\|)[^:|]*:?\s*(\d+)\s*:\s*(\d+)-(\d+)-(\d+)", str(value or ""))
    if not records:
        records = re.findall(r"(\d+)\s*:\s*(\d+)-(\d+)-(\d+)", str(value or ""))
    rates = []
    for starts, wins, seconds, thirds in records:
        n = int(starts)
        if n:
            rates.append((int(wins) + int(seconds) + int(thirds) + 1.5) / (n + 5.0))
    return mean(rates) if rates else None


def pace_bucket(value: str) -> str:
    text = str(value or "").lower()
    if any(token in text for token in ("快", "fast", "strong", "高")):
        return "fast"
    if any(token in text for token in ("慢", "slow", "soft", "低")):
        return "slow"
    return "normal"


def horse_style(speed_map: dict, number: int) -> str:
    for source, label in (
        ("leaders", "leader"),
        ("pressers", "presser"),
        ("on_pace", "on_pace"),
        ("mid_pack", "mid"),
        ("closers", "closer"),
    ):
        if number in {int(item) for item in speed_map.get(source, []) if str(item).isdigit()}:
            return label
    return "unknown"


def trend_value(value: str) -> float:
    text = str(value or "").lower()
    if "improv" in text or "上升" in text:
        return 1.0
    if "sharp_declining" in text or "急跌" in text:
        return -1.5
    if "declin" in text or "下降" in text:
        return -1.0
    return 0.0


def logic_for_race(race: dict) -> dict:
    path = ARCHIVE / race["meeting"] / f"Race_{race['race']}_Logic.json"
    return json.loads(path.read_text(encoding="utf-8"))


def join_logic(races: list[dict]) -> dict[str, int]:
    coverage = Counter()
    for race in races:
        logic = logic_for_race(race)
        analysis = logic.get("race_analysis") or {}
        race["race_class"] = str(analysis.get("race_class") or "Unknown")
        speed_map = analysis.get("speed_map") or {}
        race["pace_bucket"] = pace_bucket(speed_map.get("predicted_pace") or speed_map.get("expected_pace"))
        by_number = {int(key): value for key, value in (logic.get("horses") or {}).items() if str(key).isdigit()}
        by_name = {clean_name(value.get("horse_name")): value for value in by_number.values()}
        for horse in race["horses"]:
            source = by_number.get(int(horse["horse_number"])) or by_name.get(clean_name(horse["horse_name"])) or {}
            data = source.get("_data") or {}
            horse["trainer"] = str(source.get("trainer") or "")
            horse["jockey"] = str(source.get("jockey") or "")
            horse["style"] = horse_style(speed_map, int(horse["horse_number"]))
            horse["raw"] = data
            horse["research"] = {}
            horse["scores"] = {"baseline": float(horse["ability"])}
            if data.get("pf_metrics"):
                coverage["pf_metrics"] += 1
            if parse_consumption(data.get("consumption_summary")) is not None:
                coverage["consumption"] += 1
            if data.get("trainer_ly"):
                coverage["trainer_ly"] += 1
            if data.get("recent_shape_consensus"):
                coverage["shape"] += 1
            if parse_formline_ratio(data.get("formline_line")) is not None:
                coverage["formline_ratio"] += 1
    coverage["runners"] = sum(len(race["horses"]) for race in races)
    return dict(coverage)


def performance_components(horse: dict) -> dict[str, float | None]:
    data = horse["raw"]
    aggregates = ((data.get("pf_metrics") or {}).get("pf_aggregates") or {})
    return {
        "race_avg": -as_float(aggregates.get("race_time_diff_avg")) if as_float(aggregates.get("race_time_diff_avg")) is not None else None,
        "race_best": -as_float(aggregates.get("race_time_diff_best")) if as_float(aggregates.get("race_time_diff_best")) is not None else None,
        "l600_avg": -as_float(aggregates.get("l600_delta_avg")) if as_float(aggregates.get("l600_delta_avg")) is not None else None,
        "l600_best": -as_float(aggregates.get("l600_delta_best")) if as_float(aggregates.get("l600_delta_best")) is not None else None,
        "speed_recent": as_float(data.get("timing_600m_recent_speed")),
        "speed_avg": as_float(data.get("timing_600m_avg_speed")),
    }


def build_static_dimensions(races: list[dict]) -> None:
    component_names = ("race_avg", "race_best", "l600_avg", "l600_best", "speed_recent", "speed_avg")
    for race in races:
        components = [performance_components(horse) for horse in race["horses"]]
        performance_coverage = sum(any(value is not None for value in row.values()) for row in components) / max(1, len(components))
        race["performance_coverage"] = performance_coverage
        z_components = {
            key: zmap([row[key] for row in components])
            for key in component_names
        }
        consumption_z = zmap([
            -parse_consumption(horse["raw"].get("consumption_summary"))
            if parse_consumption(horse["raw"].get("consumption_summary")) is not None
            else None
            for horse in race["horses"]
        ])
        stage_z = zmap([parse_stage_place_rate(horse["raw"].get("stage_stats_line")) for horse in race["horses"]])
        health_z = zmap([horse["features"].get("health_score") for horse in race["horses"]])
        formline_ratio_z = zmap([parse_formline_ratio(horse["raw"].get("formline_line")) for horse in race["horses"]])
        formline_score_z = zmap([horse["features"].get("formline_score") for horse in race["horses"]])
        class_z = zmap([horse["features"].get("class_score") for horse in race["horses"]])
        rating_z = zmap([horse["features"].get("rating_score") for horse in race["horses"]])

        matrix_z = {
            key: zmap([horse["matrices"].get(key) for horse in race["horses"]])
            for key in MATRIX_WEIGHTS
        }
        for idx, horse in enumerate(race["horses"]):
            count = as_float(((horse["raw"].get("pf_metrics") or {}).get("pf_aggregates") or {}).get("pf_run_count"), 0.0)
            reliability = min(1.0, math.sqrt(max(0.0, count) / 3.0))
            perf_parts = [z_components[key][idx] for key in component_names if components[idx][key] is not None]
            performance_value = avg_present(perf_parts) * reliability
            horse["research"]["performance_efficiency"] = performance_value
            horse["research"]["performance_efficiency_guarded"] = performance_value if performance_coverage >= 0.60 else 0.0

            trend = trend_value(horse["raw"].get("timing_600m_trend"))
            horse["research"]["preparation_readiness"] = (
                0.45 * consumption_z[idx]
                + 0.25 * stage_z[idx]
                + 0.20 * trend
                + 0.10 * health_z[idx]
            )

            formal_count = as_float(horse["raw"].get("formal_count"), 0.0)
            shrink = min(1.0, max(0.0, formal_count) / 5.0)
            base_formline = 0.65 * formline_ratio_z[idx] + 0.35 * formline_score_z[idx]
            class_support = 0.55 * class_z[idx] + 0.45 * rating_z[idx]
            horse["research"]["formline_rebuild"] = shrink * base_formline + 0.20 * shrink * base_formline * clip(class_support)
            horse["x7"] = np.array([matrix_z[key][idx] for key in MATRIX_WEIGHTS], dtype=float)


def build_rolling_dimensions(races: list[dict]) -> None:
    trainer_stats: dict[str, Counter] = defaultdict(Counter)
    jockey_stats: dict[str, Counter] = defaultdict(Counter)

    def entity_value(stats: Counter) -> float:
        starts = stats["starts"]
        win_rate = (stats["wins"] + 3.0) / (starts + 30.0)
        place_rate = (stats["places"] + 9.0) / (starts + 30.0)
        return 0.40 * ((win_rate - 0.10) / 0.05) + 0.60 * ((place_rate - 0.30) / 0.10)

    for race in races:
        trainer_raw, jockey_raw = [], []
        for horse in race["horses"]:
            trainer_raw.append(entity_value(trainer_stats[clean_name(horse["trainer"])]))
            jockey_raw.append(entity_value(jockey_stats[clean_name(horse["jockey"])]))
        trainer_z, jockey_z = zmap(trainer_raw), zmap(jockey_raw)
        for idx, horse in enumerate(race["horses"]):
            horse["research"]["rolling_trainer"] = trainer_z[idx]
            horse["research"]["rolling_connections"] = 0.60 * trainer_z[idx] + 0.40 * jockey_z[idx]
        for horse in race["horses"]:
            outcome = {"starts": 1, "wins": int(horse["actual_pos"] == 1), "places": int(horse["actual_pos"] <= 3)}
            trainer_stats[clean_name(horse["trainer"])].update(outcome)
            jockey_stats[clean_name(horse["jockey"])].update(outcome)


def ranked(race: dict, score_key: str) -> list[dict]:
    return sorted(race["horses"], key=lambda horse: (-horse["scores"][score_key], horse["horse_number"]))


def evaluate(races: list[dict], score_key: str) -> tuple[dict, list[dict]]:
    values = [race_values(ranked(race, score_key)) for race in races]
    keys = values[0].keys() if values else ()
    return ({key: mean(row[key] for row in values) for key in keys} | {"races": len(values)}), values


def objective(metrics: dict) -> float:
    return (
        4.0 * metrics["top2_place_strike"]
        + 3.0 * metrics["top4_trifecta"]
        + 1.0 * metrics["top2_both_place"]
        + 1.0 * metrics["top1_win"]
        + 0.5 * metrics["winner_mrr"]
    )


def assign_raw_scores(races: list[dict], candidate: str, alpha: float, output_key: str) -> None:
    for race in races:
        raw_z = zmap([horse["research"].get(candidate) for horse in race["horses"]])
        for horse, value in zip(race["horses"], raw_z):
            horse["scores"][output_key] = horse["ability"] + alpha * value


def choose_alpha_raw(train: list[dict], candidate: str) -> float:
    split = max(1, int(len(train) * 0.80))
    validation = train[split:]
    base, _ = evaluate(validation, "baseline")
    best = (objective(base), 0.0)
    for alpha in ALPHAS[1:]:
        key = f"_tune_{candidate}_{alpha}"
        assign_raw_scores(validation, candidate, alpha, key)
        metrics, _ = evaluate(validation, key)
        if metrics["top1_win"] < base["top1_win"] - 0.02 or metrics["top4_trifecta"] < base["top4_trifecta"] - 0.01:
            continue
        value = objective(metrics)
        if value > best[0] + 1e-12:
            best = (value, alpha)
    return best[1]


def fit_shape_table(races: list[dict]) -> tuple[float, dict[tuple[str, str], float]]:
    total, places = 0, 0
    stats: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for race in races:
        for horse in race["horses"]:
            key = (race["pace_bucket"], horse["style"])
            stats[key]["starts"] += 1
            stats[key]["places"] += int(horse["actual_pos"] <= 3)
            total += 1
            places += int(horse["actual_pos"] <= 3)
    base = places / total if total else 0.30
    table = {}
    for key, counts in stats.items():
        rate = (counts["places"] + 40.0 * base) / (counts["starts"] + 40.0)
        rate = min(0.999, max(0.001, rate))
        table[key] = math.log(rate / (1.0 - rate)) - math.log(base / (1.0 - base))
    return base, table


def assign_shape_scores(races: list[dict], table: dict, alpha: float, output_key: str) -> None:
    for race in races:
        values = [table.get((race["pace_bucket"], horse["style"]), 0.0) for horse in race["horses"]]
        values = zmap(values)
        for horse, value in zip(race["horses"], values):
            horse["scores"][output_key] = horse["ability"] + alpha * value


def choose_shape(train: list[dict]) -> tuple[float, dict]:
    split = max(1, int(len(train) * 0.80))
    core, validation = train[:split], train[split:]
    _, table = fit_shape_table(core)
    base, _ = evaluate(validation, "baseline")
    best = (objective(base), 0.0)
    for alpha in ALPHAS[1:]:
        key = f"_shape_{alpha}"
        assign_shape_scores(validation, table, alpha, key)
        metrics, _ = evaluate(validation, key)
        if metrics["top1_win"] < base["top1_win"] - 0.02 or metrics["top4_trifecta"] < base["top4_trifecta"] - 0.01:
            continue
        if objective(metrics) > best[0] + 1e-12:
            best = (objective(metrics), alpha)
    _, full_table = fit_shape_table(train)
    return best[1], full_table


def pairwise_rows(races: list[dict], ordinal: bool = False) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xs, ys, weights = [], [], []
    for race in races:
        positives = [horse for horse in race["horses"] if horse["actual_pos"] <= 3]
        negatives = [horse for horse in race["horses"] if horse["actual_pos"] > 3]
        weighted_pairs = []
        if ordinal:
            winners = [horse for horse in race["horses"] if horse["actual_pos"] == 1]
            for winner in winners:
                for other in race["horses"]:
                    if other is not winner:
                        weighted_pairs.append((winner, other, 2.0))
            for positive in positives:
                if positive["actual_pos"] == 1:
                    continue
                for negative in negatives:
                    weighted_pairs.append((positive, negative, 1.0))
        else:
            for positive in positives:
                for negative in negatives:
                    weighted_pairs.append((positive, negative, 1.0))
        total_weight = sum(weight for _, _, weight in weighted_pairs) or 1.0
        for positive, negative, pair_weight in weighted_pairs:
            diff = positive["x7"] - negative["x7"]
            xs.extend((diff, -diff))
            ys.extend((1, 0))
            normalized = pair_weight / total_weight
            weights.extend((normalized, normalized))
    return np.asarray(xs), np.asarray(ys), np.asarray(weights)


def fit_pairwise(races: list[dict], c_value: float, ordinal: bool = False) -> LogisticRegression:
    x, y, weights = pairwise_rows(races, ordinal=ordinal)
    model = LogisticRegression(C=c_value, fit_intercept=False, solver="liblinear", max_iter=1000, random_state=20260713)
    model.fit(x, y, sample_weight=weights)
    return model


def assign_pairwise_scores(races: list[dict], model: LogisticRegression, alpha: float, output_key: str) -> None:
    weights = model.coef_[0]
    for race in races:
        values = zmap([float(np.dot(horse["x7"], weights)) for horse in race["horses"]])
        for horse, value in zip(race["horses"], values):
            horse["scores"][output_key] = horse["ability"] + alpha * value


def choose_pairwise(train: list[dict], ordinal: bool = False) -> tuple[float, float, LogisticRegression]:
    split = max(1, int(len(train) * 0.80))
    core, validation = train[:split], train[split:]
    base, _ = evaluate(validation, "baseline")
    best = (objective(base), 0.0, PAIRWISE_CS[0])
    for c_value in PAIRWISE_CS:
        model = fit_pairwise(core, c_value, ordinal=ordinal)
        for alpha in ALPHAS[1:]:
            key = f"_pair_{c_value}_{alpha}"
            assign_pairwise_scores(validation, model, alpha, key)
            metrics, _ = evaluate(validation, key)
            if metrics["top1_win"] < base["top1_win"] - 0.02 or metrics["top4_trifecta"] < base["top4_trifecta"] - 0.01:
                continue
            if objective(metrics) > best[0] + 1e-12:
                best = (objective(metrics), alpha, c_value)
    full_model = fit_pairwise(train, best[2], ordinal=ordinal)
    return best[1], best[2], full_model


def run_candidate_folds(races: list[dict]) -> tuple[list[dict], dict]:
    n = len(races)
    starts = [int(n * fraction) for fraction in (0.40, 0.50, 0.60, 0.70)]
    ends = [int(n * fraction) for fraction in (0.50, 0.60, 0.70, 0.80)]
    fold_details = defaultdict(list)
    dev_races = races[starts[0]:ends[-1]]
    for candidate in ALL_CANDIDATES:
        for fold_no, (start, end) in enumerate(zip(starts, ends), 1):
            train, test = races[:start], races[start:end]
            output_key = candidate
            extra = {}
            if candidate in RAW_CANDIDATES:
                alpha = choose_alpha_raw(train, candidate)
                assign_raw_scores(test, candidate, alpha, output_key)
            elif candidate == "shape_interaction":
                alpha, table = choose_shape(train)
                assign_shape_scores(test, table, alpha, output_key)
            else:
                ordinal = candidate == "ordinal_pairwise_7d"
                alpha, c_value, model = choose_pairwise(train, ordinal=ordinal)
                assign_pairwise_scores(test, model, alpha, output_key)
                extra["C"] = c_value
                extra["weights"] = dict(zip(MATRIX_WEIGHTS, (float(value) for value in model.coef_[0])))
            metrics, _ = evaluate(test, output_key)
            base, _ = evaluate(test, "baseline")
            fold_details[candidate].append({
                "fold": fold_no,
                "train_races": len(train),
                "test_races": len(test),
                "alpha": alpha,
                "top1_delta": metrics["top1_win"] - base["top1_win"],
                "top2_delta": metrics["top2_place_strike"] - base["top2_place_strike"],
                "top4_delta": metrics["top4_trifecta"] - base["top4_trifecta"],
                **extra,
            })
    return dev_races, dict(fold_details)


def candidate_summary(dev_races: list[dict], fold_details: dict) -> dict:
    base_metrics, base_values = evaluate(dev_races, "baseline")
    output = {"baseline": base_metrics, "candidates": {}}
    for candidate in ALL_CANDIDATES:
        metrics, values = evaluate(dev_races, candidate)
        top2_ci = bootstrap_delta(base_values, values, "top2_place_strike")
        top4_ci = bootstrap_delta(base_values, values, "top4_trifecta")
        details = fold_details[candidate]
        output["candidates"][candidate] = {
            "metrics": metrics,
            "deltas": {key: metrics[key] - base_metrics[key] for key in metrics if key != "races"},
            "top2_ci": top2_ci,
            "top4_ci": top4_ci,
            "top1_p": exact_mcnemar(base_values, values, "top1_win"),
            "top4_p": exact_mcnemar(base_values, values, "top4_trifecta"),
            "top2_positive_folds": sum(item["top2_delta"] > 0 for item in details),
            "top4_nonnegative_folds": sum(item["top4_delta"] >= 0 for item in details),
            "folds": details,
        }
    return output


def development_gate(summary: dict) -> list[str]:
    passed = []
    for candidate, row in summary["candidates"].items():
        delta = row["deltas"]
        if (
            delta["top2_place_strike"] > 0
            and delta["top4_trifecta"] >= 0
            and delta["top1_win"] >= -0.005
            and row["top2_positive_folds"] >= 3
            and row["top4_nonnegative_folds"] >= 3
        ):
            passed.append(candidate)
    return passed


def fit_candidate_for_holdout(train: list[dict], holdout: list[dict], candidate: str) -> dict:
    if candidate in RAW_CANDIDATES:
        alpha = choose_alpha_raw(train, candidate)
        assign_raw_scores(holdout, candidate, alpha, f"_hold_{candidate}")
        return {"alpha": alpha}
    if candidate == "shape_interaction":
        alpha, table = choose_shape(train)
        assign_shape_scores(holdout, table, alpha, f"_hold_{candidate}")
        return {"alpha": alpha}
    ordinal = candidate == "ordinal_pairwise_7d"
    alpha, c_value, model = choose_pairwise(train, ordinal=ordinal)
    assign_pairwise_scores(holdout, model, alpha, f"_hold_{candidate}")
    return {"alpha": alpha, "C": c_value, "weights": dict(zip(MATRIX_WEIGHTS, (float(value) for value in model.coef_[0])))}


def final_combination(races: list[dict], selected: list[str]) -> dict:
    split = int(len(races) * 0.80)
    train, holdout = races[:split], races[split:]
    fit_details = {candidate: fit_candidate_for_holdout(train, holdout, candidate) for candidate in ALL_CANDIDATES}
    individual = {}
    base, base_values = evaluate(holdout, "baseline")
    for candidate in ALL_CANDIDATES:
        metrics, values = evaluate(holdout, f"_hold_{candidate}")
        individual[candidate] = {
            "metrics": metrics,
            "deltas": {key: metrics[key] - base[key] for key in metrics if key != "races"},
            "top2_ci": bootstrap_delta(base_values, values, "top2_place_strike"),
            "top4_ci": bootstrap_delta(base_values, values, "top4_trifecta"),
        }
    combo_key = "final_combined"
    for race in holdout:
        for horse in race["horses"]:
            change = sum(horse["scores"][f"_hold_{candidate}"] - horse["ability"] for candidate in selected)
            horse["scores"][combo_key] = horse["ability"] + change
    metrics, values = evaluate(holdout, combo_key)
    return {
        "selected": selected,
        "fit": fit_details,
        "individual": individual,
        "baseline": base,
        "metrics": metrics,
        "deltas": {key: metrics[key] - base[key] for key in metrics if key != "races"},
        "top2_ci": bootstrap_delta(base_values, values, "top2_place_strike"),
        "top4_ci": bootstrap_delta(base_values, values, "top4_trifecta"),
        "top1_p": exact_mcnemar(base_values, values, "top1_win"),
        "top4_p": exact_mcnemar(base_values, values, "top4_trifecta"),
        "races": holdout,
    }


def candidate_family(candidate: str) -> str:
    family = {
        "pairwise_7d_recombine": "pairwise",
        "ordinal_pairwise_7d": "pairwise",
        "performance_efficiency": "performance",
        "performance_efficiency_guarded": "performance",
        "rolling_trainer": "connections",
        "rolling_connections": "connections",
    }
    return family.get(candidate, candidate)


def choose_combination(summary: dict, dev_races: list[dict]) -> tuple[list[str], str, dict]:
    passed = development_gate(summary)
    if passed:
        ranked_candidates = sorted(
            passed,
            key=lambda name: (
                summary["candidates"][name]["deltas"]["top2_place_strike"],
                summary["candidates"][name]["deltas"]["top4_trifecta"],
            ),
            reverse=True,
        )
        selected = ranked_candidates[:3]
    else:
        selected = []

    base, base_values = evaluate(dev_races, "baseline")
    pair_rows = []
    for first, second in combinations(ALL_CANDIDATES, 2):
        if candidate_family(first) == candidate_family(second):
            continue
        key = f"_dev_combo_{first}_{second}"
        for race in dev_races:
            for horse in race["horses"]:
                horse["scores"][key] = (
                    horse["ability"]
                    + horse["scores"][first] - horse["ability"]
                    + horse["scores"][second] - horse["ability"]
                )
        metrics, _ = evaluate(dev_races, key)
        deltas = {name: metrics[name] - base[name] for name in metrics if name != "races"}
        offset = 0
        top2_positive, top4_nonnegative = 0, 0
        for fold in summary["candidates"][first]["folds"]:
            chunk = dev_races[offset:offset + fold["test_races"]]
            offset += fold["test_races"]
            chunk_base, _ = evaluate(chunk, "baseline")
            chunk_metrics, _ = evaluate(chunk, key)
            top2_positive += chunk_metrics["top2_place_strike"] > chunk_base["top2_place_strike"]
            top4_nonnegative += chunk_metrics["top4_trifecta"] >= chunk_base["top4_trifecta"]
        passed_gate = (
            deltas["top2_place_strike"] > 0
            and deltas["top4_trifecta"] >= 0
            and deltas["top1_win"] >= -0.005
            and top2_positive >= 3
            and top4_nonnegative >= 3
        )
        balanced = 4.0 * deltas["top2_place_strike"] + 3.0 * deltas["top4_trifecta"] + deltas["top1_win"]
        pair_rows.append({
            "selected": [first, second],
            "score_key": key,
            "metrics": metrics,
            "deltas": deltas,
            "top2_positive_folds": top2_positive,
            "top4_nonnegative_folds": top4_nonnegative,
            "passed_gate": passed_gate,
            "balanced_objective": balanced,
        })

    eligible_pairs = [row for row in pair_rows if row["passed_gate"]]
    pool = eligible_pairs or pair_rows
    best_pair = max(
        pool,
        key=lambda row: (
            row["balanced_objective"],
            row["deltas"]["top4_trifecta"],
            row["deltas"]["top1_win"],
        ),
    )
    _, best_values = evaluate(dev_races, best_pair["score_key"])
    best_pair["top2_ci"] = bootstrap_delta(base_values, best_values, "top2_place_strike")
    best_pair["top4_ci"] = bootstrap_delta(base_values, best_values, "top4_trifecta")
    best_pair.pop("score_key", None)
    if eligible_pairs:
        reason = "development combination gate passed; duplicated candidate families were excluded"
    else:
        reason = "exploratory fallback from the development pair screen; no pair passed the strict Top1/Top2/Top4 fold gate"
    return best_pair["selected"], reason, best_pair


def segment_deltas(races: list[dict], score_key: str) -> list[dict]:
    output = []
    for field in ("condition", "distance", "field", "track", "race_class"):
        grouped = defaultdict(list)
        for race in races:
            value = field_bucket(len(race["horses"])) if field == "field" else race.get(field, "Unknown")
            grouped[str(value)].append(race)
        for label, rows in grouped.items():
            if len(rows) < 12:
                continue
            base, _ = evaluate(rows, "baseline")
            metrics, _ = evaluate(rows, score_key)
            output.append({
                "field": field,
                "segment": label,
                "races": len(rows),
                "top1_delta": metrics["top1_win"] - base["top1_win"],
                "top2_delta": metrics["top2_place_strike"] - base["top2_place_strike"],
                "top4_delta": metrics["top4_trifecta"] - base["top4_trifecta"],
            })
    return output


def performance_sensitivity(races: list[dict]) -> dict:
    """Exploratory fixed-weight screen over the post-pf_metrics regime."""
    start = int(len(races) * 0.70)
    rows = races[start:]
    base, base_values = evaluate(rows, "baseline")
    tests = []
    for alpha in (1.0, 1.25, 1.5):
        key = f"_performance_sensitivity_{alpha}"
        assign_raw_scores(rows, "performance_efficiency", alpha, key)
        metrics, values = evaluate(rows, key)
        tests.append({
            "alpha": alpha,
            "deltas": {name: metrics[name] - base[name] for name in metrics if name != "races"},
            "top2_ci": bootstrap_delta(base_values, values, "top2_place_strike"),
            "top4_ci": bootstrap_delta(base_values, values, "top4_trifecta"),
        })
    return {
        "races": len(rows),
        "date_from": rows[0]["date"],
        "date_to": rows[-1]["date"],
        "tests": tests,
    }


def pct(value: float) -> str:
    return f"{100 * value:.2f}%"


def pp(value: float) -> str:
    return f"{100 * value:+.2f}pp"


def render(payload: dict) -> str:
    summary = payload["development"]
    base = summary["baseline"]
    combo = payload["holdout_combination"]
    labels = {
        "performance_efficiency": "標準化時間／步速效率維度",
        "performance_efficiency_guarded": "有完整度閘嘅時間／步速效率維度",
        "preparation_readiness": "備戰負荷／體能維度",
        "rolling_trainer": "無洩漏 rolling trainer 維度",
        "rolling_connections": "無洩漏 trainer+jockey 維度",
        "formline_rebuild": "重建 form-line 維度",
        "shape_interaction": "賽事步速×跑法互動矩陣",
        "pairwise_7d_recombine": "pairwise 7D 組合器",
        "ordinal_pairwise_7d": "ordinal pairwise 7D 組合器",
    }
    lines = [
        "# AU Wong Choi 結構性特徵研究（Top2 / Top4）",
        "",
        "## 實驗控制",
        "",
        f"- 完整 archive：**{payload['races']} 場 / {payload['runners']} 匹馬**。",
        f"- 候選 development blind folds：**{base['races']} 場**；最終未觸碰 holdout：**{combo['baseline']['races']} 場**。",
        "- 全部 scoring inputs 都係 pre-race form、時間、步速、跑法、騎練及賽事條件；程式無讀取 odds、SP、favourite rank、market movement 或 market ranking。",
        "- 所有改動均係單一 pre-ranking score / supporting matrix，無 post-score 人手換位或 micro-rerank。",
        "- rolling connection 只使用該場之前已發生嘅 archive 賽果；pairwise 權重只用較早日期訓練。",
        "",
        "## Development baseline（連續時間盲測）",
        "",
        "| KPI | Baseline |",
        "|---|---:|",
        f"| Top1 頭馬命中 | {pct(base['top1_win'])} |",
        f"| Top1 入位率 | {pct(base['top1_place'])} |",
        f"| Top2 每選入位率 | {pct(base['top2_place_strike'])} |",
        f"| Top2 兩匹俱入位 | {pct(base['top2_both_place'])} |",
        f"| Top4 包三重彩 | {pct(base['top4_trifecta'])} |",
        f"| Top5 包三重彩 | {pct(base['top5_trifecta'])} |",
        f"| Winner MRR | {pct(base['winner_mrr'])} |",
        "",
        "## 每項獨立結構測試",
        "",
        "| 候選 | Top1 Δ | Top2 Δ | Top2 95% CI | Top4 Δ | Top4 95% CI | Top2 正向 folds | Top4 無倒退 folds | 結論 |",
        "|---|---:|---:|---|---:|---|---:|---:|---|",
    ]
    passed = set(development_gate(summary))
    for candidate in ALL_CANDIDATES:
        row = summary["candidates"][candidate]
        delta = row["deltas"]
        conclusion = "通過 development gate" if candidate in passed else "未通過"
        lines.append(
            f"| {labels[candidate]} | {pp(delta['top1_win'])} | {pp(delta['top2_place_strike'])} "
            f"| [{pp(row['top2_ci'][0])}, {pp(row['top2_ci'][1])}] | {pp(delta['top4_trifecta'])} "
            f"| [{pp(row['top4_ci'][0])}, {pp(row['top4_ci'][1])}] | {row['top2_positive_folds']}/4 "
            f"| {row['top4_nonnegative_folds']}/4 | {conclusion} |"
        )

    lines.extend([
        "",
        "## 最終 holdout：每項候選獨立表現（組合選擇後先揭盅）",
        "",
        "| 候選 | Top1 Δ | Top2 Δ | Top2 95% CI | Top4 Δ |",
        "|---|---:|---:|---|---:|",
    ])
    for candidate in ALL_CANDIDATES:
        row = combo["individual"][candidate]
        delta = row["deltas"]
        lines.append(
            f"| {labels[candidate]} | {pp(delta['top1_win'])} | {pp(delta['top2_place_strike'])} "
            f"| [{pp(row['top2_ci'][0])}, {pp(row['top2_ci'][1])}] | {pp(delta['top4_trifecta'])} |"
        )

    lines.extend([
        "",
        "## Performance figure 固定權重 sensitivity（exploratory）",
        "",
        f"以下只涵蓋 `pf_metrics` 已穩定供應嘅近期 regime（{payload['performance_sensitivity']['date_from']} 至 {payload['performance_sensitivity']['date_to']}，{payload['performance_sensitivity']['races']} 場）；權重比較已睇過結果，所以唔當 blind holdout。",
        "",
        "| Supporting weight | Top1 Δ | Top2 Δ | Top2 95% CI | Top4 Δ |",
        "|---:|---:|---:|---|---:|",
    ])
    for row in payload["performance_sensitivity"]["tests"]:
        lines.append(
            f"| {row['alpha']:.2f} | {pp(row['deltas']['top1_win'])} | {pp(row['deltas']['top2_place_strike'])} "
            f"| [{pp(row['top2_ci'][0])}, {pp(row['top2_ci'][1])}] | {pp(row['deltas']['top4_trifecta'])} |"
        )
    lines.extend([
        "",
        "解讀：performance figure 對 Top1 / Top2 有重複正向訊號，但三個固定權重都令 Top4 輕微倒退；因此只保留做 frozen shadow candidate，唔可以單獨升級。",
    ])

    lines.extend([
        "",
        "## 最終組合 holdout",
        "",
        f"- 候選選擇規則：{payload['combination_reason']}。",
        f"- 組合：{', '.join(labels[name] for name in combo['selected']) if combo['selected'] else '維持 baseline'}。",
        f"- Development 組合差異：Top1 {pp(payload['development_combination']['deltas']['top1_win'])}、Top2 {pp(payload['development_combination']['deltas']['top2_place_strike'])}、Top4 {pp(payload['development_combination']['deltas']['top4_trifecta'])}；Top2 正向 folds {payload['development_combination']['top2_positive_folds']}/4，Top4 無倒退 folds {payload['development_combination']['top4_nonnegative_folds']}/4。",
        "",
        "| KPI | Holdout baseline | 組合後 | 差異 |",
        "|---|---:|---:|---:|",
    ])
    for key, label in (
        ("top1_win", "Top1 頭馬命中"),
        ("top1_place", "Top1 入位率"),
        ("top2_place_strike", "Top2 每選入位率"),
        ("top2_both_place", "Top2 兩匹俱入位"),
        ("top4_trifecta", "Top4 包三重彩"),
        ("top5_trifecta", "Top5 包三重彩"),
        ("winner_mrr", "Winner MRR"),
    ):
        lines.append(f"| {label} | {pct(combo['baseline'][key])} | {pct(combo['metrics'][key])} | {pp(combo['deltas'][key])} |")
    lines.extend([
        "",
        f"- Top2 差異 95% bootstrap CI：[{pp(combo['top2_ci'][0])}, {pp(combo['top2_ci'][1])}]。",
        f"- Top4 差異 95% bootstrap CI：[{pp(combo['top4_ci'][0])}, {pp(combo['top4_ci'][1])}]；McNemar p={combo['top4_p']:.3f}。",
        "",
        "## Holdout 分群影響",
        "",
        "| 分群欄位 | 分群 | 場數 | Top1 Δ | Top2 Δ | Top4 Δ |",
        "|---|---|---:|---:|---:|---:|",
    ])
    for row in payload["holdout_segments"]:
        lines.append(
            f"| {row['field']} | {row['segment']} | {row['races']} | {pp(row['top1_delta'])} | {pp(row['top2_delta'])} | {pp(row['top4_delta'])} |"
        )

    lines.extend([
        "",
        "## 升級判決",
        "",
        payload["decision"],
        "",
        "### 建議下一個 forward gate",
        "",
        "- 凍結兩個 shadow 候選，唔再調參：`performance_efficiency`（weight 1.25）同 `pairwise_7d_recombine + shape_interaction`。",
        "- 收集之後至少 150 場、跨 3 個以上主要場地嘅新賽果。",
        "- 只有當 Top1 不低於 baseline、Top2 至少 +2pp 且 95% CI 不跨零、Top4 不低於 baseline，以及最少 3/4 時間 blocks 無倒退，先提交 production approval。",
        "",
        "## Design Pattern Proposal",
        "",
        "- **Issue ID:** REF-20260713-STRUCT-01",
        "- **分類:** 🔵系統性",
        "- **問題描述:** 現役 clean 7D 對 Top5 coverage 尚可，但未直接用時間標準化、準備負荷與 leakage-safe connection form 去優化 Top2 / Top4 排序。",
        "- **受影響嘅 Protocol:** 基礎 7D scoring + archive validation gate",
        "- **建議修改:** 只考慮通過連續時間 development folds 及最終 holdout 嘅 supporting dimension；否則保留現役 matrix。",
        "- **預期效果:** 以實際 holdout 差異為準，唔以單一 Sunshine Coast meeting 外推。",
        "- **SIP-DA01 評價:** 部分有效 — 單 meeting 揭示 Top2/Top4 優先級，但升級裁決必須由跨場地時間盲測決定。",
        "",
    ])
    return "\n".join(lines)


def serializable_payload(payload: dict) -> dict:
    clean = dict(payload)
    combo = dict(clean["holdout_combination"])
    combo.pop("races", None)
    clean["holdout_combination"] = combo
    return clean


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=REPORT)
    parser.add_argument("--json-output", type=Path, default=JSON_REPORT)
    args = parser.parse_args()

    races, skipped = load_or_build(False, 2.0)
    if skipped:
        raise SystemExit(f"Archive still has {len(skipped)} skipped scoring files; rebuild the cache first")
    coverage = join_logic(races)
    build_static_dimensions(races)
    build_rolling_dimensions(races)
    dev_races, fold_details = run_candidate_folds(races)
    summary = candidate_summary(dev_races, fold_details)
    selected, reason, development_combo = choose_combination(summary, dev_races)
    combo = final_combination(races, selected)
    segments = segment_deltas(combo["races"], "final_combined")
    sensitivity = performance_sensitivity(races)

    production_pass = (
        development_combo["passed_gate"]
        and
        combo["deltas"]["top2_place_strike"] > 0
        and combo["deltas"]["top4_trifecta"] >= 0
        and combo["deltas"]["top1_win"] >= 0
        and combo["top2_ci"][0] >= 0
    )
    decision = (
        "**建議進入 production approval 階段，但仍未實施。** 最終 holdout 同時改善 Top1、Top2、Top4，而 Top2 95% CI 無跨零。"
        if production_pass
        else "**暫時唔建議修改 production 7D。** 候選未同時通過 Top1、Top2、Top4 及統計穩定性要求；保留研究結果，等新增 meeting 再做 forward validation。"
    )
    payload = {
        "races": len(races),
        "runners": sum(len(race["horses"]) for race in races),
        "coverage": coverage,
        "development": summary,
        "selected": selected,
        "combination_reason": reason,
        "development_combination": development_combo,
        "holdout_combination": combo,
        "holdout_segments": segments,
        "performance_sensitivity": sensitivity,
        "production_pass": production_pass,
        "decision": decision,
    }
    args.output.write_text(render(payload), encoding="utf-8")
    args.json_output.write_text(json.dumps(serializable_payload(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"races={len(races)} runners={payload['runners']} dev={summary['baseline']['races']} holdout={combo['baseline']['races']}")
    print(f"selected={selected} production_pass={production_pass}")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
