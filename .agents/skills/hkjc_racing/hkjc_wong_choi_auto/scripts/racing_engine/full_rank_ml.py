"""Dependency-free, checksum-pinned Matrix+ML ranking for HKJC Auto.

The seven-dimension Matrix remains the official 0-100 ability and Grade source.
Official whole-field ordering blends 70% Matrix rank percentile with 30% of a
portable LambdaRank inference.  The portable artifact avoids requiring
LightGBM, sklearn, pandas or NumPy in the live HKJC pipeline.
"""

from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path

from scoring import MATRIX_WEIGHTS


RANKING_CONTRACT_VERSION = "HKJC_MATRIX_ANCHORED_LAMBDARANK_V1"
PORTABLE_SCHEMA_VERSION = "HKJC_PORTABLE_LGBM_RANKER_V1"
MODEL_SHA256 = "9397f5c67139a14920f36e13d9442220393a4be5cbe20c20a1484104055446a1"
SOURCE_JOBLIB_SHA256 = "8c8fc3a89f3df75e303bca26bb36e9fc3f2901cdd123ec90dc6c2ac67e72c9d8"
MATRIX_WEIGHT = 0.70
ML_WEIGHT = 0.30

PROJECT_ROOT = Path(__file__).resolve().parents[6]
MODEL_PATH = (
    PROJECT_ROOT
    / ".agents"
    / "skills"
    / "hkjc_racing"
    / "hkjc_reflector"
    / "artifacts"
    / "hkjc_full_rank_ml_program"
    / "models"
    / "matrix_anchored_lambdarank_portable.json"
)

MATRIX_COLUMNS = (
    "matrix_stability",
    "matrix_sectional",
    "matrix_race_shape",
    "matrix_trainer_signal",
    "matrix_horse_health",
    "matrix_form_line",
    "matrix_class_advantage",
)
RELATIVE_COLUMNS = tuple(f"rel_{column}" for column in MATRIX_COLUMNS)
MODEL_FEATURES = MATRIX_COLUMNS + RELATIVE_COLUMNS


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=1)
def load_model_bundle() -> dict:
    if not MODEL_PATH.is_file():
        raise RuntimeError(f"Full-rank ML artifact missing: {MODEL_PATH}")
    actual = _sha256(MODEL_PATH)
    if actual != MODEL_SHA256:
        raise RuntimeError(
            f"Full-rank ML checksum mismatch: expected {MODEL_SHA256}, got {actual}"
        )
    bundle = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    expected = {
        "schema_version": PORTABLE_SCHEMA_VERSION,
        "model_version": RANKING_CONTRACT_VERSION,
        "source_joblib_sha256": SOURCE_JOBLIB_SHA256,
        "features": list(MODEL_FEATURES),
        "average_output": False,
    }
    for key, value in expected.items():
        if bundle.get(key) != value:
            raise RuntimeError(f"Full-rank ML portable contract mismatch: {key}")
    feature_count = len(MODEL_FEATURES)
    for key in ("imputer_medians", "scaler_mean", "scaler_scale"):
        if len(bundle.get(key) or []) != feature_count:
            raise RuntimeError(f"Full-rank ML portable vector mismatch: {key}")
    if not bundle.get("trees"):
        raise RuntimeError("Full-rank ML portable artifact contains no trees")
    return bundle


def _horse_number_key(value: str):
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(value)


def _rank_percentiles(values: list[float]) -> list[float]:
    size = len(values)
    output = []
    for value in values:
        lower = sum(other < value for other in values)
        equal = sum(other == value for other in values)
        output.append((lower + (equal + 1.0) / 2.0) / size)
    return output


def _sample_zscores(values: list[float]) -> list[float]:
    if len(values) < 2:
        return [0.0] * len(values)
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    std = math.sqrt(variance)
    return [(value - mean) / std for value in values] if std else [0.0] * len(values)


def _matrix_base_ability(matrix_scores: dict) -> float:
    return float(
        sum(float(matrix_scores[key]) * weight for key, weight in MATRIX_WEIGHTS.items())
    )


