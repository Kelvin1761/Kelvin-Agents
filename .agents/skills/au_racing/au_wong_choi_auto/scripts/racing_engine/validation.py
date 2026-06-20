from __future__ import annotations

from pathlib import Path

from scoring import FEATURE_KEYS, MATRIX_WEIGHTS, compute_grade, get_dynamic_matrix_weights


MATRIX_KEYS = tuple(MATRIX_WEIGHTS.keys())
GENERIC_REPORT_PHRASES = (
    "資料不足，中性處理",
    "分析中",
    "待補",
    "[FILL]",
)


def validate_engine_scripts(script_root: Path) -> list[str]:
    errors = []
    for path in sorted(script_root.rglob("*.py")):
        if "__pycache__" in path.parts or path.name == "validation.py":
            continue
        text = path.read_text(encoding="utf-8")
        if " = \"[FILL]\"" in text or " = '[FILL]'" in text:
            errors.append(f"ENGINE-001 placeholder remains in {path}")
    return errors


def validate_logic_data(logic_data: dict) -> list[str]:
    errors = []
    horses = logic_data.get("horses", {})
    race_context = logic_data.get("race_analysis", {})
    dynamic_weights = get_dynamic_matrix_weights(race_context)
    scored = []
    for horse_num, horse in horses.items():
        auto = horse.get("python_auto")
        if not isinstance(auto, dict):
            errors.append(f"SCHEMA-001 horse {horse_num} missing python_auto")
            continue
        scored.append((str(horse_num), auto))
        errors.extend(_validate_auto_namespace(str(horse_num), auto, dynamic_weights))
    verdict = logic_data.get("python_auto_verdict")
    if not isinstance(verdict, dict):
        errors.append("VERDICT-001 missing python_auto_verdict")
    return errors


def validate_report_output(text: str) -> list[str]:
    issues = []
    for phrase in GENERIC_REPORT_PHRASES:
        if phrase in text:
            issues.append(f"REPORT-001 forbidden phrase remains: {phrase}")
    return issues


def _validate_auto_namespace(horse_num: str, auto: dict, dynamic_weights: dict = None) -> list[str]:
    errors = []
    features = auto.get("feature_scores", {})
    missing = sorted(set(FEATURE_KEYS) - set(features))
    if missing:
        errors.append(f"SCHEMA-002 horse {horse_num} missing feature scores: {missing}")
    matrix_scores = auto.get("matrix_scores", {})
    if sorted(matrix_scores.keys()) != sorted(MATRIX_KEYS):
        errors.append(f"SCHEMA-003 horse {horse_num} matrix_scores keys mismatch")
    ability = auto.get("ability_score")
    weights = dynamic_weights if dynamic_weights else MATRIX_WEIGHTS
    if ability is None:
        errors.append(f"SCORE-001 horse {horse_num} missing ability score")
    else:
        expected = sum(float(matrix_scores.get(key, 60)) * weight for key, weight in weights.items())
        # Diversity bonus: +2.0 for horses with no section below 56
        min_section = min(float(matrix_scores.get(k, 60)) for k in MATRIX_KEYS)
        if min_section >= 56:
            expected += 2.0
        # Barrier-bias adjustment is folded into ability_score by the engine and
        # persisted separately; account for it so the check matches the real formula.
        expected += float(auto.get("barrier_bias", 0) or 0)
        if abs(float(ability) - expected) > 0.06:
            errors.append(f"SCORE-002 horse {horse_num} ability mismatch: {ability} != {expected:.2f}")
        if auto.get("grade") != compute_grade(float(ability)):
            errors.append(f"SCORE-003 horse {horse_num} grade mismatch")
    if len(str(auto.get("core_logic", "")).strip()) < 40:
        errors.append(f"NLG-001 horse {horse_num} core_logic too short")
    return errors
