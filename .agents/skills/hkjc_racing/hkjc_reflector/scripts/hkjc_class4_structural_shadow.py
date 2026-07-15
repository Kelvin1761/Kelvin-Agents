#!/usr/bin/env python3
"""Frozen market-free Class 4 structural shadow for HKJC Reflector.

The scorer is deliberately isolated from the production 7D matrix.  It writes
meeting artefacts plus an append-only central ledger, separates retrospective
bootstrap evidence from prospective evidence, and only reports promotion
eligibility for manual approval.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import math
import os
import random
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np
import pandas as pd

from build_hkjc_ranking_dataset import build_rows
from hkjc_results_db import get_analysis_archive_root
from review_auto_weighting import meeting_date


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_CONFIG = SKILL_DIR / "resources" / "hkjc_class4_shadow_v1.json"
DEFAULT_MODEL = SKILL_DIR / "artifacts" / "hkjc_class4_shadow_model_v1.json"
DEFAULT_TRAINING = SKILL_DIR / "artifacts" / "hkjc_class4_shadow_training_v1.csv"
DEFAULT_LEDGER = get_analysis_archive_root() / "HKJC_Class4_Shadow_Ledger.jsonl"
DEFAULT_TRACKER_JSON = get_analysis_archive_root() / "HKJC_Class4_Shadow_Tracker.json"
DEFAULT_TRACKER_MD = get_analysis_archive_root() / "HKJC_Class4_Shadow_Tracker.md"

MEETING_CSV = "HKJC_Class4_Shadow_Scoring.csv"
MEETING_JSON = "HKJC_Class4_Shadow_Forward_Review.json"
MEETING_MD = "HKJC_Class4_Shadow_Forward_Review.md"
REPORT_START = "<!-- HKJC_CLASS4_SHADOW_START -->"
REPORT_END = "<!-- HKJC_CLASS4_SHADOW_END -->"
BASELINE = "current_live_rank_score"
RNG_SEED = 20260714

FORBIDDEN_FEATURE_TOKENS = (
    "odds", "market", "favourite", "favorite", "betting", "dividend", "starting_price"
)

BLOCKS: dict[str, list[str]] = {
    "trackwork_trial": [
        "tw_entries_count", "tw_gallop_count", "tw_flags_count",
        "tw_confidence_low", "tw_jockey_present", "flag_trackwork_slowing",
        "flag_medical_issue", "days_since_last", "trackwork_density",
    ],
    "variant_sectional": [
        "raw_finish_time_adj", "raw_l400", "flag_energy_up", "flag_energy_down",
        "flag_l400_up", "flag_l400_down", "flag_finish_competitive", "flag_finish_slow",
    ],
    "historical_professional_priors": [
        "prior_combo_starts", "prior_combo_win_rate", "prior_combo_place_rate",
        "prior_jockey_cd_starts", "prior_jockey_cd_win_rate", "prior_jockey_cd_place_rate",
        "prior_trainer_cd_starts", "prior_trainer_cd_win_rate", "prior_trainer_cd_place_rate",
        "prior_class_distance_starts", "prior_class_distance_win_rate", "prior_class_distance_place_rate",
        "prior_draw_class_starts", "prior_draw_class_win_rate", "prior_draw_class_place_rate",
        "prior_weight_class_starts", "prior_weight_class_win_rate", "prior_weight_class_place_rate",
        "prior_rest_bucket_starts", "prior_rest_bucket_win_rate", "prior_rest_bucket_place_rate",
        "prior_horse_cd_starts", "prior_horse_cd_win_rate", "prior_horse_cd_place_rate",
        "prior_horse_rest_starts", "prior_horse_rest_win_rate", "prior_horse_rest_place_rate",
    ],
    "rail_draw_condition": [
        "barrier", "field_size", "venue_hv", "venue_st", "is_sprint", "is_middle",
        "course_valid_turf", "course_A", "course_B", "course_C", "course_Cplus3",
        "draw_x_course_A", "draw_x_course_B", "draw_x_course_C", "draw_x_course_Cplus3",
        "draw_x_hv", "draw_x_sprint",
    ],
}

METRIC_KEYS = (
    "top1_win", "top2_hits", "both_top2_place", "top3_hits", "top4_hits",
    "top4_all", "top5_hits", "top5_all", "winner_mrr",
)


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _race_z(values: pd.Series, race_key: pd.Series) -> pd.Series:
    grouped = values.groupby(race_key)
    centre = grouped.transform("mean")
    scale = grouped.transform(lambda values: values.std(ddof=0)).replace(0, np.nan)
    return ((values - centre) / scale).fillna(0.0)


def prepare_features(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Reproduce the frozen research feature engineering without result inputs."""
    df = raw.copy()
    df["date"] = df["date"].astype(str)
    df["race_key"] = df["meeting"].astype(str) + "::" + df["race_number"].astype(str)
    df["venue_hv"] = (df["venue"] == "跑馬地").astype(float)
    df["venue_st"] = (df["venue"] == "沙田").astype(float)
    distance = _numeric(df, "distance_num").fillna(0)
    df["is_sprint"] = distance.isin([1000, 1200]).astype(float)
    df["is_middle"] = distance.isin([1600, 1650, 1800]).astype(float)
    df["trackwork_density"] = _numeric(df, "tw_gallop_count") / (
        1.0 + _numeric(df, "tw_entries_count")
    )

    course = df.get("course", pd.Series("Unknown", index=df.index)).fillna("Unknown").astype(str)
    df["course_valid_turf"] = course.isin(["A", "B", "C", "C+3"]).astype(float)
    for token in ("A", "B", "C", "C+3"):
        safe = token.replace("+", "plus")
        df[f"course_{safe}"] = (course == token).astype(float)
        df[f"draw_x_course_{safe}"] = _numeric(df, "barrier").fillna(0) * df[f"course_{safe}"]
    df["draw_x_hv"] = _numeric(df, "barrier").fillna(0) * df["venue_hv"]
    df["draw_x_sprint"] = _numeric(df, "barrier").fillna(0) * df["is_sprint"]

    expanded: dict[str, list[str]] = {}
    for block, columns in BLOCKS.items():
        for column in columns:
            if column not in df:
                df[column] = np.nan
        relative = []
        for column in columns:
            values = _numeric(df, column)
            grouped = values.groupby(df["race_key"])
            centre = grouped.transform("mean")
            scale = grouped.transform(lambda values: values.std(ddof=0)).replace(0, np.nan)
            relative_name = f"{column}__race_rel"
            df[relative_name] = ((values - centre) / scale).fillna(0.0)
            relative.append(relative_name)
        expanded[block] = list(dict.fromkeys([*columns, *relative]))
    return df, expanded


