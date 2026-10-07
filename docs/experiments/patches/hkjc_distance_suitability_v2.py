#!/usr/bin/env python3
"""Evaluate a residual, surface-specific HKJC distance-suitability signal.

The deployed same-distance adjustment rewards any same-distance placing.  That
confounds distance aptitude with general horse ability: a good horse that runs
well at every trip receives the same reward as a genuine route specialist.

V2 estimates the within-horse residual instead:

    target-distance posterior - same-surface all-distance posterior

Both posteriors are strictly point-in-time, recency weighted and shrunk toward
neutral.  Happy Valley turf, Sha Tin turf and Sha Tin AWT are fitted separately.
No odds, result from the target race, or later history is used as a feature.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


REPO = Path(os.environ.get("HKJC_EXPERIMENT_REPO", Path(__file__).resolve().parents[3])).resolve()
PATCHES = Path(__file__).resolve().parent
FACTS = REPO / ".agents/scripts"
for path in (PATCHES, FACTS):
    sys.path.insert(0, str(path))

import hkjc_distance_component_ab as base  # noqa: E402
import hkjc_hierarchical_refit as metrics  # noqa: E402
import inject_hkjc_fact_anchors as facts  # noqa: E402


WEIGHTS = (0.02, 0.04, 0.06, 0.08)
CAPS = (4.0, 6.0, 8.0, 10.0)
VARIANTS = ("exact_blend", "kernel_place", "kernel_margin", "kernel_blend")
PRIOR_RUNS = 4.0
HALF_LIFE_DAYS = 365.0
MAX_AGE_DAYS = 1095
TEMPERATURE = 6.0
PRIMARY_KEYS = ("gold", "good")
RANKING_KEYS = ("top3_capture_at5", "competitive_recall_at5", "ndcg5")


def _surface_key(value: object) -> str:
    normalized = facts.normalize_venue_surface(value)
    if normalized == "跑馬地":
        return "HV_TURF"
    if normalized == "沙田AWT":
        return "ST_AWT"
    if normalized == "沙田":
        return "ST_TURF"
    return ""


def _history(block: str) -> list[dict[str, Any]]:
    """Parse only the two local history tables rendered in a horse block."""
    rows: list[dict[str, Any]] = []
    seen_dates: set[str] = set()
    in_local_table = False
    for line in block.splitlines():
        if "完整賽績檔案" in line or "較舊歷史賽績" in line:
            in_local_table = True
            continue
        if in_local_table and (line.startswith("🌍") or line.startswith("📊") or line.startswith("💡")):
            in_local_table = False
        if not in_local_table or not line.startswith("|"):
            continue
        columns = [part.strip() for part in line.split("|")]
        if len(columns) < 11 or not columns[1].isdigit():
            continue
        dt = facts.parse_date(columns[2])
        if dt is None:
            continue
        date_key = dt.date().isoformat()
        if date_key in seen_dates:
            continue
        try:
            distance = int(columns[4])
            finish = int(columns[9])
        except (TypeError, ValueError):
            continue
        surface = _surface_key(columns[3])
        if not surface or distance <= 0 or finish <= 0:
            continue
        margin = facts.parse_margin(columns[10])
        rows.append({
            "date": date_key,
            "date_dt": dt,
            "surface": surface,
            "distance": distance,
            "finish": finish,
            "margin": margin,
        })
        seen_dates.add(date_key)
    rows.sort(key=lambda row: row["date_dt"], reverse=True)
    return rows


def _place_utility(finish: int) -> float:
    # Coarse on purpose: older profile rows have no reliable field size.
    ladder = {1: 1.0, 2: 0.78, 3: 0.64, 4: 0.50, 5: 0.40, 6: 0.32,
              7: 0.25, 8: 0.18, 9: 0.12}
    return ladder.get(int(finish), 0.08)


def _margin_utility(finish: int, margin: float | None) -> float | None:
    if margin is None:
        return None
    signed = -abs(float(margin)) if int(finish) == 1 else abs(float(margin))
    return 1.0 / (1.0 + math.exp(max(-20.0, min(20.0, signed / 2.5))))


def _utility(row: dict[str, Any], variant: str) -> float:
    place = _place_utility(int(row["finish"]))
    margin = _margin_utility(int(row["finish"]), row.get("margin"))
    if variant == "kernel_place":
        return place
    if variant == "kernel_margin":
        return margin if margin is not None else 0.5
    if margin is None:
        return place
    return 0.65 * place + 0.35 * margin


def _distance_kernel(delta: int, variant: str) -> float:
    if delta == 0:
        return 1.0
    if variant == "exact_blend":
        return 0.0
    if delta <= 100:
        return 0.50
    if delta <= 200:
        return 0.25
    return 0.0


def _feature_score(rows: list[dict[str, Any]], anchor: datetime, surface: str,
                   target_distance: int, variant: str) -> dict[str, Any]:
    target_sum = 0.0
    target_n = 0.0
    surface_sum = 0.0
    surface_n = 0.0
    raw_target = 0
    raw_surface = 0
    future_rows = 0
    for row in rows:
        dt = row["date_dt"]
        if dt >= anchor:
            future_rows += 1
            continue
        if row["surface"] != surface:
            continue
        age = (anchor - dt).days
        if age <= 0 or age > MAX_AGE_DAYS:
            continue
        recency = 2.0 ** (-age / HALF_LIFE_DAYS)
        utility = _utility(row, variant)
        surface_sum += recency * utility
        surface_n += recency
        raw_surface += 1
        kernel = _distance_kernel(abs(int(row["distance"]) - target_distance), variant)
        if kernel > 0:
            weight = recency * kernel
            target_sum += weight * utility
            target_n += weight
            raw_target += 1

    target_post = (target_sum + 0.5 * PRIOR_RUNS) / (target_n + PRIOR_RUNS)
    surface_post = (surface_sum + 0.5 * PRIOR_RUNS) / (surface_n + PRIOR_RUNS)
    # Missing target-distance evidence is neutral.  Penalising a horse merely
    # because it has other-distance history would turn absence into evidence.
    residual = 0.0 if target_n <= 0 else target_post - surface_post
    score = max(40.0, min(80.0, 60.0 + 40.0 * residual))
    return {
        "score": round(score, 6),
        "residual": round(residual, 8),
        "target_effective_n": round(target_n, 6),
        "surface_effective_n": round(surface_n, 6),
        "target_runs": raw_target,
        "surface_runs": raw_surface,
        "future_or_same_day_rows": future_rows,
    }


def _attach_features(races: list[dict[str, Any]], meeting_root: Path) -> dict[str, Any]:
    audit: Counter[str] = Counter()
    folder_map = {path.name: path for path in meeting_root.glob("20??-??-??_*") if path.is_dir()}
    for race in races:
        folder_name, race_text = race["race_key"].rsplit("::", 1)
        folder = folder_map.get(folder_name)
        if folder is None:
            continue
        race_no = int(race_text)
        facts_path = base.history_ab._facts_path(folder, race_no)
        logic_path = folder / f"Race_{race_no}_Logic.json"
        if facts_path is None or not logic_path.exists():
            continue
        logic = json.loads(logic_path.read_text(encoding="utf-8"))
        context = logic.get("race_analysis") or {}
        target_distance = base.history_ab._integer(context.get("distance"))
        anchor = datetime.strptime(race["date"], "%Y-%m-%d")
        blocks = base.history_ab._horse_blocks(facts_path.read_text(encoding="utf-8"))
        for runner in race["runners"]:
            rows = _history(blocks.get(int(runner["horse_number"]), ""))
            runner["distance_v2"] = {}
            for variant in VARIANTS:
                feature = _feature_score(rows, anchor, runner["surface"], target_distance, variant)
                runner["distance_v2"][variant] = feature
                audit["future_or_same_day_rows"] += int(feature["future_or_same_day_rows"])
            if rows:
                audit["horses_with_history"] += 1
            if runner["distance_v2"]["kernel_blend"]["target_effective_n"] > 0:
                audit[f"{runner['surface']}_horses_with_target_evidence"] += 1
    # The same future-row count is repeated once per variant above.
    audit["future_or_same_day_rows"] //= len(VARIANTS)
    return dict(audit)


def _candidate_score(runner: dict[str, Any], profile: dict[str, dict[str, Any]]) -> float:
    params = profile[runner["surface"]]
    feature = runner["distance_v2"][params["variant"]]
    component = 60.0 + max(-float(params["cap"]), min(float(params["cap"]), float(feature["score"]) - 60.0))
    weight = float(params["weight"])
    return (1.0 - weight) * float(runner["no_class_raw"]) + weight * component


def _race_output(race: dict[str, Any], profile: dict[str, dict[str, Any]]) -> dict[str, Any]:
    baseline_scores = {row["horse_number"]: row["current_raw"] for row in race["runners"]}
    candidate_scores = {row["horse_number"]: _candidate_score(row, profile) for row in race["runners"]}
    return {
        "race_key": race["race_key"], "date": race["date"], "surface": race["surface"],
        "field_size": race["field_size"], "actual_pos": race["actual_pos"],
        "models": {
            "current_live": base._record(baseline_scores, race["actual_pos"]),
            "distance_v2": base._record(candidate_scores, race["actual_pos"]),
        },
    }


def _report(records: list[dict[str, Any]]) -> dict[str, Any]:
    candidate = [metrics._flags(row["models"]["distance_v2"], row["actual_pos"]) for row in records]
    baseline = [metrics._flags(row["models"]["current_live"], row["actual_pos"]) for row in records]
    return {
        "baseline": metrics._summarize(baseline),
        "candidate": metrics._summarize(candidate),
        "paired": metrics._paired(candidate, baseline),
    }


def _surface_reports(records: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[row["surface"]].append(row)
    return {key: _report(value) for key, value in sorted(grouped.items())}


def _pairwise_loss(races: list[dict[str, Any]], profile: dict[str, dict[str, Any]]) -> float:
    losses: list[float] = []
    weights: list[float] = []
    for race in races:
        scores = {row["horse_number"]: _candidate_score(row, profile) for row in race["runners"]}
        actual = race["actual_pos"]
        for horse_i, pos_i in actual.items():
            if pos_i > 3:
                continue
            for horse_j, pos_j in actual.items():
                if pos_j <= pos_i:
                    continue
                pair_weight = 1.0 if pos_i == 1 else (0.6 if pos_i == 2 else 0.35)
                if pos_j >= 8:
                    pair_weight *= 1.1
                margin = (scores[horse_i] - scores[horse_j]) / TEMPERATURE
                losses.append(float(np.logaddexp(0.0, -margin)))
                weights.append(pair_weight)
    return float(np.average(np.asarray(losses), weights=np.asarray(weights))) if losses else 0.0


def _neutral_profile() -> dict[str, dict[str, Any]]:
    return {surface: {"weight": 0.02, "cap": 4.0, "variant": "kernel_blend"}
            for surface in ("HV_TURF", "ST_TURF", "ST_AWT")}


def _fit(races: list[dict[str, Any]]) -> dict[str, Any]:
    profile = _neutral_profile()
    audit: dict[str, Any] = {}
    for surface in ("HV_TURF", "ST_TURF", "ST_AWT"):
        subset = [race for race in races if race["surface"] == surface]
        candidates: list[tuple[float, float, float, str]] = []
        for variant in VARIANTS:
            for weight in WEIGHTS:
                for cap in CAPS:
                    trial = copy.deepcopy(profile)
                    trial[surface] = {"weight": weight, "cap": cap, "variant": variant}
                    candidates.append((_pairwise_loss(subset, trial), weight, cap, variant))
        loss, weight, cap, variant = min(
            candidates,
            key=lambda item: (round(item[0], 12), item[1], item[2], VARIANTS.index(item[3])),
        )
        profile[surface] = {"weight": weight, "cap": cap, "variant": variant}
        audit[surface] = {"races": len(subset), "loss": round(loss, 8)}
    return {"profile": profile, "audit": audit}


def _date_folds(dev_dates: list[str]) -> list[tuple[list[str], list[str]]]:
    initial = max(8, int(math.ceil(len(dev_dates) * 0.40)))
    blocks = [list(block) for block in np.array_split(np.asarray(dev_dates[initial:], dtype=object), 5) if len(block)]
    output: list[tuple[list[str], list[str]]] = []
    cursor = initial
    for block in blocks:
        output.append((dev_dates[:cursor], block))
        cursor += len(block)
    return output


def _walk_forward(races: list[dict[str, Any]], dev_dates: list[str]) -> dict[str, Any]:
    all_records: list[dict[str, Any]] = []
    folds = []
    for number, (train_dates, valid_dates) in enumerate(_date_folds(dev_dates), start=1):
        train_set, valid_set = set(train_dates), set(valid_dates)
        train = [race for race in races if race["date"] in train_set]
        valid = [race for race in races if race["date"] in valid_set]
        fit = _fit(train)
        records = [_race_output(race, fit["profile"]) for race in valid]
        all_records.extend(records)
        report = _report(records)
        folds.append({
            "fold": number,
            "train_dates": [train_dates[0], train_dates[-1]],
            "valid_dates": [valid_dates[0], valid_dates[-1]],
            "train_races": len(train), "valid_races": len(valid),
            "fit": fit, **report,
            "primary_nonnegative": all(report["paired"][key]["delta"] >= 0 for key in PRIMARY_KEYS),
        })
    aggregate = _report(all_records)
    return {
        "folds": folds,
        "records": all_records,
        **aggregate,
        "by_surface": _surface_reports(all_records),
        "primary_nonnegative_folds": sum(row["primary_nonnegative"] for row in folds),
        "ranking_positive_metrics": sum(aggregate["paired"][key]["delta"] > 0 for key in RANKING_KEYS),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    meeting_root = Path(args.meeting_root)
    races, base_coverage = base._load_dataset(meeting_root)
    feature_coverage = _attach_features(races, meeting_root)
    dates = sorted({race["date"] for race in races})
    terminal_count = max(1, math.ceil(len(dates) * 0.15))
    dev_dates, terminal_dates = dates[:-terminal_count], dates[-terminal_count:]
    dev_set, terminal_set = set(dev_dates), set(terminal_dates)
    dev = [race for race in races if race["date"] in dev_set]
    terminal = [race for race in races if race["date"] in terminal_set]

    walk_forward = _walk_forward(races, dev_dates)
    final_fit = _fit(dev)
    # This terminal period was already opened by EXP-20261007-04.  It is shown
    # only as a non-decision diagnostic and must not be used to change V2.
    terminal_records = [_race_output(race, final_fit["profile"]) for race in terminal]
    result = {
        "contract": {
            "races": len(races), "dates": len(dates),
            "date_min": dates[0], "date_max": dates[-1],
            "development_dates": [dev_dates[0], dev_dates[-1]],
            "development_races": len(dev),
            "terminal_dates": [terminal_dates[0], terminal_dates[-1]],
            "terminal_races": len(terminal),
            "terminal_policy": "already_opened_non_decision_diagnostic_only",
            "surface_partition": ["HV_TURF", "ST_TURF", "ST_AWT"],
            "grid": {"weights": WEIGHTS, "caps": CAPS, "variants": VARIANTS},
        },
        "formula": {
            "signal": "within_horse_target_distance_minus_same_surface_all_distance",
            "prior_runs": PRIOR_RUNS, "half_life_days": HALF_LIFE_DAYS,
            "max_age_days": MAX_AGE_DAYS,
            "distance_kernel": {"exact": 1.0, "within_100m": 0.5, "within_200m": 0.25},
            "missing": "neutral",
        },
        "leakage_audit": {
            "future_or_same_day_rows": feature_coverage.get("future_or_same_day_rows", 0),
            "status": "PASS" if feature_coverage.get("future_or_same_day_rows", 0) == 0 else "FAIL",
        },
        "coverage": {"base": base_coverage, "distance_v2": feature_coverage},
        "walk_forward_development": {key: value for key, value in walk_forward.items() if key != "records"},
        "final_development_fit": final_fit,
        "terminal_non_decision_diagnostic": {
            **_report(terminal_records),
            "by_surface": _surface_reports(terminal_records),
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
