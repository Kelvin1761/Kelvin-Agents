#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
REFLECTOR_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"
ENGINE_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi_auto" / "scripts" / "racing_engine"
sys.path.insert(0, str(REFLECTOR_DIR))
sys.path.insert(0, str(ENGINE_DIR))

from review_auto_weighting import (  # noqa: E402
    build_results_index,
    default_results_roots,
    load_results,
    meeting_date,
    race_num_from_path,
    venue_from_meeting_dir,
)
from scoring import MATRIX_WEIGHTS, clip_score  # noqa: E402


DEBUT_WEIGHTS = {
    "trainer_signal": 0.30,
    "horse_health": 0.30,
    "race_shape": 0.20,
    "stability": 0.15,
    "class_advantage": 0.05,
}

REBALANCED_WEIGHTS = {
    "sectional": 0.1700,
    "trainer_signal": 0.1950,
    "stability": 0.1250,
    "race_shape": 0.2200,
    "class_advantage": 0.1200,
    "horse_health": 0.0650,
    "form_line": 0.1050,
}


def _as_float(value: object, default: float = 60.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _text_blob(horse: dict) -> str:
    parts: list[str] = []
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    for key in (
        "margin_trend",
        "trackwork_digest",
        "trackwork_health",
        "formline_strength",
        "jockey_combo_block",
        "weight_trend",
        "draw_position_fit",
    ):
        parts.append(str(data.get(key, "")))
    for key in ("core_logic", "best_distance", "last_6_finishes"):
        parts.append(str(horse.get(key, "")))
    return "\n".join(parts)


def _ability(matrix: dict[str, float], is_debut: bool, weights: dict[str, float] | None = None) -> float:
    active = DEBUT_WEIGHTS if is_debut else (weights or MATRIX_WEIGHTS)
    return round(sum(_as_float(matrix.get(key), 60.0) * weight for key, weight in active.items()), 4)


def _copy_matrix(auto: dict) -> dict[str, float]:
    return {key: clip_score(_as_float(value)) for key, value in (auto.get("matrix_scores") or {}).items()}


def _latent_upside_points(horse: dict, auto: dict) -> float:
    matrix = auto.get("matrix_scores") or {}
    features = auto.get("feature_scores") or {}
    text = _text_blob(horse)
    points = 0.0

    if _as_float(matrix.get("form_line")) >= 74:
        points += 1.2
    elif _as_float(matrix.get("form_line")) >= 70:
        points += 0.7
    if _as_float(matrix.get("trainer_signal")) >= 72:
        points += 0.9
    elif _as_float(matrix.get("trainer_signal")) >= 68:
        points += 0.45
    if _as_float(matrix.get("class_advantage")) >= 70:
        points += 0.65
    if _as_float(matrix.get("horse_health")) >= 68:
        points += 0.55
    if _as_float(features.get("weight_score")) >= 68:
        points += 0.35

    if "賽日騎師有參與操練" in text:
        points += 0.45
    if "試閘段速訊號強" in text or "trial_sectional_signal': 'strong" in text:
        points += 0.55
    if "收窄中" in text:
        points += 0.55
    elif "擴大中" in text:
        points -= 0.30

    last_finish = _as_int((horse.get("_data") or {}).get("last_finish") or "")
    if last_finish >= 8 and _as_float(matrix.get("form_line")) >= 70 and _as_float(matrix.get("horse_health")) >= 66:
        points += 0.75

    return max(0.0, min(points, 4.5))


def _risk_pressure_points(horse: dict, auto: dict) -> float:
    matrix = auto.get("matrix_scores") or {}
    features = auto.get("feature_scores") or {}
    text = _text_blob(horse)
    flags = set(auto.get("risk_flags") or [])
    points = 0.0

    if _as_float(matrix.get("race_shape")) < 58:
        points += 1.0
    if _as_float(matrix.get("sectional")) < 56:
        points += 0.8
    if _as_float(matrix.get("stability")) < 56:
        points += 0.7
    if _as_float(matrix.get("horse_health")) < 64:
        points += 0.7
    if _as_float(features.get("risk_score")) < 64:
        points += 0.8
    if _as_float(features.get("distance_score")) < 58:
        points += 0.6
    if _as_float(features.get("confidence_score")) < 76:
        points += 0.5
    if "trackwork_slowing" in flags or "操練放緩" in text:
        points += 0.45
    if "急劇變化" in text or "大減" in text or "大增" in text:
        points += 0.45

    return min(points, 4.0)


def current_matrix(horse: dict) -> tuple[float, dict[str, float]]:
    auto = horse["auto"]
    matrix = _copy_matrix(auto)
    return _ability(matrix, horse["is_debut"]), matrix


def latent_upside(horse: dict) -> tuple[float, dict[str, float]]:
    auto = horse["auto"]
    matrix = _copy_matrix(auto)
    points = _latent_upside_points(horse["raw"], auto)
    matrix["form_line"] = clip_score(matrix.get("form_line", 60.0) + points * 1.25)
    matrix["trainer_signal"] = clip_score(matrix.get("trainer_signal", 60.0) + points * 0.85)
    matrix["stability"] = clip_score(matrix.get("stability", 60.0) + points * 0.80)
    matrix["sectional"] = clip_score(matrix.get("sectional", 60.0) + points * 0.70)
    matrix["class_advantage"] = clip_score(matrix.get("class_advantage", 60.0) + points * 0.45)
    matrix["horse_health"] = clip_score(matrix.get("horse_health", 60.0) + points * 0.40)
    return _ability(matrix, horse["is_debut"]), matrix


def risk_gate(horse: dict) -> tuple[float, dict[str, float]]:
    auto = horse["auto"]
    matrix = _copy_matrix(auto)
    points = _risk_pressure_points(horse["raw"], auto)
    matrix["race_shape"] = clip_score(matrix.get("race_shape", 60.0) - points * 1.20)
    matrix["sectional"] = clip_score(matrix.get("sectional", 60.0) - points * 0.95)
    matrix["stability"] = clip_score(matrix.get("stability", 60.0) - points * 0.85)
    matrix["horse_health"] = clip_score(matrix.get("horse_health", 60.0) - points * 1.35)
    matrix["trainer_signal"] = clip_score(matrix.get("trainer_signal", 60.0) - points * 0.35)
    return _ability(matrix, horse["is_debut"]), matrix


def _race_shape_context_delta(horse: dict) -> float:
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    text = "\n".join(
        str(data.get(key, ""))
        for key in ("draw_position_fit", "position_window", "position_pi", "running_style")
    )
    delta = 0.0
    if "✅匹配" in text:
        delta += 4.0
    if "❌錯配" in text or "錯配!" in text:
        delta -= 8.0
    if "⚠️需主動切入" in text:
        delta -= 3.0
    if "上升軌" in text:
        delta += 2.0
    elif "衰退中" in text:
        delta -= 2.0
    if "信心: 高" in text:
        delta += 0.8
    elif "信心: 低" in text:
        delta -= 0.8

    recent = str(data.get("position_window", "")).split("|")[0]
    if "消耗=低消耗" in recent:
        delta += 1.0
    elif "消耗=極高消耗" in recent:
        delta -= 2.0
    elif "消耗=高消耗" in recent:
        delta -= 1.2
    return max(-10.0, min(7.0, delta))


def _draw_position_fit_score(horse: dict) -> float:
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    text = str(data.get("draw_position_fit", "")) + "\n" + str(data.get("position_pi", ""))
    score = 60.0
    if "✅匹配" in text:
        score += 12.0
    if "❌錯配" in text or "錯配!" in text:
        score -= 14.0
    if "⚠️需主動切入" in text:
        score -= 6.0
    if "上升軌" in text:
        score += 5.0
    elif "微升" in text:
        score += 2.0
    elif "衰退中" in text:
        score -= 5.0
    elif "微跌" in text:
        score -= 2.0
    return clip_score(score)


def _trip_consumption_score(horse: dict) -> float:
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    parts = str(data.get("position_window", "")).split("|")[:3]
    values = []
    for part in parts:
        if "消耗=低消耗" in part:
            values.append(70.0)
        elif "消耗=中低消耗" in part:
            values.append(66.0)
        elif "消耗=中等消耗" in part:
            values.append(60.0)
        elif "消耗=極高消耗" in part:
            values.append(46.0)
        elif "消耗=高消耗" in part:
            values.append(52.0)
    if not values:
        return 60.0
    return clip_score(sum(values) / len(values))


def race_shape_formula(horse: dict, draw_w: float, fit_w: float, trip_w: float) -> tuple[float, dict[str, float]]:
    auto = horse["auto"]
    matrix = _copy_matrix(auto)
    features = auto.get("feature_scores") or {}
    draw = _as_float(features.get("draw_score"), matrix.get("race_shape", 60.0))
    fit = _draw_position_fit_score(horse["raw"])
    trip = _trip_consumption_score(horse["raw"])
    matrix["race_shape"] = clip_score(draw * draw_w + fit * fit_w + trip * trip_w)
    return _ability(matrix, horse["is_debut"]), matrix


def race_shape_formula_55_25_20(horse: dict) -> tuple[float, dict[str, float]]:
    return race_shape_formula(horse, 0.55, 0.25, 0.20)


def race_shape_formula_50_30_20(horse: dict) -> tuple[float, dict[str, float]]:
    return race_shape_formula(horse, 0.50, 0.30, 0.20)


def race_shape_formula_60_25_15(horse: dict) -> tuple[float, dict[str, float]]:
    return race_shape_formula(horse, 0.60, 0.25, 0.15)


def race_shape_formula_45_35_20(horse: dict) -> tuple[float, dict[str, float]]:
    return race_shape_formula(horse, 0.45, 0.35, 0.20)


def venue_aware_race_shape(horse: dict) -> tuple[float, dict[str, float]]:
    venue = str(horse.get("race_venue") or "")
    if venue == "沙田":
        return race_shape_formula_55_25_20(horse)
    return race_shape_context(horse)


def race_shape_context(horse: dict) -> tuple[float, dict[str, float]]:
    auto = horse["auto"]
    matrix = _copy_matrix(auto)
    matrix["race_shape"] = clip_score(matrix.get("race_shape", 60.0) + _race_shape_context_delta(horse["raw"]))
    return _ability(matrix, horse["is_debut"]), matrix


def race_shape_rebalanced(horse: dict) -> tuple[float, dict[str, float]]:
    _, matrix = race_shape_context(horse)
    return _ability(matrix, horse["is_debut"], REBALANCED_WEIGHTS), matrix


def latent_plus_risk(horse: dict) -> tuple[float, dict[str, float]]:
    ability, matrix = latent_upside(horse)
    auto = horse["auto"]
    points = _risk_pressure_points(horse["raw"], auto)
    matrix["race_shape"] = clip_score(matrix.get("race_shape", 60.0) - points * 1.20)
    matrix["sectional"] = clip_score(matrix.get("sectional", 60.0) - points * 0.95)
    matrix["stability"] = clip_score(matrix.get("stability", 60.0) - points * 0.85)
    matrix["horse_health"] = clip_score(matrix.get("horse_health", 60.0) - points * 1.35)
    matrix["trainer_signal"] = clip_score(matrix.get("trainer_signal", 60.0) - points * 0.35)
    return _ability(matrix, horse["is_debut"]), matrix


def evidence_calibrated(horse: dict) -> tuple[float, dict[str, float]]:
    auto = horse["auto"]
    matrix = _copy_matrix(auto)
    features = auto.get("feature_scores") or {}
    confidence = _as_float(features.get("confidence_score"), 76.0)
    risk = _as_float(features.get("risk_score"), 66.0)
    shrink = 1.0
    if confidence < 76:
        shrink -= 0.12
    if risk < 64:
        shrink -= 0.12
    if _risk_pressure_points(horse["raw"], auto) >= 2.0:
        shrink -= 0.08
    shrink = max(0.70, shrink)
    for key, value in list(matrix.items()):
        matrix[key] = clip_score(60.0 + (value - 60.0) * shrink)
    return _ability(matrix, horse["is_debut"]), matrix


def rebalanced_weights(horse: dict) -> tuple[float, dict[str, float]]:
    auto = horse["auto"]
    matrix = _copy_matrix(auto)
    return _ability(matrix, horse["is_debut"], REBALANCED_WEIGHTS), matrix


def combined_rebalanced(horse: dict) -> tuple[float, dict[str, float]]:
    _, matrix = latent_plus_risk(horse)
    return _ability(matrix, horse["is_debut"], REBALANCED_WEIGHTS), matrix


def _top_n(ranked: list[tuple[int, float]], n: int) -> list[int]:
    return [horse for horse, _score in ranked[:n]]


def evaluate_race(horses: list[dict], actual_pos: dict[int, int], scorer: Callable[[dict], tuple[float, dict[str, float]]]) -> dict:
    scored = []
    deltas = []
    for horse in horses:
        score, matrix = scorer(horse)
        base_score, _ = current_matrix(horse)
        scored.append((horse["horse_num"], score, base_score, matrix))
        deltas.append(score - base_score)
    ranked_full = sorted(scored, key=lambda row: (-row[1], row[0]))
    ranked = [(horse_num, score) for horse_num, score, _base, _matrix in ranked_full]
    actual_top3 = [horse for horse, _pos in sorted(actual_pos.items(), key=lambda item: item[1])[:3]]
    actual_top3_set = set(actual_top3)
    winner = actual_top3[0]
    picks3 = _top_n(ranked, 3)
    picks5 = _top_n(ranked, 5)
    top2 = _top_n(ranked, 2)
    winner_rank = next((idx for idx, (horse, _score) in enumerate(ranked, start=1) if horse == winner), len(ranked) + 1)
    return {
        "picks": _top_n(ranked, 5),
        "top3_hits": sum(1 for horse in picks3 if horse in actual_top3_set),
        "top5_hits": sum(1 for horse in picks5 if horse in actual_top3_set),
        "top2_hits": sum(1 for horse in top2 if horse in actual_top3_set),
        "top2_both": all(horse in actual_top3_set for horse in top2) if len(top2) == 2 else False,
        "winner_top1": bool(picks3 and picks3[0] == winner),
        "winner_top3": winner in set(picks3),
        "winner_top5": winner in set(picks5),
        "winner_rank": winner_rank,
        "mrr": 1.0 / winner_rank if winner_rank else 0.0,
        "avg_delta": round(sum(deltas) / len(deltas), 4) if deltas else 0.0,
        "changed_horses": sum(1 for value in deltas if abs(value) >= 0.05),
    }


def summarize(results: list[dict]) -> dict:
    total = len(results)
    top2_dist = Counter(item["top2_hits"] for item in results)
    if total == 0:
        return {}
    return {
        "races": total,
        "gold_top3_3hits": sum(1 for item in results if item["top3_hits"] == 3),
        "top3_2plus": sum(1 for item in results if item["top3_hits"] >= 2),
        "top5_3plus": sum(1 for item in results if item["top5_hits"] == 3),
        "top5_2plus": sum(1 for item in results if item["top5_hits"] >= 2),
        "top2_both_in_top3": sum(1 for item in results if item["top2_both"]),
        "top2_zero": top2_dist.get(0, 0),
        "top2_one": top2_dist.get(1, 0),
        "winner_top1": sum(1 for item in results if item["winner_top1"]),
        "winner_top3": sum(1 for item in results if item["winner_top3"]),
        "winner_top5": sum(1 for item in results if item["winner_top5"]),
        "avg_winner_rank": round(sum(item["winner_rank"] for item in results) / total, 3),
        "mrr": round(sum(item["mrr"] for item in results) / total, 4),
        "avg_changed_horses": round(sum(item["changed_horses"] for item in results) / total, 3),
        "avg_score_delta": round(sum(item["avg_delta"] for item in results) / total, 4),
    }


def delta(candidate: dict, baseline: dict) -> dict:
    out = {}
    for key, value in candidate.items():
        if key == "races":
            continue
        base = baseline.get(key, 0)
        if isinstance(value, (int, float)) and isinstance(base, (int, float)):
            out[key] = round(value - base, 4)
    return out


def load_samples() -> tuple[list[dict], dict]:
    results_index = build_results_index(default_results_roots() + [ROOT])
    meetings = candidate_meeting_dirs()
    seen: set[tuple[str, str, int]] = set()
    samples: list[dict] = []
    skipped: defaultdict[str, int] = defaultdict(int)
    for meeting_dir in meetings:
        date = meeting_date(meeting_dir)
        if not date:
            skipped["no_date"] += 1
            continue
        result_path = results_index.get(date)
        if not result_path:
            skipped["no_result_file"] += 1
            continue
        venue = venue_from_meeting_dir(meeting_dir)
        all_results = load_results(result_path)
        for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json"), key=race_num_from_path):
            race_number = race_num_from_path(logic_path)
            key = (date, venue, race_number)
            if key in seen:
                skipped["duplicate_race"] += 1
                continue
            actual_pos = all_results.get(race_number)
            if not actual_pos:
                skipped["no_race_result"] += 1
                continue
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            horses = []
            for horse_num_text, horse in (logic.get("horses") or {}).items():
                horse_num = _as_int(horse_num_text, -1)
                auto = horse.get("python_auto") if isinstance(horse.get("python_auto"), dict) else {}
                if horse_num <= 0 or horse_num not in actual_pos or not auto.get("matrix_scores"):
                    continue
                horses.append(
                    {
                        "horse_num": horse_num,
                        "horse_name": horse.get("horse_name", ""),
                        "is_debut": bool(horse.get("is_debut") or horse.get("debut_runner") or horse.get("career_tag") == "DEBUT"),
                        "race_venue": venue,
                        "raw": horse,
                        "auto": auto,
                    }
                )
            if len(horses) < 4:
                skipped["too_few_horses"] += 1
                continue
            seen.add(key)
            samples.append(
                {
                    "meeting": meeting_dir.name,
                    "date": date,
                    "venue": venue,
                    "race_number": race_number,
                    "actual_pos": actual_pos,
                    "horses": horses,
                }
            )
    meta = {
        "meetings": len({sample["meeting"] for sample in samples}),
        "races": len(samples),
        "horses": sum(len(sample["horses"]) for sample in samples),
        "skipped": dict(skipped),
    }
    return samples, meta


def candidate_meeting_dirs() -> list[Path]:
    roots = [
        ROOT / "Archive_Race_Analysis" / "HK_Racing",
        ROOT / "meetings",
        ROOT,
    ]
    meetings: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        candidates = root.iterdir() if root != ROOT else root.glob("20*_ShaTin")
        for path in candidates:
            if not path.is_dir():
                continue
            name = path.name
            if "ShaTin" not in name and "HappyValley" not in name:
                continue
            if not any(path.glob("Race_*_Logic.json")):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            meetings.append(path)
    return sorted(meetings)


def run() -> dict:
    samples, meta = load_samples()
    scorers = {
        "current_matrix": current_matrix,
        "race_shape_formula_55_25_20": race_shape_formula_55_25_20,
        "race_shape_formula_50_30_20": race_shape_formula_50_30_20,
        "race_shape_formula_60_25_15": race_shape_formula_60_25_15,
        "race_shape_formula_45_35_20": race_shape_formula_45_35_20,
        "venue_aware_race_shape": venue_aware_race_shape,
        "race_shape_context": race_shape_context,
        "latent_upside": latent_upside,
        "risk_gate": risk_gate,
        "latent_plus_risk": latent_plus_risk,
        "evidence_calibrated": evidence_calibrated,
        "rebalanced_weights": rebalanced_weights,
        "race_shape_rebalanced": race_shape_rebalanced,
        "combined_rebalanced": combined_rebalanced,
    }
    scopes = {
        "all": lambda sample: True,
        "sha_tin": lambda sample: sample["venue"] == "沙田",
        "happy_valley": lambda sample: sample["venue"] == "跑馬地",
        "recent_2026_06_13": lambda sample: sample["date"] == "2026-06-13",
    }
    payload = {
        "meta": meta,
        "weights": {
            "current": MATRIX_WEIGHTS,
            "rebalanced": REBALANCED_WEIGHTS,
            "debut": DEBUT_WEIGHTS,
        },
        "scopes": {},
    }
    for scope_name, predicate in scopes.items():
        subset = [sample for sample in samples if predicate(sample)]
        if not subset:
            continue
        scope_payload = {}
        baseline_summary = None
        for model_name, scorer in scorers.items():
            race_results = [
                evaluate_race(sample["horses"], sample["actual_pos"], scorer)
                for sample in subset
            ]
            summary = summarize(race_results)
            entry = {"summary": summary}
            if model_name == "current_matrix":
                baseline_summary = summary
            elif baseline_summary is not None:
                entry["delta_vs_current"] = delta(summary, baseline_summary)
            scope_payload[model_name] = entry
        payload["scopes"][scope_name] = scope_payload
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="HKJC matrix-wide upside/risk shadow test.")
    parser.add_argument("--output", type=Path, default=ROOT / "scratch" / "hkjc_upside_risk_matrix_test.json")
    args = parser.parse_args()
    payload = run()
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
