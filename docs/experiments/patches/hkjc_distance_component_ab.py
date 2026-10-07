#!/usr/bin/env python3
"""Evaluate moving same-distance evidence out of class advantage.

Three formulas share the same point-in-time, complete-history inputs:

1. current: deployed formula (same-distance micro adjustment inside class_score)
2. no_class_distance: remove only that class_score micro adjustment
3. independent_distance: formula 2 plus a capped, low-weight distance dimension

The independent profile is selected on expanding development folds.  The final
profile is fitted on all development dates and the locked terminal block is
opened once.  No odds or post-race feature is used by scoring.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
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
AUTO = REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"
FACTS = REPO / ".agents/scripts"
REFLECTOR = REPO / ".agents/skills/hkjc_racing/hkjc_reflector/scripts"
SHARED = REPO / ".agents/skills/shared_racing"
for path in (PATCHES, AUTO, FACTS, REFLECTOR, SHARED):
    sys.path.insert(0, str(path))

import hkjc_full_history_distance_ab as history_ab  # noqa: E402
import hkjc_hierarchical_refit as metrics  # noqa: E402
import inject_hkjc_fact_anchors as facts  # noqa: E402
from hkjc_no_regression_gate import evaluate_stage4_candidate  # noqa: E402
from hkjc_racing_engine import scoring  # noqa: E402
from hkjc_racing_engine.engine_core import RacingEngine  # noqa: E402


WEIGHTS = (0.02, 0.04, 0.06, 0.08)
CAPS = (4.0, 6.0, 8.0, 10.0)
TEMPERATURE = 6.0
PRIMARY_KEYS = ("gold", "good")
RANKING_KEYS = ("top3_capture_at5", "competitive_recall_at5", "ndcg5")


def _venue_group(surface: str) -> str:
    return "HV" if surface == "HV_TURF" else "ST"


def _distance_component(distance_score: float, cap: float) -> float:
    return 60.0 + max(-cap, min(cap, float(distance_score) - 60.0))


def _candidate_score(runner: dict[str, Any], profile: dict[str, dict[str, float]]) -> float:
    params = profile[_venue_group(runner["surface"])]
    weight = float(params["weight"])
    component = _distance_component(runner["distance_score"], float(params["cap"]))
    return (1.0 - weight) * float(runner["no_class_raw"]) + weight * component


def _record(scores: dict[int, float], actual: dict[int, int]) -> dict[str, Any]:
    picks = sorted(scores, key=lambda number: (-scores[number], number))
    top3 = {number for number, position in actual.items() if position <= 3}
    return {
        "picks": picks,
        "gold": top3.issubset(set(picks[:4])),
        "good": len(picks) >= 2 and picks[0] in top3 and picks[1] in top3,
    }


def _race_model(race: dict[str, Any], model: str, profile: dict | None = None) -> dict[str, Any]:
    if model == "current_live":
        scores = {row["horse_number"]: row["current_raw"] for row in race["runners"]}
    elif model == "no_class_distance":
        scores = {row["horse_number"]: row["no_class_raw"] for row in race["runners"]}
    elif model == "independent_distance" and profile is not None:
        scores = {row["horse_number"]: _candidate_score(row, profile) for row in race["runners"]}
    else:
        raise ValueError(f"unsupported model: {model}")
    return _record(scores, race["actual_pos"])


def _race_output(race: dict[str, Any], candidate: str, profile: dict | None = None) -> dict[str, Any]:
    return {
        "race_key": race["race_key"],
        "date": race["date"],
        "surface": race["surface"],
        "field_size": race["field_size"],
        "actual_pos": race["actual_pos"],
        "models": {
            "current_live": _race_model(race, "current_live"),
            candidate: _race_model(race, candidate, profile),
        },
    }


def _flags_for(records: list[dict[str, Any]], candidate: str) -> tuple[list[dict], list[dict]]:
    cand, base = [], []
    for record in records:
        actual = record["actual_pos"]
        cand.append(metrics._flags(record["models"][candidate], actual))
        base.append(metrics._flags(record["models"]["current_live"], actual))
    return cand, base


def _report(records: list[dict[str, Any]], candidate: str) -> dict[str, Any]:
    cand, base = _flags_for(records, candidate)
    return {
        "baseline": metrics._summarize(base),
        "candidate": metrics._summarize(cand),
        "paired": metrics._paired(cand, base),
    }


def _surface_reports(records: list[dict[str, Any]], candidate: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["surface"]].append(record)
    return {surface: _report(rows, candidate) for surface, rows in sorted(grouped.items())}


def _pairwise_loss(races: list[dict[str, Any]], profile: dict[str, dict[str, float]]) -> float:
    losses, weights = [], []
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


def _fit(races: list[dict[str, Any]]) -> dict[str, Any]:
    profile: dict[str, dict[str, float]] = {}
    audit: dict[str, Any] = {}
    for venue in ("ST", "HV"):
        subset = [race for race in races if _venue_group(race["surface"]) == venue]
        candidates = []
        for weight in WEIGHTS:
            for cap in CAPS:
                params = {
                    "ST": {"weight": 0.04, "cap": 6.0},
                    "HV": {"weight": 0.04, "cap": 6.0},
                }
                params[venue] = {"weight": weight, "cap": cap}
                loss = _pairwise_loss(subset, params)
                candidates.append((loss, weight, cap))
        # Exact tie-break is deliberately conservative: lower weight, then cap.
        loss, weight, cap = min(candidates, key=lambda item: (round(item[0], 12), item[1], item[2]))
        profile[venue] = {"weight": weight, "cap": cap}
        audit[venue] = {"races": len(subset), "loss": round(loss, 8)}
    return {"profile": profile, "audit": audit}


def _date_folds(dev_dates: list[str]) -> list[tuple[list[str], list[str]]]:
    initial = max(8, int(math.ceil(len(dev_dates) * 0.40)))
    blocks = [list(block) for block in np.array_split(np.asarray(dev_dates[initial:], dtype=object), 5) if len(block)]
    output, cursor = [], initial
    for block in blocks:
        output.append((dev_dates[:cursor], block))
        cursor += len(block)
    return output


def _walk_forward(races: list[dict[str, Any]], dev_dates: list[str]) -> dict[str, Any]:
    all_records: list[dict[str, Any]] = []
    folds = []
    for number, (train_dates, valid_dates) in enumerate(_date_folds(dev_dates), start=1):
        train = [race for race in races if race["date"] in set(train_dates)]
        valid = [race for race in races if race["date"] in set(valid_dates)]
        fit = _fit(train)
        records = [_race_output(race, "independent_distance", fit["profile"]) for race in valid]
        all_records.extend(records)
        fold_report = _report(records, "independent_distance")
        folds.append({
            "fold": number,
            "train_dates": [train_dates[0], train_dates[-1]],
            "valid_dates": [valid_dates[0], valid_dates[-1]],
            "train_races": len(train),
            "valid_races": len(valid),
            "fit": fit,
            **fold_report,
            "primary_nonnegative": all(fold_report["paired"][key]["delta"] >= 0 for key in PRIMARY_KEYS),
        })
    aggregate = _report(all_records, "independent_distance")
    ranking_positive = sum(aggregate["paired"][key]["delta"] > 0 for key in RANKING_KEYS)
    primary_folds = sum(row["primary_nonnegative"] for row in folds)
    eligible = bool(
        all(aggregate["paired"][key]["delta"] >= 0 for key in PRIMARY_KEYS)
        and primary_folds >= 3
        and ranking_positive >= 2
    )
    return {
        "folds": folds,
        "records": all_records,
        **aggregate,
        "primary_nonnegative_folds": primary_folds,
        "ranking_positive_metrics": ranking_positive,
        "eligible_for_terminal": eligible,
    }


def _load_dataset(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    races: list[dict[str, Any]] = []
    audit = Counter()
    class_deltas: list[float] = []
    distance_weights = getattr(
        scoring,
        "DISTANCE_SUITABILITY_MICRO_WEIGHTS",
        scoring.CLASS_MICRO_WEIGHTS,
    )
    originals = {
        "bonus": distance_weights["same_dist_place_bonus"],
        "pen": distance_weights["same_dist_unplaced_pen"],
    }
    try:
        for folder in sorted(root.glob("20??-??-??_*")):
            date_match = re.match(r"(20\d{2}-\d{2}-\d{2})", folder.name)
            if not date_match:
                continue
            meeting_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
            actual_by_race = history_ab._result_map(folder)
            for logic_path in sorted(folder.glob("Race_*_Logic.json")):
                race_match = re.search(r"Race_(\d+)_Logic", logic_path.name)
                if not race_match or race_match.group(1) not in actual_by_race:
                    continue
                race_no = int(race_match.group(1))
                facts_path = history_ab._facts_path(folder, race_no)
                if facts_path is None:
                    continue
                logic = json.loads(logic_path.read_text(encoding="utf-8"))
                context = copy.deepcopy(logic.get("race_analysis") or {})
                context["race_date"] = meeting_date.date().isoformat()
                horses = copy.deepcopy(logic.get("horses") or {})
                blocks = history_ab._horse_blocks(facts_path.read_text(encoding="utf-8"))
                for horse_no, horse in horses.items():
                    history = history_ab._history(blocks.get(history_ab._integer(horse_no), ""))
                    if not history:
                        continue
                    audit["horses_with_history"] += 1
                    audit["future_or_same_day_rows"] += sum(row["date_dt"] >= meeting_date for row in history)
                    season_stats, best_distance = history_ab._candidate_fields(history, context, meeting_date)
                    history_ab._apply_candidate(horse, season_stats, best_distance)

                actual = actual_by_race[str(race_no)]
                runner_rows = []
                for horse_no, horse in horses.items():
                    number = history_ab._integer(horse_no)
                    if number not in actual:
                        continue
                    distance_weights["same_dist_place_bonus"] = originals["bonus"]
                    distance_weights["same_dist_unplaced_pen"] = originals["pen"]
                    current = RacingEngine(copy.deepcopy(horse), context).analyze_horse()
                    distance_weights["same_dist_place_bonus"] = 0.0
                    distance_weights["same_dist_unplaced_pen"] = 0.0
                    no_class = RacingEngine(copy.deepcopy(horse), context).analyze_horse()
                    runner_rows.append({
                        "horse_number": number,
                        "current_raw": float(current["ability_score_raw"]),
                        "no_class_raw": float(no_class["ability_score_raw"]),
                        "distance_score": float(no_class["feature_scores"]["distance_score"]),
                        "surface": "",
                    })
                    delta = float(no_class["ability_score_raw"]) - float(current["ability_score_raw"])
                    class_deltas.append(delta)
                    if abs(delta) > 1e-9:
                        audit["ability_changed_no_class"] += 1
                common = {row["horse_number"] for row in runner_rows}
                actual = {number: position for number, position in actual.items() if number in common}
                if len(actual) < 4 or len({number for number, position in actual.items() if position <= 3}) < 3:
                    continue
                runner_rows = [row for row in runner_rows if row["horse_number"] in actual]
                venue = facts.normalize_venue_surface(context.get("venue") or context.get("racecourse"))
                surface = "HV_TURF" if venue == "跑馬地" else "ST_AWT" if venue == "沙田AWT" else "ST_TURF"
                for row in runner_rows:
                    row["surface"] = surface
                races.append({
                    "race_key": f"{folder.name}::{race_no}",
                    "date": meeting_date.date().isoformat(),
                    "surface": surface,
                    "field_size": len(actual),
                    "actual_pos": actual,
                    "runners": runner_rows,
                })
    finally:
        distance_weights["same_dist_place_bonus"] = originals["bonus"]
        distance_weights["same_dist_unplaced_pen"] = originals["pen"]
    return races, {
        **dict(audit),
        "mean_abs_no_class_delta": round(float(np.mean(np.abs(class_deltas))), 6) if class_deltas else 0.0,
        "max_abs_no_class_delta": round(max((abs(value) for value in class_deltas), default=0.0), 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    races, coverage = _load_dataset(Path(args.meeting_root))
    ranking_payload = []
    raw_payload = []
    for race in races:
        ordered = sorted(
            race["runners"],
            key=lambda row: (-row["current_raw"], row["horse_number"]),
        )
        ranking_payload.append([race["race_key"], [row["horse_number"] for row in ordered]])
        raw_payload.append([
            race["race_key"],
            [[row["horse_number"], row["current_raw"]] for row in sorted(race["runners"], key=lambda item: item["horse_number"])],
        ])
    coverage["current_ranking_sha256"] = hashlib.sha256(
        json.dumps(ranking_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    coverage["current_raw_score_sha256"] = hashlib.sha256(
        json.dumps(raw_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    dates = sorted({race["date"] for race in races})
    terminal_count = max(1, math.ceil(len(dates) * 0.15))
    dev_dates, terminal_dates = dates[:-terminal_count], dates[-terminal_count:]
    dev_set, terminal_set = set(dev_dates), set(terminal_dates)
    dev = [race for race in races if race["date"] in dev_set]
    terminal = [race for race in races if race["date"] in terminal_set]

    no_class_records = [_race_output(race, "no_class_distance") for race in races]
    no_class_dev = [row for row in no_class_records if row["date"] in dev_set]
    no_class_terminal = [row for row in no_class_records if row["date"] in terminal_set]
    no_class_stage4 = evaluate_stage4_candidate(
        no_class_records,
        "no_class_distance",
        leakage_audit_passed=coverage.get("future_or_same_day_rows", 0) == 0,
        holdout_fraction=0.15,
    )

    walk_forward = _walk_forward(races, dev_dates)
    independent_terminal: dict[str, Any] = {"opened": False}
    independent_stage4 = None
    final_fit = _fit(dev)
    if walk_forward["eligible_for_terminal"]:
        terminal_records = [
            _race_output(race, "independent_distance", final_fit["profile"])
            for race in terminal
        ]
        independent_terminal = {
            "opened": True,
            "fit": final_fit,
            **_report(terminal_records, "independent_distance"),
        }
        predicted_dates = {row["date"] for row in walk_forward["records"]}
        # The earliest development block exists only to seed the first fit.  Add
        # conservative no-change predictions there so the decision helper sees
        # the original 33-date split without introducing in-sample predictions.
        seed_records = []
        for race in dev:
            if race["date"] in predicted_dates:
                continue
            row = _race_output(race, "current_live")
            row["models"]["independent_distance"] = copy.deepcopy(row["models"]["current_live"])
            seed_records.append(row)
        stage4_records = seed_records + walk_forward["records"] + terminal_records
        independent_stage4 = evaluate_stage4_candidate(
            stage4_records,
            "independent_distance",
            leakage_audit_passed=coverage.get("future_or_same_day_rows", 0) == 0,
            holdout_fraction=0.15,
        )

    report = {
        "contract": {
            "races": len(races),
            "dates": len(dates),
            "date_min": dates[0] if dates else None,
            "date_max": dates[-1] if dates else None,
            "development_dates": [dev_dates[0], dev_dates[-1]],
            "development_races": len(dev),
            "terminal_dates": [terminal_dates[0], terminal_dates[-1]],
            "terminal_races": len(terminal),
            "candidate_grid": {"weights": WEIGHTS, "caps": CAPS, "venue_partition": "ST versus HV"},
            "baseline": "deployed full-history formula",
        },
        "corpus": {
            "catalog_status": "hot_only_unregistered",
            "coverage_note": "local archive used; no matching long-term catalog records",
        },
        "leakage_audit": {
            "future_or_same_day_rows": coverage.get("future_or_same_day_rows", 0),
            "status": "PASS" if coverage.get("future_or_same_day_rows", 0) == 0 else "FAIL",
        },
        "coverage": coverage,
        "no_class_distance": {
            "development": _report(no_class_dev, "no_class_distance"),
            "terminal": _report(no_class_terminal, "no_class_distance"),
            "terminal_by_surface": _surface_reports(no_class_terminal, "no_class_distance"),
            "all": _report(no_class_records, "no_class_distance"),
            "stage4": no_class_stage4,
        },
        "independent_distance": {
            "walk_forward_development": {key: value for key, value in walk_forward.items() if key != "records"},
            "final_development_fit": final_fit,
            "terminal": independent_terminal,
            "terminal_by_surface": (
                _surface_reports(terminal_records, "independent_distance")
                if independent_terminal["opened"] else {}
            ),
            "stage4": independent_stage4,
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
