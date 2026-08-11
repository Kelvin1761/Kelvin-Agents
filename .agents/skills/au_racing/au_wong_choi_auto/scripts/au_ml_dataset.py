#!/usr/bin/env python3
"""Build and audit the point-in-time AU Wong Choi ML research dataset.

The input is the result-separated snapshot emitted by
``au_runtime_failure_audit.py --dataset-json``.  This module keeps an explicit
feature allow-list: target results and Starting Price remain available only as
labels for retrospective analysis/betting and can never enter model matrices.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from statistics import mean

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))

from scoring import FEATURE_KEYS, MATRIX_WEIGHTS  # noqa: E402


SCHEMA_VERSION = 1
OUTCOME_COLUMNS = {
    "actual_pos",
    "label_win",
    "label_place",
    "market_sp_label",
}
IDENTITY_COLUMNS = {
    "race_id",
    "date",
    "track",
    "race_number",
    "horse_number",
    "horse_name",
}
FORBIDDEN_FEATURE_TOKENS = (
    "actual_pos",
    "result",
    "market",
    "odds",
    "price",
    "starting_price",
    "sp_label",
    "fluc",
    "favourite",
)

BASE_NUMERIC_FEATURES = (
    "race_distance",
    "field_size",
    "barrier",
    "barrier_pct",
    "weight",
    "rating",
    "rating_missing",
    "formal_count",
    "trial_count",
    "trial_top3_count",
    "days_since_last_run",
    "days_since_last_run_missing",
    "recent_finish_mean_3",
    "recent_finish_mean_5",
    "recent_finish_best_3",
    "recent_place_rate_5",
    "recent_win_rate_5",
    "recent_field_percentile_3",
    "same_distance_place_rate",
    "near_distance_place_rate",
    "same_track_place_rate",
    "same_going_place_rate",
    "current_jockey_rides",
    "current_jockey_win_rate",
    "current_jockey_place_rate",
    "jockey_ly_log_rides",
    "jockey_ly_win_rate",
    "jockey_ly_place_rate",
    "trainer_ly_log_rides",
    "trainer_ly_win_rate",
    "trainer_ly_place_rate",
    "pf_run_count",
    "pf_race_time_diff_avg",
    "pf_l800_delta_avg",
    "pf_l600_delta_avg",
    "pf_l400_delta_avg",
    "pf_l200_delta_avg",
    "pf_tempo_qrank_avg",
    "shape_entropy",
    "shape_consensus_count",
    "shape_front_count",
    "shape_mid_count",
    "shape_back_count",
    "shape_inside_count",
    "shape_wide_no_cover_count",
    "shape_early_work_count",
    "source_coverage_pct",
)

CATEGORICAL_FEATURES = (
    "venue",
    "going_bucket",
    "surface",
    "race_type",
    "distance_bucket",
    "field_size_bucket",
    "class_move",
    "shape_consensus",
    "pf_early_runner_pace",
    "pf_early_race_pace",
)


def as_float(value, default: float | None = None) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def as_int(value, default: int = 0) -> int:
    parsed = as_float(value)
    return int(parsed) if parsed is not None else default


def first_int(value, default: int = 0) -> int:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else default


def safe_ratio(numerator, denominator) -> float | None:
    numerator = as_float(numerator)
    denominator = as_float(denominator)
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def clean_category(value, default: str = "Unknown") -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if text and text not in {"-", "N/A"} else default


def going_bucket(value) -> str:
    text = clean_category(value).lower()
    if "heavy" in text or "重" in text:
        return "Heavy"
    if "soft" in text or "軟" in text:
        return "Soft"
    if "good" in text or "firm" in text or "好" in text or "快" in text:
        return "Good/Firm"
    if "synthetic" in text or "合成" in text:
        return "Synthetic"
    return "Unknown"


def race_type(value) -> str:
    text = clean_category(value).lower()
    if "maiden" in text:
        return "Maiden"
    if re.search(r"\b(group|listed|g[123])\b", text):
        return "BlackType"
    if "benchmark" in text or re.search(r"\bbm\s*\d+", text):
        return "Benchmark"
    if "set weight" in text or "wfa" in text:
        return "SetWeights"
    if "handicap" in text:
        return "Handicap"
    if "class" in text:
        return "Class"
    if "open" in text:
        return "Open"
    return "Other"


def distance_bucket(value) -> str:
    distance = as_int(value)
    if not distance:
        return "Unknown"
    if distance <= 1100:
        return "Sprint<=1100"
    if distance <= 1400:
        return "Sprint1200-1400"
    if distance <= 1800:
        return "Middle1500-1800"
    if distance <= 2200:
        return "Staying1900-2200"
    return "Staying2300+"


def field_size_bucket(value) -> str:
    size = as_int(value)
    if size <= 7:
        return "Small<=7"
    if size <= 11:
        return "Medium8-11"
    return "Large12+"


def place_slots(field_size: int) -> int:
    """Australian fixed-odds place convention used for analysis labels."""
    if field_size >= 8:
        return 3
    if field_size >= 5:
        return 2
    return 1


def _parse_date(value) -> date | None:
    text = str(value or "").strip()
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _facts_runs(text: str) -> list[dict]:
    rows = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cols = [part.strip() for part in line.strip("|").split("|")]
        if len(cols) < 10 or not cols[0].isdigit() or not _parse_date(cols[2]):
            continue
        placing_match = re.match(r"\s*(\d+)", cols[7])
        field_match = re.match(r"\s*(\d+)\s*/\s*(\d+)", cols[7])
        venue = re.sub(r"\s+R\d+\b.*$", "", cols[3], flags=re.I).strip()
        rows.append(
            {
                "is_trial": "試閘" in cols[1].lower() or "trial" in cols[1].lower(),
                "date": _parse_date(cols[2]),
                "venue": venue,
                "distance": first_int(cols[4]),
                "going": going_bucket(cols[5]),
                "finish": (
                    int(placing_match.group())
                    if placing_match and int(placing_match.group()) >= 1
                    else None
                ),
                "field": int(field_match.group(2)) if field_match else None,
                "class_move": cols[8],
            }
        )
    return rows


def _record_stats(text: str, label: str | None = None) -> tuple[int, int, int]:
    source = str(text or "")
    if label:
        match = re.search(
            rf"{re.escape(label)}:\s*(\d+):(\d+)-(\d+)-(\d+)",
            source,
        )
    else:
        match = re.match(r"\s*(\d+):(\d+)-(\d+)-(\d+)", source)
    if not match:
        return 0, 0, 0
    starts, wins, seconds, thirds = map(int, match.groups())
    return starts, wins, wins + seconds + thirds


def _rate_from_record(text: str, label: str | None = None) -> float | None:
    starts, _wins, places = _record_stats(text, label)
    return safe_ratio(places, starts)


def _history_features(raw: dict, metadata: dict) -> tuple[dict, list[dict]]:
    target_date = _parse_date(metadata.get("date"))
    all_runs = _facts_runs(raw.get("facts_section", ""))
    leakage = []
    valid_runs = []
    for run in all_runs:
        if target_date and run["date"] and run["date"] >= target_date:
            leakage.append(run)
        else:
            valid_runs.append(run)
    official = sorted(
        (run for run in valid_runs if not run["is_trial"]),
        key=lambda run: run["date"],
        reverse=True,
    )
    trials = sorted(
        (run for run in valid_runs if run["is_trial"]),
        key=lambda run: run["date"],
        reverse=True,
    )
    recent = official[:5]
    finishes = [run["finish"] for run in recent if run["finish"] is not None]
    target_distance = as_int(metadata.get("distance"))
    target_track = clean_category(metadata.get("track"))
    target_going = going_bucket(metadata.get("going"))

    def placed(run: dict) -> bool:
        return run["finish"] is not None and run["finish"] <= 3

    same_distance = [run for run in official if run["distance"] == target_distance]
    near_distance = [
        run for run in official
        if run["distance"] and target_distance and abs(run["distance"] - target_distance) <= 100
    ]
    same_track = [run for run in official if clean_category(run["venue"]) == target_track]
    same_going = [run for run in official if run["going"] == target_going]
    field_percentiles = [
        (run["field"] - run["finish"]) / max(1, run["field"] - 1)
        for run in official[:3]
        if run["field"] and run["finish"] and run["field"] > 1
    ]
    days = None
    if target_date and official and official[0]["date"]:
        days = (target_date - official[0]["date"]).days
    return (
        {
            "formal_count": len(official),
            "trial_count": len(trials),
            "trial_top3_count": sum(placed(run) for run in trials),
            "days_since_last_run": days,
            "days_since_last_run_missing": 1 if days is None else 0,
            "recent_finish_mean_3": mean(finishes[:3]) if finishes[:3] else None,
            "recent_finish_mean_5": mean(finishes) if finishes else None,
            "recent_finish_best_3": min(finishes[:3]) if finishes[:3] else None,
            "recent_place_rate_5": safe_ratio(sum(value <= 3 for value in finishes), len(finishes)),
            "recent_win_rate_5": safe_ratio(sum(value == 1 for value in finishes), len(finishes)),
            "recent_field_percentile_3": mean(field_percentiles) if field_percentiles else None,
            "same_distance_place_rate": safe_ratio(sum(placed(run) for run in same_distance), len(same_distance)),
            "near_distance_place_rate": safe_ratio(sum(placed(run) for run in near_distance), len(near_distance)),
            "same_track_place_rate": safe_ratio(sum(placed(run) for run in same_track), len(same_track)),
            "same_going_place_rate": safe_ratio(sum(placed(run) for run in same_going), len(same_going)),
            "class_move": clean_category(official[0]["class_move"] if official else raw.get("class_move")),
        },
        leakage,
    )


def _people_features(raw: dict) -> dict:
    jockey = raw.get("jockey_ly") if isinstance(raw.get("jockey_ly"), dict) else {}
    trainer = raw.get("trainer_ly") if isinstance(raw.get("trainer_ly"), dict) else {}
    current_rides = as_int(raw.get("current_jockey_formal_rides"))
    return {
        "current_jockey_rides": current_rides,
        "current_jockey_win_rate": safe_ratio(raw.get("current_jockey_formal_wins"), current_rides),
        "current_jockey_place_rate": safe_ratio(raw.get("current_jockey_formal_places"), current_rides),
        "jockey_ly_log_rides": math.log1p(as_int(jockey.get("rides"))),
        "jockey_ly_win_rate": safe_ratio(jockey.get("wins"), jockey.get("rides")),
        "jockey_ly_place_rate": safe_ratio(jockey.get("places"), jockey.get("rides")),
        "trainer_ly_log_rides": math.log1p(as_int(trainer.get("rides"))),
        "trainer_ly_win_rate": safe_ratio(trainer.get("wins"), trainer.get("rides")),
        "trainer_ly_place_rate": safe_ratio(trainer.get("places"), trainer.get("rides")),
    }


def _pf_features(raw: dict) -> dict:
    pf = raw.get("pf_aggregates") if isinstance(raw.get("pf_aggregates"), dict) else {}
    return {
        "pf_run_count": as_int(pf.get("pf_run_count")),
        "pf_race_time_diff_avg": as_float(pf.get("race_time_diff_avg")),
        "pf_l800_delta_avg": as_float(pf.get("l800_delta_avg")),
        "pf_l600_delta_avg": as_float(pf.get("l600_delta_avg")),
        "pf_l400_delta_avg": as_float(pf.get("l400_delta_avg")),
        "pf_l200_delta_avg": as_float(pf.get("l200_delta_avg")),
        "pf_tempo_qrank_avg": as_float(pf.get("tempo_qrank_avg")),
        "pf_early_runner_pace": clean_category(pf.get("latest_early_runner_pace")),
        "pf_early_race_pace": clean_category(pf.get("latest_early_race_pace")),
    }


def _source_coverage(states: dict) -> float:
    if not states:
        return 0.0
    usable = sum(value in {"observed", "derived"} for value in states.values())
    return 100.0 * usable / len(states)


def numeric_features() -> tuple[str, ...]:
    leaves = tuple(f"leaf_{key}" for key in FEATURE_KEYS)
    state_flags = tuple(
        f"leaf_{key}_{state}"
        for key in FEATURE_KEYS
        for state in ("observed", "derived", "fallback", "missing")
    )
    return BASE_NUMERIC_FEATURES + leaves + state_flags


def feature_contract() -> dict:
    return {
        "numeric": list(numeric_features()),
        "categorical": list(CATEGORICAL_FEATURES),
        "forbidden_market_tokens": list(FORBIDDEN_FEATURE_TOKENS),
        "outcomes": sorted(OUTCOME_COLUMNS),
        "identities": sorted(IDENTITY_COLUMNS),
    }


def validate_feature_contract(contract: dict) -> None:
    features = contract["numeric"] + contract["categorical"]
    collisions = sorted(set(features) & (OUTCOME_COLUMNS | IDENTITY_COLUMNS))
    forbidden = sorted(
        name for name in features
        if any(token in name.lower() for token in FORBIDDEN_FEATURE_TOKENS)
    )
    if collisions or forbidden:
        raise ValueError(
            f"ML feature contract leaks labels/market: collisions={collisions}, forbidden={forbidden}"
        )


def _race_id(metadata: dict) -> str:
    return f"{metadata.get('date')}|{metadata.get('track')}|R{as_int(metadata.get('race_number'))}"


def build_rows(runtime: dict) -> tuple[list[dict], dict]:
    contract = feature_contract()
    validate_feature_contract(contract)
    rows = []
    future_records = []
    race_ids = Counter()
    runner_ids = Counter()
    integrity = Counter()
    raw_key_tokens = Counter()
    for race in runtime.get("races") or []:
        metadata = race.get("metadata") or {}
        race_id = _race_id(metadata)
        race_ids[race_id] += 1
        source_rows = race.get("rows") or []
        aligned_field_size = len(source_rows)
        declared_size = as_int(metadata.get("field_size"))
        positions = [as_int(source.get("actual_pos"), 999) for source in source_rows]
        result_field_size = max((pos for pos in positions if pos < 999), default=aligned_field_size)
        max_barrier = max(
            (
                as_int((source.get("raw_pre_race") or {}).get("barrier"))
                for source in source_rows
            ),
            default=aligned_field_size,
        )
        # Prediction-time declared runners/gate positions are features.  The
        # official field after scratchings is outcome-side metadata and is used
        # only to define the Australian place label.
        analysis_field_size = max(
            declared_size,
            aligned_field_size,
            max_barrier,
        )
        if declared_size and declared_size != aligned_field_size:
            integrity["declared_field_size_mismatch"] += 1
        for source in source_rows:
            horse_number = as_int(source.get("horse_number"), 999)
            runner_key = f"{race_id}|{horse_number}"
            runner_ids[runner_key] += 1
            actual_pos = as_int(source.get("actual_pos"), 999)
            raw = source.get("raw_pre_race") if isinstance(source.get("raw_pre_race"), dict) else {}
            for key in raw:
                if any(token in key.lower() for token in FORBIDDEN_FEATURE_TOKENS):
                    raw_key_tokens[key] += 1
            history, leakage = _history_features(raw, metadata)
            for item in leakage:
                future_records.append(
                    {
                        "race_id": race_id,
                        "horse_number": horse_number,
                        "horse_name": source.get("horse_name"),
                        "target_date": metadata.get("date"),
                        "run_date": item["date"].isoformat() if item.get("date") else None,
                        "is_trial": item.get("is_trial"),
                    }
                )
            rating = as_float(raw.get("rating"))
            if rating is not None and rating <= 0:
                rating = None
            barrier = as_float(raw.get("barrier"))
            states = source.get("feature_evidence_state") or {}
            feature_scores = source.get("feature_scores") or {}
            slots = place_slots(result_field_size)
            row = {
                "race_id": race_id,
                "date": metadata.get("date"),
                "track": metadata.get("track"),
                "race_number": as_int(metadata.get("race_number")),
                "horse_number": horse_number,
                "horse_name": source.get("horse_name"),
                "actual_pos": actual_pos,
                "label_win": 1 if actual_pos == 1 else 0,
                "place_slots": slots,
                "label_place": 1 if actual_pos <= slots else 0,
                "market_sp_label": as_float(source.get("result_sp_label")),
                "champion_score": as_float(source.get("score"), 0.0),
                "race_distance": as_float(metadata.get("distance")),
                "field_size": analysis_field_size,
                "barrier": barrier,
                "barrier_pct": (
                    (barrier - 1) / max(1, analysis_field_size - 1)
                    if barrier is not None and barrier > 0
                    else None
                ),
                "weight": as_float(raw.get("weight")),
                "rating": rating,
                "rating_missing": 1 if rating is None else 0,
                **history,
                **_people_features(raw),
                **_pf_features(raw),
                "shape_entropy": as_float(raw.get("recent_shape_entropy")),
                "shape_consensus_count": as_float(raw.get("recent_shape_consensus_count")),
                "shape_front_count": as_float(raw.get("recent_shape_front_count")),
                "shape_mid_count": as_float(raw.get("recent_shape_mid_count")),
                "shape_back_count": as_float(raw.get("recent_shape_back_count")),
                "shape_inside_count": as_float(raw.get("recent_shape_inside_count")),
                "shape_wide_no_cover_count": as_float(raw.get("recent_shape_wide_no_cover_count")),
                "shape_early_work_count": as_float(raw.get("recent_shape_early_work_count")),
                "source_coverage_pct": _source_coverage(states),
                "venue": clean_category(metadata.get("track")),
                "going_bucket": going_bucket(metadata.get("going")),
                "surface": (
                    "Synthetic"
                    if "synthetic" in clean_category(metadata.get("track")).lower()
                    or going_bucket(metadata.get("going")) == "Synthetic"
                    else "Turf"
                ),
                "race_type": race_type(metadata.get("race_class")),
                "distance_bucket": distance_bucket(metadata.get("distance")),
                "field_size_bucket": field_size_bucket(analysis_field_size),
                "shape_consensus": clean_category(raw.get("recent_shape_consensus")),
            }
            for key in FEATURE_KEYS:
                row[f"leaf_{key}"] = as_float(feature_scores.get(key))
                state = clean_category(states.get(key), "missing").lower()
                if state not in {"observed", "derived", "fallback", "missing"}:
                    state = "missing"
                for candidate in ("observed", "derived", "fallback", "missing"):
                    row[f"leaf_{key}_{candidate}"] = 1 if state == candidate else 0
            rows.append(row)
        if sum(pos == 1 for pos in positions) == 0:
            integrity["race_without_winner"] += 1
        elif sum(pos == 1 for pos in positions) > 1:
            integrity["dead_heat_or_duplicate_winner"] += 1
        if any(pos < 1 for pos in positions):
            integrity["invalid_finishing_position"] += 1

    duplicate_races = [key for key, count in race_ids.items() if count > 1]
    duplicate_runners = [key for key, count in runner_ids.items() if count > 1]
    audit = {
        "schema_version": SCHEMA_VERSION,
        "races": len(race_ids),
        "runners": len(rows),
        "duplicate_races": duplicate_races,
        "duplicate_runners": duplicate_runners,
        "integrity_counts": dict(integrity),
        "future_or_target_run_records": future_records,
        "raw_market_like_keys": dict(raw_key_tokens),
        "feature_contract": contract,
    }
    return rows, audit


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "Unknown"


def _coverage(rows: list[dict], contract: dict) -> dict:
    report = {}
    for key in contract["numeric"] + contract["categorical"]:
        values = [row.get(key) for row in rows]
        present = [value for value in values if value not in (None, "", "Unknown")]
        numeric = [float(value) for value in present if isinstance(value, (int, float))]
        report[key] = {
            "present": len(present),
            "coverage_pct": round(100 * len(present) / max(1, len(rows)), 3),
            "missing_pct": round(100 * (len(rows) - len(present)) / max(1, len(rows)), 3),
            "neutral_60_pct": round(
                100 * sum(value == 60 for value in numeric) / max(1, len(rows)),
                3,
            ),
            "unique": len({str(value) for value in present}),
            "min": min(numeric) if numeric else None,
            "max": max(numeric) if numeric else None,
        }
    return report


def complete_audit(rows: list[dict], base: dict, runtime_path: Path) -> dict:
    dates = sorted(row["date"] for row in rows if _parse_date(row.get("date")))
    races = {}
    for row in rows:
        races.setdefault(row["race_id"], row)
    by_venue = Counter(row["venue"] for row in races.values())
    by_distance = Counter(row["distance_bucket"] for row in races.values())
    by_class = Counter(row["race_type"] for row in races.values())
    by_going = Counter(row["going_bucket"] for row in races.values())
    leakage_blockers = (
        len(base["future_or_target_run_records"])
        + len(base["duplicate_races"])
        + len(base["duplicate_runners"])
        + base["integrity_counts"].get("race_without_winner", 0)
        + base["integrity_counts"].get("invalid_finishing_position", 0)
    )
    limitations = [
        "The archive has already been used for prior Rating Matrix optimisation; the final chronological test is new to this ML run but is not globally untouched.",
        "Stable provider horse/jockey/trainer IDs are unavailable; normalized names are used for joins and names are excluded from ML features.",
        "The result-aligned snapshot excludes scratchings and does not preserve target-time scratching history.",
        "Historical body weight and historical place dividends/CLV snapshots are unavailable.",
        "Some Rating Matrix leaves use documented fallback/default values; evidence-state flags are included so ML can distinguish them.",
    ]
    readiness = "NOT READY" if leakage_blockers else "READY WITH LIMITATIONS"
    audit = {
        **base,
        "readiness": readiness,
        "date_range": [dates[0], dates[-1]] if dates else [None, None],
        "average_field_size": round(mean(row["field_size"] for row in races.values()), 3),
        "usable_races": len(races) if readiness != "NOT READY" else 0,
        "excluded_races": 0 if readiness != "NOT READY" else len(races),
        "races_by_venue": dict(by_venue.most_common()),
        "races_by_distance": dict(by_distance.most_common()),
        "races_by_class": dict(by_class.most_common()),
        "races_by_track_condition": dict(by_going.most_common()),
        "feature_coverage": _coverage(rows, base["feature_contract"]),
        "limitations": limitations,
        "champion": {
            "model": "Current AU Wong Choi Rating Matrix",
            "commit_sha": _git_sha(),
            "runtime_dataset_sha256": _sha256_file(runtime_path),
            "matrix_weights": MATRIX_WEIGHTS,
            "source_files": {
                str(path.relative_to(PROJECT_ROOT)): _sha256_file(path)
                for path in (
                    SCRIPT_DIR / "racing_engine" / "engine_core.py",
                    SCRIPT_DIR / "racing_engine" / "scoring.py",
                    SCRIPT_DIR / "racing_engine" / "matrix_mapper.py",
                )
            },
        },
    }
    return audit


def render_readiness(audit: dict) -> str:
    coverage = sorted(
        audit["feature_coverage"].items(),
        key=lambda item: (item[1]["coverage_pct"], item[0]),
    )
    lines = [
        "# AU ML Readiness Report",
        "",
        f"**Dataset classification: {audit['readiness']}**",
        "",
        "## Dataset",
        "",
        f"- Total races: **{audit['races']}**",
        f"- Total runners: **{audit['runners']}**",
        f"- Date range: **{audit['date_range'][0]} → {audit['date_range'][1]}**",
        f"- Average field size: **{audit['average_field_size']:.2f}**",
        f"- Usable races: **{audit['usable_races']}**",
        f"- Excluded races: **{audit['excluded_races']}**",
        "",
        "## Champion Freeze",
        "",
        f"- Model: {audit['champion']['model']}",
        f"- Commit SHA: `{audit['champion']['commit_sha']}`",
        f"- Runtime dataset SHA256: `{audit['champion']['runtime_dataset_sha256']}`",
        f"- Matrix weights: `{json.dumps(audit['champion']['matrix_weights'], sort_keys=True)}`",
        "- Frozen scorer source SHA256:",
        *[
            f"  - `{path}`: `{digest}`"
            for path, digest in audit["champion"]["source_files"].items()
        ],
        "",
        "## Data Integrity And Leakage",
        "",
        f"- Duplicate race IDs: **{len(audit['duplicate_races'])}**",
        f"- Duplicate runners: **{len(audit['duplicate_runners'])}**",
        f"- Target/future run records in Facts: **{len(audit['future_or_target_run_records'])}**",
        f"- Market-like raw keys quarantined from features: `{audit['raw_market_like_keys']}`",
        f"- Other integrity counts: `{audit['integrity_counts']}`",
        "- Starting Price exists only as `market_sp_label`; explicit allow-lists prevent it entering model features.",
        "",
        "## Race Coverage",
        "",
        f"- Venue: `{json.dumps(audit['races_by_venue'], sort_keys=True)}`",
        f"- Distance: `{json.dumps(audit['races_by_distance'], sort_keys=True)}`",
        f"- Class: `{json.dumps(audit['races_by_class'], sort_keys=True)}`",
        f"- Track condition: `{json.dumps(audit['races_by_track_condition'], sort_keys=True)}`",
        "",
        "## Feature Coverage",
        "",
        "| Feature | Coverage | Missing | Neutral 60 | Unique | Range |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for name, row in coverage:
        bounds = "—" if row["min"] is None else f"{row['min']:.3g}…{row['max']:.3g}"
        lines.append(
            f"| `{name}` | {row['coverage_pct']:.1f}% | {row['missing_pct']:.1f}% | "
            f"{row['neutral_60_pct']:.1f}% | {row['unique']} | {bounds} |"
        )
    lines.extend([
        "",
        "## Known Limitations",
        "",
        *[f"- {item}" for item in audit["limitations"]],
        "",
        "## Recommended Feature Set",
        "",
        "- Raw point-in-time race/horse/history/people/PF/shape features.",
        "- Current 0–100 leaf scores as engineered inputs, paired with observed/derived/fallback/missing flags.",
        "- Low-cardinality race context categories (venue, going, surface, race type, distance and field-size bands).",
        "- Exclude horse/jockey/trainer names, all market fields, result fields, Rating Matrix aggregate score and matrix aggregates from independent challengers.",
        "",
        "## Decision",
        "",
        (
            "Continue automatically into chronological ML training."
            if audit["readiness"] != "NOT READY"
            else "Do not train until the integrity/leakage blockers above are fixed."
        ),
        "",
    ])
    return "\n".join(lines)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dataset", type=Path, required=True)
    parser.add_argument("--dataset-output", type=Path, required=True)
    parser.add_argument("--audit-json", type=Path, required=True)
    parser.add_argument("--readiness-md", type=Path, required=True)
    args = parser.parse_args()
    runtime = json.loads(args.runtime_dataset.read_text(encoding="utf-8"))
    rows, base = build_rows(runtime)
    audit = complete_audit(rows, base, args.runtime_dataset)
    write_json(
        args.dataset_output,
        {
            "schema_version": SCHEMA_VERSION,
            "feature_contract": audit["feature_contract"],
            "rows": rows,
        },
    )
    write_json(args.audit_json, audit)
    args.readiness_md.parent.mkdir(parents=True, exist_ok=True)
    args.readiness_md.write_text(render_readiness(audit), encoding="utf-8")
    print(f"Readiness: {audit['readiness']}")
    print(f"Races: {audit['races']}  runners: {audit['runners']}")
    print(f"Future/target Facts records: {len(audit['future_or_target_run_records'])}")
    print(f"Dataset: {args.dataset_output}")
    print(f"Report: {args.readiness_md}")
    return 0 if audit["readiness"] != "NOT READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