def assert_market_free(features: list[str]) -> None:
    offenders = [
        feature for feature in features
        if any(token in feature.lower() for token in FORBIDDEN_FEATURE_TOKENS)
    ]
    if offenders:
        raise ValueError(f"Market-derived features are forbidden: {offenders}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freeze_model(training_csv: Path, output: Path, config_path: Path) -> Path:
    """Fit once and serialize portable inference state; runtime needs no sklearn."""
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    config = json.loads(config_path.read_text(encoding="utf-8"))
    raw = pd.read_csv(training_csv, encoding="utf-8-sig")
    frame, blocks = prepare_features(raw)
    models: dict[str, Any] = {}
    needed = sorted({block for variant in config["variants"].values() for block in variant["weights"]})
    for block in needed:
        features = blocks[block]
        assert_market_free(features)
        pipeline = Pipeline([
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
            ("model", LogisticRegression(C=0.18, max_iter=2000, solver="liblinear")),
        ])
        pipeline.fit(frame[features], frame["is_top3"].astype(int))
        imputer = pipeline.named_steps["impute"]
        scaler = pipeline.named_steps["scale"]
        logistic = pipeline.named_steps["model"]
        statistics = np.asarray(imputer.statistics_, dtype=float)
        valid_features = [index for index, value in enumerate(statistics) if math.isfinite(float(value))]
        indicator_features = [int(value) for value in imputer.indicator_.features_]
        model_state = {
            "features": features,
            "imputer_statistics": [float(value) if math.isfinite(float(value)) else None for value in statistics],
            "valid_features": valid_features,
            "indicator_features": indicator_features,
            "scaler_mean": [float(value) for value in scaler.mean_],
            "scaler_scale": [float(value) for value in scaler.scale_],
            "coef": [float(value) for value in logistic.coef_[0]],
            "intercept": float(logistic.intercept_[0]),
        }
        portable = portable_probability(frame, model_state)
        sklearn_probability = pipeline.predict_proba(frame[features])[:, 1]
        max_error = float(np.max(np.abs(portable - sklearn_probability)))
        if max_error > 1e-10:
            raise ValueError(f"Portable model verification failed for {block}: {max_error}")
        model_state["portable_verification_max_abs_error"] = max_error
        models[block] = model_state

    payload = {
        "version": config["version"],
        "trained_through": config["trained_through"],
        "training_dataset": str(training_csv.resolve()),
        "training_sha256": _sha256(training_csv),
        "training_rows": int(len(frame)),
        "training_races": int(frame["race_key"].nunique()),
        "training_meetings": int(frame["date"].nunique()),
        "target": "is_top3",
        "market_features_used": [],
        "models": models,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(output, payload)
    return output


def portable_probability(frame: pd.DataFrame, state: dict[str, Any]) -> np.ndarray:
    features = list(state["features"])
    assert_market_free(features)
    matrix = np.column_stack([_numeric(frame, feature).to_numpy(float) for feature in features])
    missing = ~np.isfinite(matrix)
    statistics = np.asarray([
        np.nan if value is None else float(value) for value in state["imputer_statistics"]
    ])
    valid = np.asarray(state["valid_features"], dtype=int)
    transformed = matrix[:, valid].copy()
    valid_missing = ~np.isfinite(transformed)
    if valid_missing.any():
        transformed[valid_missing] = np.take(statistics[valid], np.where(valid_missing)[1])
    indicators = np.asarray(state["indicator_features"], dtype=int)
    if indicators.size:
        transformed = np.column_stack([transformed, missing[:, indicators].astype(float)])
    centre = np.asarray(state["scaler_mean"], dtype=float)
    scale = np.asarray(state["scaler_scale"], dtype=float)
    transformed = (transformed - centre) / np.where(scale == 0, 1.0, scale)
    logits = transformed @ np.asarray(state["coef"], dtype=float) + float(state["intercept"])
    logits = np.clip(logits, -40.0, 40.0)
    return 1.0 / (1.0 + np.exp(-logits))


def _rank_metrics(ranked: pd.DataFrame) -> dict[str, float | int]:
    positions = ranked["finish_pos"].astype(int).tolist()
    top2_hits = sum(position <= 3 for position in positions[:2])
    top3_hits = sum(position <= 3 for position in positions[:3])
    top4_hits = sum(position <= 3 for position in positions[:4])
    top5_hits = sum(position <= 3 for position in positions[:5])
    winner_rank = positions.index(1) + 1
    return {
        "top1_win": int(positions[0] == 1),
        "top2_hits": int(top2_hits),
        "both_top2_place": int(top2_hits == 2),
        "top3_hits": int(top3_hits),
        "top4_hits": int(top4_hits),
        "top4_all": int(top4_hits == 3),
        "top5_hits": int(top5_hits),
        "top5_all": int(top5_hits == 3),
        "winner_mrr": 1.0 / winner_rank,
    }


def score_frame(
    raw: pd.DataFrame,
    config: dict[str, Any],
    model_artifact: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if model_artifact.get("version") != config.get("version"):
        raise ValueError("Shadow config/model version mismatch")
    if model_artifact.get("market_features_used"):
        raise ValueError("Frozen model declares market features")
    frame, _blocks = prepare_features(raw)
    frame["score__baseline"] = _numeric(frame, BASELINE)
    support_names = sorted(model_artifact["models"])
    for block in support_names:
        probability = pd.Series(
            portable_probability(frame, model_artifact["models"][block]), index=frame.index
        )
        frame[f"support__{block}"] = _race_z(probability, frame["race_key"])
    baseline_z = _race_z(frame["score__baseline"], frame["race_key"])
    frame["score__primary_full_support"] = baseline_z
    frame["score__challenger_trackwork_variant"] = baseline_z
    class4 = frame["race_class_label"].astype(str).eq(config["target_race_class"])
    for variant, definition in config["variants"].items():
        score = baseline_z.copy()
        structural = pd.Series(0.0, index=frame.index)
        for block, weight in definition["weights"].items():
            structural += float(weight) * frame[f"support__{block}"]
        score.loc[class4] = score.loc[class4] + structural.loc[class4]
        frame[f"score__{variant}"] = score

    horse_rows: list[dict[str, Any]] = []
    race_records: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    variants = ("baseline", *config["variants"].keys())
    for race_key, race in frame.groupby("race_key", sort=False):
        if race["score__baseline"].isna().any():
            skipped.append({"race_key": race_key, "reason": "missing current_live_rank_score"})
            continue
        first = race.iloc[0]
        rankings: dict[str, pd.DataFrame] = {}
        for variant in variants:
            score_column = f"score__{variant}"
            rankings[variant] = race.sort_values(
                [score_column, "horse_number"], ascending=[False, True]
            )
        event_key = f"{first['date']}|{first['venue']}|{int(first['race_number'])}"
        record: dict[str, Any] = {
            "event_key": event_key,
            "date": str(first["date"]),
            "meeting_name": str(first["meeting_name"]),
            "race_number": int(first["race_number"]),
            "venue": str(first["venue"]),
            "track": str(first["track"]),
            "course": str(first["course"]),
            "distance_num": int(float(first["distance_num"])),
            "race_class": str(first["race_class_label"]),
            "is_target_class": bool(str(first["race_class_label"]) == config["target_race_class"]),
            "field_size": int(len(race)),
            "observed_placegetters": int((race["finish_pos"].astype(int) <= 3).sum()),
            "data_quality_warning": (
                "fewer than three official placegetters are present in the frozen Logic join"
                if int((race["finish_pos"].astype(int) <= 3).sum()) < 3 else None
            ),
            "actual_top3": [
                int(number) for number in race.sort_values("finish_pos").loc[
                    race.sort_values("finish_pos")["finish_pos"].astype(int) <= 3, "horse_number"
                ].tolist()
            ],
            "models": {},
        }
        for variant, ranked in rankings.items():
            top_numbers = ranked["horse_number"].astype(int).tolist()
            record["models"][variant] = {
                **_rank_metrics(ranked),
                "top1": top_numbers[0],
                "top2": top_numbers[:2],
                "top4": top_numbers[:4],
            }
        race_records.append(record)

        rank_maps = {
            variant: {int(number): rank for rank, number in enumerate(ranked["horse_number"], 1)}
            for variant, ranked in rankings.items()
        }
        for _, row in race.sort_values("horse_number").iterrows():
            number = int(row["horse_number"])
            horse_rows.append({
                "race_number": int(row["race_number"]),
                "race_class": str(row["race_class_label"]),
                "horse_number": number,
                "horse_name": str(row["horse_name"]),
                "finish_pos": int(row["finish_pos"]),
                "baseline_rank": rank_maps["baseline"][number],
                "primary_rank": rank_maps["primary_full_support"][number],
                "challenger_rank": rank_maps["challenger_trackwork_variant"][number],
                "baseline_score": float(row["score__baseline"]),
                "primary_score": float(row["score__primary_full_support"]),
                "challenger_score": float(row["score__challenger_trackwork_variant"]),
                **{block: float(row[f"support__{block}"]) for block in support_names},
                "model_version": config["version"],
            })
    return horse_rows, race_records, skipped


def _summarize(records: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    if not records:
        return {"races": 0}
    models = [record["models"][variant] for record in records]
    n = len(models)
    return {
        "races": n,
        "top1_wins": sum(int(row["top1_win"]) for row in models),
        "top1_rate": sum(float(row["top1_win"]) for row in models) / n,
        "top2_place_hits": sum(int(row["top2_hits"]) for row in models),
        "top2_individual_place_rate": sum(float(row["top2_hits"]) for row in models) / (2 * n),
        "both_top2_place": sum(int(row["both_top2_place"]) for row in models),
        "both_top2_place_rate": sum(float(row["both_top2_place"]) for row in models) / n,
        "avg_top3_hits": sum(float(row["top3_hits"]) for row in models) / n,
        "avg_top4_hits": sum(float(row["top4_hits"]) for row in models) / n,
        "top4_all": sum(int(row["top4_all"]) for row in models),
        "top4_all_rate": sum(float(row["top4_all"]) for row in models) / n,
        "avg_top5_hits": sum(float(row["top5_hits"]) for row in models) / n,
        "top5_all": sum(int(row["top5_all"]) for row in models),
        "winner_mrr": sum(float(row["winner_mrr"]) for row in models) / n,
    }


def _deltas(records: list[dict[str, Any]], variant: str) -> dict[str, float]:
    baseline = _summarize(records, "baseline")
    candidate = _summarize(records, variant)
    if not records:
        return {}
    return {
        "top1_rate": candidate["top1_rate"] - baseline["top1_rate"],
        "top2_individual_place_rate": candidate["top2_individual_place_rate"] - baseline["top2_individual_place_rate"],
        "both_top2_place_rate": candidate["both_top2_place_rate"] - baseline["both_top2_place_rate"],
        "avg_top4_hits": candidate["avg_top4_hits"] - baseline["avg_top4_hits"],
        "top4_all_rate": candidate["top4_all_rate"] - baseline["top4_all_rate"],
        "winner_mrr": candidate["winner_mrr"] - baseline["winner_mrr"],
    }


def _bootstrap_ci(records: list[dict[str, Any]], variant: str) -> tuple[float, float]:
    deltas = [
        (record["models"][variant]["top2_hits"] - record["models"]["baseline"]["top2_hits"]) / 2.0
        for record in records
    ]
    if not deltas:
        return 0.0, 0.0
    rng = random.Random(RNG_SEED)
    simulations = sorted(
        mean(deltas[rng.randrange(len(deltas))] for _ in deltas)
        for _ in range(5000)
    )
    return simulations[int(0.025 * len(simulations))], simulations[int(0.975 * len(simulations))]


def _record_fingerprint(record: dict[str, Any]) -> str:
    payload = {
        key: value for key, value in record.items()
        if key not in {"recorded_at", "revision", "source_fingerprint"}
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Corrupt shadow ledger line {line_number}: {exc}") from exc
    return records


def append_ledger(path: Path, records: list[dict[str, Any]]) -> dict[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    appended = unchanged = revised = 0
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        existing = []
        for line in handle:
            if line.strip():
                existing.append(json.loads(line))
        latest: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in existing:
            key = (row["model_version"], row["phase"], row["event_key"])
            if key not in latest or int(row.get("revision", 1)) >= int(latest[key].get("revision", 1)):
                latest[key] = row
        handle.seek(0, os.SEEK_END)
        for source in records:
            row = dict(source)
            key = (row["model_version"], row["phase"], row["event_key"])
            fingerprint = _record_fingerprint(row)
            previous = latest.get(key)
            if previous and previous.get("source_fingerprint") == fingerprint:
                unchanged += 1
                continue
            revision = int(previous.get("revision", 0)) + 1 if previous else 1
            row.update({
                "revision": revision,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "source_fingerprint": fingerprint,
            })
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            latest[key] = row
            appended += 1
            revised += int(previous is not None)
        handle.flush()
        os.fsync(handle.fileno())
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return {"appended": appended, "unchanged": unchanged, "revised": revised}


def _latest_records(path: Path, version: str) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for record in _read_ledger(path):
        if record.get("model_version") != version:
            continue
        key = (record["phase"], record["event_key"])
        if key not in latest or int(record.get("revision", 1)) >= int(latest[key].get("revision", 1)):
            latest[key] = record
    return sorted(latest.values(), key=lambda row: (row["date"], row["meeting_name"], row["race_number"]))


def _scope_payload(records: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "races": len(records),
        "class4_races": sum(int(record["is_target_class"]) for record in records),
        "meetings": len({record["meeting_name"] for record in records}),
        "venues": sorted({record["venue"] for record in records}),
        "baseline": _summarize(records, "baseline"),
        "variants": {},
    }
    for variant in config["variants"]:
        payload["variants"][variant] = {
            "metrics": _summarize(records, variant),
            "deltas": _deltas(records, variant),
            "top2_bootstrap_95_ci": _bootstrap_ci(records, variant),
        }
    return payload


def build_tracker(ledger: Path, config: dict[str, Any]) -> dict[str, Any]:
    records = _latest_records(ledger, config["version"])
    retrospective = [record for record in records if record["phase"] == "retrospective"]
    prospective = [record for record in records if record["phase"] == "prospective"]
    tracker = {
        "model_version": config["version"],
        "production_matrix_changed": False,
        "manual_approval_required": True,
        "ledger": str(ledger),
        "retrospective": _scope_payload(retrospective, config),
        "prospective": _scope_payload(prospective, config),
        "promotion_gate": config["promotion_gate"],
        "promotion": {},
    }
    gate = config["promotion_gate"]
    for variant in config["variants"]:
        scope = tracker["prospective"]
        row = scope["variants"][variant]
        delta = row["deltas"]
        ci = row["top2_bootstrap_95_ci"]
        venue_deltas = {}
        for venue in scope["venues"]:
            subset = [record for record in prospective if record["venue"] == venue]
            venue_deltas[venue] = _deltas(subset, variant).get("top2_individual_place_rate", 0.0)

        blocks = []
        nonnegative_blocks = 0
        for index in range(int(gate["time_blocks"])):
            start = (len(prospective) * index) // int(gate["time_blocks"])
            end = (len(prospective) * (index + 1)) // int(gate["time_blocks"])
            block_records = prospective[start:end]
            block_delta = _deltas(block_records, variant)
            passed = bool(block_records) and all(
                block_delta.get(key, -1.0) >= 0.0
                for key in ("top2_individual_place_rate", "both_top2_place_rate", "avg_top4_hits")
            )
            nonnegative_blocks += int(passed)
            blocks.append({"block": index + 1, "races": len(block_records), "deltas": block_delta, "nonnegative": passed})

        checks = {
            "minimum_prospective_races": scope["races"] >= gate["minimum_prospective_races"],
            "minimum_prospective_class4_races": scope["class4_races"] >= gate["minimum_prospective_class4_races"],
            "minimum_meetings": scope["meetings"] >= gate["minimum_meetings"],
            "minimum_venues": len(scope["venues"]) >= gate["minimum_venues"],
            "top1_no_material_regression": delta.get("top1_rate", -1.0) * 100 >= gate["top1_delta_floor_pp"],
            "top2_gain_target": delta.get("top2_individual_place_rate", -1.0) * 100 >= gate["top2_delta_target_pp"],
            "top2_ci_lower_bound": ci[0] * 100 >= gate["top2_ci_lower_floor_pp"],
            "both_top2_not_down": delta.get("both_top2_place_rate", -1.0) * 100 >= gate["both_top2_delta_floor_pp"],
            "avg_top4_not_down": delta.get("avg_top4_hits", -1.0) >= gate["avg_top4_hits_delta_floor"],
            "top4_all_not_down": delta.get("top4_all_rate", -1.0) * 100 >= gate["top4_all_delta_floor_pp"],
            "both_venues_nonnegative": len(venue_deltas) >= gate["minimum_venues"] and all(value >= 0 for value in venue_deltas.values()),
            "time_block_consistency": nonnegative_blocks >= gate["minimum_nonnegative_time_blocks"],
        }
        tracker["promotion"][variant] = {
            "checks": checks,
            "venue_top2_deltas": venue_deltas,
            "nonnegative_time_blocks": nonnegative_blocks,
            "blocks": blocks,
            "eligible_for_manual_review": bool(checks) and all(checks.values()),
            "auto_promote": False,
        }
    return tracker


def _pct(value: float) -> str:
    return f"{100 * value:.2f}%"


def render_tracker(tracker: dict[str, Any]) -> str:
    prospective = tracker["prospective"]
    retrospective = tracker["retrospective"]
    gate = tracker["promotion_gate"]
    lines = [
        "# HKJC Class 4 Structural Shadow Tracker", "",
        f"- Model: `{tracker['model_version']}`.",
        "- No odds, market movement or market ranking is used.",
        "- Production 7D matrix remains unchanged; promotion always requires manual approval.",
        f"- Retrospective: **{retrospective['races']} races** ({retrospective['class4_races']} Class 4).",
        f"- Prospective: **{prospective['races']}/{gate['minimum_prospective_races']} races** "
        f"({prospective['class4_races']}/{gate['minimum_prospective_class4_races']} Class 4).", "",
        "## Prospective KPI", "",
        "| Candidate | Top1 Δ | Top2 Δ | Top2 95% CI | Both Top2 Δ | Avg Top4 Δ | Top4 all Δ | Status |",
        "|---|---:|---:|---|---:|---:|---:|---|",
    ]
    for variant, row in prospective["variants"].items():
        delta = row["deltas"]
        ci = row["top2_bootstrap_95_ci"]
        promotion = tracker["promotion"][variant]
        lines.append(
            f"| {variant} | {100 * delta.get('top1_rate', 0):+.2f}pp "
            f"| {100 * delta.get('top2_individual_place_rate', 0):+.2f}pp "
            f"| [{100 * ci[0]:+.2f}pp, {100 * ci[1]:+.2f}pp] "
            f"| {100 * delta.get('both_top2_place_rate', 0):+.2f}pp "
            f"| {delta.get('avg_top4_hits', 0):+.3f} "
            f"| {100 * delta.get('top4_all_rate', 0):+.2f}pp "
            f"| {'READY FOR MANUAL REVIEW' if promotion['eligible_for_manual_review'] else 'SHADOW'} |"
        )
    lines.extend(["", "## Promotion checks", ""])
    for variant, promotion in tracker["promotion"].items():
        passed = sum(int(value) for value in promotion["checks"].values())
        lines.append(f"- `{variant}`: {passed}/{len(promotion['checks'])} checks passed; auto-promote = `false`.")
    lines.append("")
    return "\n".join(lines)


def render_meeting(payload: dict[str, Any], tracker: dict[str, Any] | None) -> str:
    summary = payload["summaries"]
    baseline = summary["baseline"]
    lines = [
        "# HKJC Class 4 Structural Shadow Forward Review", "",
        f"- Meeting: `{payload['meeting_name']}`; phase: **{payload['phase']}**.",
        f"- Frozen model: `{payload['model_version']}`.",
        "- No odds, market movement or market ranking is used.",
        "- Official 7D score and official ranking remain unchanged.",
        f"- Evaluated: **{baseline['races']} races**; skipped: **{len(payload['skipped_races'])}**.", "",
        "| KPI | Baseline | Primary | Challenger |",
        "|---|---:|---:|---:|",
    ]
    for key, label, formatter in (
        ("top1_rate", "Top1 win", _pct),
        ("top2_individual_place_rate", "Top2 individual place", _pct),
        ("both_top2_place_rate", "Both Top2 placed", _pct),
        ("avg_top4_hits", "Avg Top4 hits", lambda value: f"{value:.3f}"),
        ("top4_all_rate", "Top4 all three placed", _pct),
    ):
        lines.append(
            f"| {label} | {formatter(baseline.get(key, 0))} "
            f"| {formatter(summary['primary_full_support'].get(key, 0))} "
            f"| {formatter(summary['challenger_trackwork_variant'].get(key, 0))} |"
        )
    lines.extend(["", "## Race-level", "", "| Race | Class | Actual Top3 | Baseline Top2 | Primary Top2 | Challenger Top2 | T2 hits B/P/C | Top4 hits B/P/C |", "|---:|---|---|---|---|---|---|---|"])
    for record in payload["race_records"]:
        models = record["models"]
        lines.append(
            f"| {record['race_number']} | {record['race_class']} | {record['actual_top3']} "
            f"| {models['baseline']['top2']} | {models['primary_full_support']['top2']} "
            f"| {models['challenger_trackwork_variant']['top2']} "
            f"| {models['baseline']['top2_hits']}/{models['primary_full_support']['top2_hits']}/{models['challenger_trackwork_variant']['top2_hits']} "
            f"| {models['baseline']['top4_hits']}/{models['primary_full_support']['top4_hits']}/{models['challenger_trackwork_variant']['top4_hits']} |"
        )
    if payload.get("ledger_update"):
        update = payload["ledger_update"]
        lines.extend(["", f"- Ledger: appended {update['appended']}, revised {update['revised']}, unchanged {update['unchanged']}."])
    if tracker:
        prospective = tracker["prospective"]
        lines.extend(["", f"- Prospective progress: **{prospective['races']}/{tracker['promotion_gate']['minimum_prospective_races']} races**."])
    if payload["skipped_races"]:
        lines.extend(["", "## Skipped races", ""])
        lines.extend(f"- `{row['race_key']}`: {row['reason']}" for row in payload["skipped_races"])
    lines.append("")
    return "\n".join(lines)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def append_to_reflector_report(report_path: Path, payload: dict[str, Any], tracker: dict[str, Any] | None) -> None:
    if not report_path.exists():
        return
    baseline = payload["summaries"]["baseline"]
    primary = payload["summaries"]["primary_full_support"]
    prospective = tracker["prospective"] if tracker else {"races": 0}
    eligible = bool(tracker and tracker["promotion"]["primary_full_support"]["eligible_for_manual_review"])
    block = "\n".join([
        REPORT_START,
        "## Class 4 Structural Shadow",
        "",
        f"- Meeting Top2 individual place: baseline {_pct(baseline.get('top2_individual_place_rate', 0))} → primary {_pct(primary.get('top2_individual_place_rate', 0))}.",
        f"- Meeting Avg Top4 hits: baseline {baseline.get('avg_top4_hits', 0):.3f} → primary {primary.get('avg_top4_hits', 0):.3f}.",
        f"- Prospective tracker: **{prospective.get('races', 0)} races**; status: **{'READY FOR MANUAL REVIEW' if eligible else 'SHADOW'}**.",
        "- Production matrix unchanged; no market inputs used.",
        REPORT_END,
    ])
    text = report_path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(REPORT_START) + r".*?" + re.escape(REPORT_END), re.DOTALL)
    updated = pattern.sub(block, text) if pattern.search(text) else text.rstrip() + "\n\n" + block + "\n"
    _atomic_text(report_path, updated)


def _phase_for_date(date: str, config: dict[str, Any]) -> str:
    return "prospective" if date >= str(config["prospective_start"]) else "retrospective"


def run_meeting(
    meeting_dir: Path,
    results_file: Path,
    config_path: Path,
    model_path: Path,
    ledger_path: Path,
    tracker_json: Path,
    tracker_md: Path,
    reflector_report: Path | None = None,
    target_races: set[int] | None = None,
    update_ledger: bool = True,
) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    model = json.loads(model_path.read_text(encoding="utf-8"))
    date = meeting_date(meeting_dir)
    if not date:
        raise ValueError(f"Cannot infer meeting date from {meeting_dir.name}")
    raw, coverage = build_rows(
        [meeting_dir], [], results_index_override={date: results_file}
    )
    if target_races:
        raw = raw[raw["race_number"].astype(int).isin(target_races)].copy()
    if raw.empty:
        raise ValueError("No joined Logic/result rows available for shadow scoring")
    horse_rows, race_records, skipped = score_frame(raw, config, model)
    phase = _phase_for_date(date, config)
    summaries = {
        variant: _summarize(race_records, variant)
        for variant in ("baseline", *config["variants"].keys())
    }
    payload: dict[str, Any] = {
        "model_version": config["version"],
        "phase": phase,
        "meeting": str(meeting_dir.resolve()),
        "meeting_name": meeting_dir.name,
        "results_file": str(results_file.resolve()),
        "coverage": coverage,
        "summaries": summaries,
        "race_records": race_records,
        "skipped_races": skipped,
        "partial_run": bool(target_races),
        "production_matrix_changed": False,
        "market_features_used": [],
    }
    tracker = None
    if update_ledger and not target_races:
        ledger_records = [
            {
                **record,
                "model_version": config["version"],
                "phase": phase,
                "source": "hkjc_reflector",
                "results_file": str(results_file.resolve()),
            }
            for record in race_records
        ]
        payload["ledger_update"] = append_ledger(ledger_path, ledger_records)
        tracker = build_tracker(ledger_path, config)
        _atomic_json(tracker_json, tracker)
        _atomic_text(tracker_md, render_tracker(tracker))
    else:
        payload["ledger_update"] = None
        if tracker_json.exists():
            tracker = json.loads(tracker_json.read_text(encoding="utf-8"))

    _write_csv(meeting_dir / MEETING_CSV, horse_rows)
    _atomic_json(meeting_dir / MEETING_JSON, payload)
    _atomic_text(meeting_dir / MEETING_MD, render_meeting(payload, tracker))
    if reflector_report:
        append_to_reflector_report(reflector_report, payload, tracker)
    return {
        "review_path": str(meeting_dir / MEETING_MD),
        "review_json": str(meeting_dir / MEETING_JSON),
        "tracker_json": str(tracker_json) if tracker else None,
        "tracker_markdown": str(tracker_md) if tracker else None,
        "phase": phase,
        "races": len(race_records),
        "partial_run": bool(target_races),
        "ledger_updated": bool(update_ledger and not target_races),
    }


def _metrics_from_research_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in METRIC_KEYS}


def _bootstrap_period(
    baseline_rows: list[dict[str, Any]],
    primary_rows: list[dict[str, Any]],
    challenger_rows: list[dict[str, Any]],
    version: str,
    source: str,
) -> list[dict[str, Any]]:
    primary_map = {row["race_key"]: row for row in primary_rows}
    challenger_map = {row["race_key"]: row for row in challenger_rows}
    records = []
    for baseline in baseline_rows:
        race_key = baseline["race_key"]
        is_class4 = str(baseline["race_class"]).strip() == "Class 4"
        primary = primary_map[race_key] if is_class4 else baseline
        challenger = challenger_map[race_key] if is_class4 else baseline
        race_number = int(str(race_key).rsplit("::", 1)[-1])
        record = {
            "model_version": version,
            "phase": "retrospective",
            "source": source,
            "event_key": f"{baseline['date']}|{baseline['venue']}|{race_number}",
            "date": str(baseline["date"]),
            "meeting_name": str(baseline["meeting_name"]),
            "race_number": race_number,
            "venue": str(baseline["venue"]),
            "track": str(baseline["track"]),
            "course": str(baseline["course"]),
            "distance_num": int(baseline["distance_num"]),
            "race_class": str(baseline["race_class"]),
            "is_target_class": is_class4,
            "field_size": None,
            "actual_top3": [],
            "models": {
                "baseline": _metrics_from_research_row(baseline),
                "primary_full_support": _metrics_from_research_row(primary),
                "challenger_trackwork_variant": _metrics_from_research_row(challenger),
            },
        }
        records.append(record)
    return records


def bootstrap_research(
    discovery_report: Path,
    forward_report: Path,
    config_path: Path,
    ledger_path: Path,
    tracker_json: Path,
    tracker_md: Path,
) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    discovery = json.loads(discovery_report.read_text(encoding="utf-8"))
    forward = json.loads(forward_report.read_text(encoding="utf-8"))
    discovery_models = discovery["models"]
    forward_models = forward["scopes"]["full_113_races"]
    records = _bootstrap_period(
        discovery_models["baseline"]["race_rows"],
        discovery_models["support_tw20_variant10_prior10_rail10"]["race_rows"],
        discovery_models["support_tw20_variant10"]["race_rows"],
        config["version"],
        "retrospective_bootstrap_discovery",
    )
    records.extend(_bootstrap_period(
        forward_models["baseline"]["race_rows"],
        forward_models["candidate_b_trackwork_variant_prior_rail"]["race_rows"],
        forward_models["ablation_trackwork_variant"]["race_rows"],
        config["version"],
        "retrospective_bootstrap_forward",
    ))
    update = append_ledger(ledger_path, records)
    tracker = build_tracker(ledger_path, config)
    _atomic_json(tracker_json, tracker)
    _atomic_text(tracker_md, render_tracker(tracker))
    return {"records": len(records), "ledger_update": update, "tracker": tracker_json.as_posix()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HKJC market-free Class 4 structural shadow tracker")
    parser.add_argument("meeting_dir", nargs="?", type=Path)
    parser.add_argument("--results-file", type=Path)
    parser.add_argument("--reflector-report", type=Path)
    parser.add_argument("--race", action="append", type=int)
    parser.add_argument("--no-ledger", action="store_true")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--tracker-json", type=Path, default=DEFAULT_TRACKER_JSON)
    parser.add_argument("--tracker-md", type=Path, default=DEFAULT_TRACKER_MD)
    parser.add_argument("--freeze-model", type=Path, metavar="TRAINING_CSV")
    parser.add_argument("--bootstrap-research", action="store_true")
    parser.add_argument(
        "--discovery-report", type=Path,
        default=PROJECT_ROOT / "scratch" / "hkjc_structural_signal_research_corrected.json",
    )
    parser.add_argument(
        "--forward-report", type=Path,
        default=PROJECT_ROOT / "scratch" / "hkjc_top2_forward_validation.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = args.config.resolve()
    model = args.model.resolve()
    ledger = args.ledger.resolve()
    tracker_json = args.tracker_json.resolve()
    tracker_md = args.tracker_md.resolve()
    if args.freeze_model:
        output = freeze_model(args.freeze_model.resolve(), model, config)
        print(json.dumps({"model": str(output)}, ensure_ascii=False))
        return 0
    if args.bootstrap_research:
        result = bootstrap_research(
            args.discovery_report.resolve(), args.forward_report.resolve(), config,
            ledger, tracker_json, tracker_md,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if not args.meeting_dir or not args.results_file:
        raise SystemExit("meeting_dir and --results-file are required")
    result = run_meeting(
        args.meeting_dir.resolve(), args.results_file.resolve(), config, model,
        ledger, tracker_json, tracker_md,
        reflector_report=args.reflector_report.resolve() if args.reflector_report else None,
        target_races=set(args.race or []) or None,
        update_ledger=not args.no_ledger,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