def build_model_frame(horses: dict) -> tuple[list[str], list[dict[str, float]], list[float]]:
    horse_numbers = sorted((str(number) for number in horses), key=_horse_number_key)
    rows: list[dict[str, float]] = []
    matrix_abilities: list[float] = []
    for horse_number in horse_numbers:
        auto = (horses[horse_number] or {}).get("python_auto") or {}
        matrix_scores = auto.get("matrix_scores") or {}
        missing = [key for key in MATRIX_WEIGHTS if key not in matrix_scores]
        if missing:
            raise RuntimeError(
                f"Horse {horse_number} missing Matrix dimensions for ML ranking: {missing}"
            )
        rows.append({f"matrix_{key}": float(matrix_scores[key]) for key in MATRIX_WEIGHTS})
        matrix_abilities.append(_matrix_base_ability(matrix_scores))

    for column in MATRIX_COLUMNS:
        relative = _sample_zscores([row[column] for row in rows])
        for row, value in zip(rows, relative):
            row[f"rel_{column}"] = value
    return horse_numbers, rows, matrix_abilities


def _transform(bundle: dict, rows: list[dict[str, float]]) -> list[list[float]]:
    medians = bundle["imputer_medians"]
    means = bundle["scaler_mean"]
    scales = bundle["scaler_scale"]
    output = []
    for row in rows:
        transformed = []
        for index, feature in enumerate(MODEL_FEATURES):
            value = float(row.get(feature, medians[index]))
            if not math.isfinite(value):
                value = float(medians[index])
            scale = float(scales[index])
            transformed.append((value - float(means[index])) / scale if scale else 0.0)
        output.append(transformed)
    return output


def _tree_value(node: dict, row: list[float]) -> float:
    current = node
    while "leaf_value" not in current:
        if current.get("decision_type") != "<=":
            raise RuntimeError("Unsupported portable tree decision type")
        value = row[int(current["split_feature"])]
        go_left = bool(current.get("default_left")) if not math.isfinite(value) else value <= float(current["threshold"])
        current = current["left_child"] if go_left else current["right_child"]
    return float(current["leaf_value"])


def _predict_raw(bundle: dict, rows: list[list[float]]) -> list[float]:
    return [sum(_tree_value(tree, row) for tree in bundle["trees"]) for row in rows]


def apply_full_rank_ml(logic_data: dict) -> dict:
    horses = logic_data.get("horses") or {}
    if len(horses) < 2:
        raise RuntimeError("Full-rank ML requires at least two runners")
    bundle = load_model_bundle()
    horse_numbers, rows, matrix_ability = build_model_frame(horses)
    ml_raw = _predict_raw(bundle, _transform(bundle, rows))
    matrix_percentile = _rank_percentiles(matrix_ability)
    ml_percentile = _rank_percentiles(ml_raw)
    hybrid_score = [
        MATRIX_WEIGHT * matrix_rank
        + ML_WEIGHT * ml_rank
        + 1e-10 * ability
        for matrix_rank, ml_rank, ability in zip(
            matrix_percentile, ml_percentile, matrix_ability
        )
    ]
    matrix_by_horse = dict(zip(horse_numbers, matrix_ability))
    matrix_order = {
        horse_number: rank
        for rank, horse_number in enumerate(
            sorted(
                horse_numbers,
                key=lambda number: (-matrix_by_horse[number], _horse_number_key(number)),
            ),
            start=1,
        )
    }

    for index, horse_number in enumerate(horse_numbers):
        auto = horses[horse_number]["python_auto"]
        auto["rank_score"] = float(hybrid_score[index])
        auto["ranking_contract_id"] = RANKING_CONTRACT_VERSION
        auto["ranking_components"] = {
            "matrix_base_ability": round(float(matrix_ability[index]), 6),
            "matrix_rank": matrix_order[horse_number],
            "matrix_rank_percentile": round(float(matrix_percentile[index]), 12),
            "ml_raw_score": round(float(ml_raw[index]), 12),
            "ml_rank_percentile": round(float(ml_percentile[index]), 12),
            "matrix_weight": MATRIX_WEIGHT,
            "ml_weight": ML_WEIGHT,
        }

    contract = {
        "version": RANKING_CONTRACT_VERSION,
        "mode": "matrix_ml_hybrid",
        "matrix_weight": MATRIX_WEIGHT,
        "ml_weight": ML_WEIGHT,
        "model_sha256": MODEL_SHA256,
        "source_joblib_sha256": SOURCE_JOBLIB_SHA256,
        "portable_schema": PORTABLE_SCHEMA_VERSION,
        "feature_scope": "matrix_7d_absolute_plus_race_relative",
        "features": list(MODEL_FEATURES),
        "ability_and_grade_source": "frozen_7d_matrix",
        "ranking_source": "within_race_percentile_blend",
        "market_free": True,
    }
    logic_data["python_auto_ranking_contract"] = contract
    return contract
