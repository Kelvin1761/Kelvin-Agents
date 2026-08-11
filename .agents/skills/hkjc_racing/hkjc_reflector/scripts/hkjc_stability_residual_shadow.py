#!/usr/bin/env python3
"""Run the frozen HKJC stability-residual model as a non-production shadow.

The runner reads already-scored ``Race_*_Logic.json`` files and writes separate
CSV/JSON diagnostics.  It never edits Logic JSON, Auto analysis, Auto scoring,
mainline rank, grade, verdict, or pick status.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from scipy.special import expit, logit


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL = (
    SCRIPT_DIR.parent
    / "artifacts"
    / "hkjc_dimension_ml_program"
    / "models"
    / "stability-win-residual.joblib"
)
MODEL_VERSION = "HKJC_STABILITY_RESIDUAL_SHADOW_V1"
MODEL_SHA256 = "c6928b9dfbf7e19bc5493e708512fb207be15dd0e6bbe5c2cf53ea88b8472b12"
EXPECTED_CAP = 0.05
EXPECTED_TARGET = "Win"
EXPECTED_DIMENSION = "stability"
EXPECTED_FEATURES = [
    "matrix_stability",
    "rel_matrix_stability",
    "feat_form_score",
    "feat_consistency_score",
    "feat_trackwork_trend_score",
    "last6_runs",
    "last6_mean_finish",
    "last6_best_finish",
    "last6_worst_finish",
    "last6_top3_count",
    "last6_top5_count",
    "days_since_last",
    "tw_entries_count",
    "tw_gallop_count",
    "tw_flags_count",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="Scored Race_X_Logic.json or meeting folder")
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--output-dir", default=None)
    parser.add_argument(
        "--results-file",
        default=None,
        help="Optional post-race results JSON; never used for shadow scoring",
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        number = float(value)
        return None if math.isnan(number) else number
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group(0)) if match else None


def _horse_number_sort(value: object) -> tuple[int, str]:
    text = str(value)
    try:
        return int(text), text
    except ValueError:
        return 10**9, text


def _race_file_sort(path: Path) -> tuple[int, str]:
    match = re.search(r"Race_(\d+)_Logic\.json$", path.name, re.I)
    return (int(match.group(1)) if match else 10**9, path.name)


def _parse_last_finishes(value: object) -> list[int]:
    tokens = value if isinstance(value, list) else re.findall(r"\d+", str(value or ""))
    finishes = []
    for token in tokens:
        number = _coerce_float(token)
        if number is not None and 1 <= number <= 99:
            finishes.append(int(round(number)))
    return finishes[:6]


def _last_finish_features(value: object) -> dict[str, float | int | None]:
    finishes = _parse_last_finishes(value)
    if not finishes:
        return {
            "last6_runs": 0,
            "last6_mean_finish": None,
            "last6_best_finish": None,
            "last6_worst_finish": None,
            "last6_top3_count": 0,
            "last6_top5_count": 0,
        }
    return {
        "last6_runs": len(finishes),
        "last6_mean_finish": round(sum(finishes) / len(finishes), 4),
        "last6_best_finish": min(finishes),
        "last6_worst_finish": max(finishes),
        "last6_top3_count": sum(finish <= 3 for finish in finishes),
        "last6_top5_count": sum(finish <= 5 for finish in finishes),
    }


def _trackwork_features(value: object) -> dict[str, float | None]:
    if not isinstance(value, dict):
        return {
            "tw_entries_count": None,
            "tw_gallop_count": None,
            "tw_flags_count": None,
        }
    entries = value.get("entries") or []
    flags = value.get("flags") or []
    gallops = (
        sum(
            isinstance(entry, dict) and entry.get("type") == "gallop"
            for entry in entries
        )
        if isinstance(entries, list)
        else 0
    )
    return {
        "tw_entries_count": float(len(entries)) if isinstance(entries, list) else None,
        "tw_gallop_count": float(gallops),
        "tw_flags_count": float(len(flags)) if isinstance(flags, list) else None,
    }


def _feature_row(horse_number: str, horse: dict[str, Any]) -> dict[str, Any]:
    auto = horse.get("python_auto") if isinstance(horse, dict) else None
    if not isinstance(auto, dict) or not auto:
        raise ValueError(
            f"Horse {horse_number} has no python_auto; run HKJC Auto before the shadow"
        )
    matrix = auto.get("matrix_scores") or {}
    features = auto.get("feature_scores") or {}
    derived = auto.get("derived_feature_scores") or {}
    stability = _coerce_float(matrix.get("stability"))
    ability = _coerce_float(auto.get("ability_score"))
    stored_rank = _coerce_float(auto.get("rank"))
    if stability is None or ability is None or stored_rank is None:
        raise ValueError(
            f"Horse {horse_number} is missing mainline stability/ability/rank"
        )
    row = {
        "horse_number": str(horse_number),
        "horse_name": str(horse.get("horse_name") or ""),
        "mainline_ability": ability,
        "stored_mainline_rank": int(round(stored_rank)),
        "matrix_stability": stability,
        "feat_form_score": _coerce_float(features.get("form_score")),
        "feat_consistency_score": _coerce_float(features.get("consistency_score")),
        "feat_trackwork_trend_score": _coerce_float(
            derived.get("trackwork_trend_score")
        ),
        "days_since_last": _coerce_float(horse.get("days_since_last")),
    }
    row.update(_last_finish_features(horse.get("last_6_finishes")))
    row.update(_trackwork_features(horse.get("trackwork")))
    return row


def build_feature_frame(logic: dict[str, Any]) -> pd.DataFrame:
    horses = logic.get("horses") or {}
    if not isinstance(horses, dict) or not horses:
        raise ValueError("Logic JSON contains no horses")
    rows = [
        _feature_row(str(horse_number), horse)
        for horse_number, horse in sorted(
            horses.items(), key=lambda item: _horse_number_sort(item[0])
        )
    ]
    frame = pd.DataFrame(rows)
    stability = pd.to_numeric(frame["matrix_stability"], errors="coerce")
    std = float(stability.std(ddof=1))
    frame["rel_matrix_stability"] = (
        (stability - float(stability.mean())) / std
        if std > 0 and not math.isnan(std)
        else 0.0
    )
    return frame


def load_frozen_model(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    checksum = _sha256(path)
    if checksum != MODEL_SHA256:
        raise ValueError(
            f"Frozen stability model checksum mismatch: {checksum} != {MODEL_SHA256}"
        )
    payload = joblib.load(path)
    if payload.get("dimension") != EXPECTED_DIMENSION:
        raise ValueError("Model dimension is not frozen stability")
    if payload.get("target") != EXPECTED_TARGET:
        raise ValueError("Model target is not frozen Win")
    if list(payload.get("features") or []) != EXPECTED_FEATURES:
        raise ValueError("Model feature contract mismatch")
    if abs(float(payload.get("cap")) - EXPECTED_CAP) > 1e-12:
        raise ValueError("Model cap contract mismatch")
    residual = payload.get("residual_model") or {}
    if not {"preprocessor", "coefficients"}.issubset(residual):
        raise ValueError("Portable residual model is incomplete")
    return payload


def apply_shadow_model(
    frame: pd.DataFrame, payload: dict[str, Any]
) -> pd.DataFrame:
    features = list(payload["features"])
    baseline_model = payload["baseline_calibrator"]
    baseline_raw = baseline_model.predict_proba(
        frame[["mainline_ability"]].rename(
            columns={"mainline_ability": "current_live_recomputed_ability"}
        )
    )[:, 1]
    baseline_probability = baseline_raw / baseline_raw.sum()

    residual = payload["residual_model"]
    transformed = np.asarray(
        residual["preprocessor"].transform(frame[features]), dtype=float
    )
    raw_delta = transformed @ np.asarray(residual["coefficients"], dtype=float)
    bounded_delta = np.clip(raw_delta, -EXPECTED_CAP, EXPECTED_CAP)
    adjusted = expit(
        logit(np.clip(baseline_probability, 1e-6, 1 - 1e-6)) + bounded_delta
    )
    shadow_probability = adjusted / adjusted.sum()

    output = frame.copy()
    output["mainline_win_probability"] = baseline_probability
    output["raw_logit_delta"] = raw_delta
    output["bounded_logit_delta"] = bounded_delta
    output["shadow_win_probability"] = shadow_probability
    output = _assign_ranks(output, "mainline_win_probability", "mainline_rank")
    if not (
        output["stored_mainline_rank"].astype(int)
        == output["mainline_rank"].astype(int)
    ).all():
        raise ValueError(
            "Stored mainline rank does not match ability order; refusing shadow comparison"
        )
    output = _assign_ranks(output, "shadow_win_probability", "shadow_rank")
    output["rank_delta"] = output["mainline_rank"] - output["shadow_rank"]
    output["entered_top2"] = (
        (output["mainline_rank"] > 2) & (output["shadow_rank"] <= 2)
    )
    output["exited_top2"] = (
        (output["mainline_rank"] <= 2) & (output["shadow_rank"] > 2)
    )
    output["model_version"] = MODEL_VERSION
    return output.sort_values("shadow_rank").reset_index(drop=True)


def _assign_ranks(frame: pd.DataFrame, probability: str, rank: str) -> pd.DataFrame:
    output = frame.copy()
    order = sorted(
        range(len(output)),
        key=lambda index: (
            -float(output.iloc[index][probability]),
            _horse_number_sort(output.iloc[index]["horse_number"]),
        ),
    )
    ranks = np.empty(len(output), dtype=int)
    for position, index in enumerate(order, start=1):
        ranks[index] = position
    output[rank] = ranks
    return output


def _race_number(logic: dict[str, Any], path: Path) -> str:
    value = (logic.get("race_analysis") or {}).get("race_number")
    if value not in (None, ""):
        return str(value)
    match = re.search(r"Race_(\d+)", path.name, re.I)
    return match.group(1) if match else ""


def score_logic_file(path: Path, payload: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    before = _sha256(path)
    logic = json.loads(path.read_text(encoding="utf-8"))
    frame = apply_shadow_model(build_feature_frame(logic), payload)
    after = _sha256(path)
    if before != after:
        raise RuntimeError("Shadow runner modified its Logic input")
    race_number = _race_number(logic, path)
    frame.insert(0, "race_number", race_number)
    base_top2 = frame.sort_values("mainline_rank").head(2)["horse_number"].tolist()
    shadow_top2 = frame.sort_values("shadow_rank").head(2)["horse_number"].tolist()
    summary = {
        "race_number": race_number,
        "source_file": path.name,
        "base_top2": base_top2,
        "shadow_top2": shadow_top2,
        "top2_changed": set(base_top2) != set(shadow_top2),
        "entered_top2": frame.loc[frame["entered_top2"], "horse_number"].tolist(),
        "exited_top2": frame.loc[frame["exited_top2"], "horse_number"].tolist(),
    }
    return frame, summary


def _load_results(path: Path | None) -> dict[str, dict[str, int]]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    output: dict[str, dict[str, int]] = {}
    for race_number, race in payload.items():
        positions = {}
        for row in (race or {}).get("results", []):
            position = _coerce_float(row.get("pos"))
            horse_number = row.get("horse_no")
            if position is not None and horse_number not in (None, ""):
                positions[str(horse_number)] = int(position)
        if positions:
            output[str(race_number)] = positions
    return output


def _attach_result_evaluation(
    frame: pd.DataFrame,
    summaries: list[dict[str, Any]],
    results: dict[str, dict[str, int]],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    output = frame.copy()
    output["finish_pos"] = [
        results.get(str(row.race_number), {}).get(str(row.horse_number))
        for row in output.itertuples(index=False)
    ]
    evaluated = []
    for summary in summaries:
        positions = results.get(str(summary["race_number"]), {})
        if not positions:
            continue
        actual_top3 = {
            horse_number for horse_number, position in positions.items() if position <= 3
        }
        base_hits = len(actual_top3 & set(summary["base_top2"]))
        shadow_hits = len(actual_top3 & set(summary["shadow_top2"]))
        evaluated.append(
            {
                "race_number": summary["race_number"],
                "actual_top3": sorted(actual_top3, key=_horse_number_sort),
                "base_top2_hits": base_hits,
                "shadow_top2_hits": shadow_hits,
                "top2_hit_delta": shadow_hits - base_hits,
                "outcome": (
                    "helped"
                    if shadow_hits > base_hits
                    else "harmed"
                    if shadow_hits < base_hits
                    else "unchanged"
                ),
            }
        )
    aggregate = {
        "evaluated_races": len(evaluated),
        "helped": sum(item["outcome"] == "helped" for item in evaluated),
        "harmed": sum(item["outcome"] == "harmed" for item in evaluated),
        "unchanged": sum(item["outcome"] == "unchanged" for item in evaluated),
        "race_evaluation": evaluated,
    }
    return output, aggregate


def run_shadow(
    target: Path,
    model_path: Path = DEFAULT_MODEL,
    output_dir: Path | None = None,
    results_path: Path | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    payload = load_frozen_model(model_path)
    if target.is_dir():
        logic_files = sorted(target.glob("Race_*_Logic.json"), key=_race_file_sort)
        prefix = "HKJC"
        destination = output_dir or target
    else:
        logic_files = [target]
        prefix = re.sub(r"_Logic$", "", target.stem)
        destination = output_dir or target.parent
    if not logic_files:
        raise ValueError(f"No Race_*_Logic.json found under {target}")
    destination.mkdir(parents=True, exist_ok=True)

    frames = []
    summaries = []
    for logic_path in logic_files:
        frame, summary = score_logic_file(logic_path, payload)
        frames.append(frame)
        summaries.append(summary)
    combined = pd.concat(frames, ignore_index=True)
    evaluation: dict[str, Any] = {"evaluated_races": 0}
    if results_path is not None:
        combined, evaluation = _attach_result_evaluation(
            combined, summaries, _load_results(results_path)
        )

    csv_path = destination / f"{prefix}_Stability_Residual_Shadow.csv"
    json_path = destination / f"{prefix}_Stability_Residual_Shadow.json"
    combined.to_csv(csv_path, index=False, encoding="utf-8-sig")
    report = {
        "model_version": MODEL_VERSION,
        "model_sha256": _sha256(model_path),
        "contract": {
            "dimension": EXPECTED_DIMENSION,
            "target": EXPECTED_TARGET,
            "cap": EXPECTED_CAP,
            "features": EXPECTED_FEATURES,
            "mainline_modified": False,
            "ranking_authority": "shadow_only",
        },
        "races": summaries,
        "evaluation": evaluation,
    }
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return csv_path, json_path, report


def main() -> int:
    args = parse_args()
    csv_path, json_path, report = run_shadow(
        Path(args.target).resolve(),
        Path(args.model).resolve(),
        Path(args.output_dir).resolve() if args.output_dir else None,
        Path(args.results_file).resolve() if args.results_file else None,
    )
    print(f"shadow_csv={csv_path}")
    print(f"shadow_json={json_path}")
    print(
        json.dumps(
            {
                "model_version": report["model_version"],
                "races": len(report["races"]),
                "top2_changed": sum(race["top2_changed"] for race in report["races"]),
                "mainline_modified": report["contract"]["mainline_modified"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
