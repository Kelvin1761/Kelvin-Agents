from __future__ import annotations

from pathlib import Path

from scoring import FEATURE_KEYS, MATRIX_WEIGHTS, compute_grade


FORBIDDEN_SCRIPT_TERMS = (
    "openai",
    "anthropic",
    "gemini",
    "google.generativeai",
    "litellm",
    "ollama",
    "fair_odds",
    "kelly",
    "pace_score",
    "leader_score",
    "on_pace_score",
    "backmarker_score",
)

GENERIC_REPORT_PHRASES = (
    "由相關 12 項分數映射",
    "Neutral Jockey",
    "Neutral Trainer",
    "Inside Draw",
    "Outside Draw",
    "Middle Draw",
)

MATRIX_KEYS = tuple(MATRIX_WEIGHTS.keys())


def validate_engine_scripts(script_root: Path) -> list[str]:
    errors = []
    for path in sorted(script_root.rglob("*.py")):
        if "__pycache__" in path.parts or path.name == "validation.py":
            continue
        text = path.read_text(encoding="utf-8").lower()
        for term in FORBIDDEN_SCRIPT_TERMS:
            if term in text:
                errors.append(f"ENGINE-001 forbidden term `{term}` in {path}")
    return errors


def validate_logic_data(logic_data: dict) -> list[str]:
    errors = []
    horses = logic_data.get("horses", {})
    scored = []
    for horse_num, horse in horses.items():
        auto = horse.get("python_auto")
        if not isinstance(auto, dict):
            errors.append(f"SCHEMA-001 horse {horse_num} missing python_auto")
            continue
        scored.append((str(horse_num), auto))
        errors.extend(_validate_auto_namespace(str(horse_num), auto))
    errors.extend(_validate_verdict(logic_data, scored))
    return errors


def validate_report_output(text: str) -> list[str]:
    return [f"REPORT-002 generic or raw phrase remains: {phrase}" for phrase in GENERIC_REPORT_PHRASES if phrase in text]


def _validate_auto_namespace(horse_num: str, auto: dict) -> list[str]:
    errors = []
    features = auto.get("feature_scores", {})
    missing = sorted(set(FEATURE_KEYS) - set(features))
    if missing:
        errors.append(f"SCHEMA-002 horse {horse_num} missing feature scores: {missing}")
    for key in FEATURE_KEYS:
        score = features.get(key)
        if not _in_range(score):
            errors.append(f"SCORE-001 horse {horse_num} {key} outside 0-100: {score}")

    matrix_scores = auto.get("matrix_scores", {})
    matrix_reasoning = auto.get("matrix_reasoning", {})
    if sorted(matrix_scores) != sorted(MATRIX_KEYS):
        errors.append(f"SCHEMA-003 horse {horse_num} matrix_scores keys mismatch")
    for key in MATRIX_KEYS:
        score = matrix_scores.get(key)
        if not _in_range(score):
            errors.append(f"SCORE-002 horse {horse_num} matrix {key} outside 0-100: {score}")
        reasoning = matrix_reasoning.get(key) if isinstance(matrix_reasoning, dict) else None
        text = reasoning.get("text") if isinstance(reasoning, dict) else ""
        if not text or len(text.strip()) < 24:
            errors.append(f"MATRIX-001 horse {horse_num} {key} missing narrative reasoning")

    ability = auto.get("ability_score")
    if not _in_range(ability):
        errors.append(f"SCORE-003 horse {horse_num} ability outside 0-100: {ability}")
    elif not auto.get("sip_flags"):
        expected = sum(float(matrix_scores.get(key, 60)) * weight for key, weight in MATRIX_WEIGHTS.items())
        if abs(float(ability) - expected) > 0.05:
            errors.append(f"SCORE-004 horse {horse_num} ability formula mismatch: {ability} != {expected:.2f}")
    if auto.get("grade") != compute_grade(float(ability)):
        errors.append(f"SCORE-005 horse {horse_num} grade mismatch")

    core_logic = str(auto.get("core_logic") or "")
    if len(core_logic.strip()) < 40:
        errors.append(f"NLG-001 horse {horse_num} core_logic too short")
    if "|" in core_logic or any(phrase in core_logic for phrase in GENERIC_REPORT_PHRASES):
        errors.append(f"NLG-002 horse {horse_num} core_logic still raw/generic")
    if "[FILL" in core_logic.upper():
        errors.append(f"NLG-003 horse {horse_num} core_logic contains placeholder")

    if not isinstance(auto.get("score_provenance"), dict):
        errors.append(f"SCHEMA-004 horse {horse_num} missing score_provenance")
    return errors


def _validate_verdict(logic_data: dict, scored: list[tuple[str, dict]]) -> list[str]:
    verdict = logic_data.get("python_auto_verdict")
    if not isinstance(verdict, dict):
        return ["VERDICT-001 missing python_auto_verdict"]
    errors = []
    ranked = verdict.get("ranking", [])
    ordered_pairs = [
        (
            float(item.get("rank_score", item.get("ability_score", -1))),
            float(item.get("ability_score", -1)),
            str(item.get("horse_number", "")),
        )
        for item in ranked
    ]
    if ordered_pairs != sorted(ordered_pairs, key=lambda item: (-item[0], -item[1], _horse_number_sort_key(item[2]))):
        errors.append("VERDICT-002 ranking not sorted by rank_score/ability_score")
    expected_top4 = [
        num
        for num, _auto in sorted(
            scored,
            key=lambda item: (
                -float(item[1].get("rank_score", item[1].get("ability_score", 0))),
                -float(item[1].get("ability_score", 0)),
                _horse_number_sort_key(item[0]),
            ),
        )[:4]
    ]
    actual_top4 = [str(item.get("horse_number")) for item in verdict.get("top4", [])]
    if actual_top4 != expected_top4:
        errors.append(f"VERDICT-003 top4 mismatch: {actual_top4} != {expected_top4}")
    return errors


def _in_range(value) -> bool:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return 0 <= numeric <= 100


def _horse_number_sort_key(value: str):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value
