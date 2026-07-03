from __future__ import annotations

from pathlib import Path

from scoring import FEATURE_KEYS, MATRIX_WEIGHTS, compute_grade


MATRIX_KEYS = tuple(MATRIX_WEIGHTS.keys())


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
    for horse_num, horse in horses.items():
        auto = horse.get("python_auto")
        if not isinstance(auto, dict):
            errors.append(f"SCHEMA-001 horse {horse_num} missing python_auto")
            continue
        errors.extend(_validate_auto_namespace(str(horse_num), auto))
    verdict = logic_data.get("python_auto_verdict")
    if not isinstance(verdict, dict):
        errors.append("VERDICT-001 missing python_auto_verdict")
    return errors


def _validate_auto_namespace(horse_num: str, auto: dict) -> list[str]:
    errors = []
    features = auto.get("feature_scores", {})
    missing = sorted(set(FEATURE_KEYS) - set(features))
    if missing:
        errors.append(f"SCHEMA-002 horse {horse_num} missing feature scores: {missing}")
    matrix_scores = auto.get("matrix_scores", {})
    if sorted(matrix_scores.keys()) != sorted(MATRIX_KEYS):
        errors.append(f"SCHEMA-003 horse {horse_num} matrix_scores keys mismatch")
    ability = auto.get("ability_score")
    base_7d = auto.get("base_7d_score")
    if ability is None:
        errors.append(f"SCORE-001 horse {horse_num} missing ability score")
    else:
        expected = sum(float(matrix_scores.get(key, 60)) * weight for key, weight in MATRIX_WEIGHTS.items())
        expected_score = float(base_7d if base_7d is not None else ability)
        if abs(expected_score - expected) > 0.06:
            errors.append(f"SCORE-002 horse {horse_num} clean 7D mismatch: {expected_score:.2f} != {expected:.2f}")
        # ability_score = pure 7D + wet_form_feature (0 on dry going, folded in on Soft/Heavy)
        wet_feat = float(auto.get("wet_form_feature", 0) or 0)
        if abs(float(ability) - (expected + wet_feat)) > 0.06:
            errors.append(f"SCORE-004 horse {horse_num} ability != clean 7D + wet_form: {float(ability):.2f} != {expected + wet_feat:.2f}")
        if auto.get("grade") != compute_grade(float(ability)):
            errors.append(f"SCORE-003 horse {horse_num} grade mismatch")
    if len(str(auto.get("core_logic", "")).strip()) < 40:
        errors.append(f"NLG-001 horse {horse_num} core_logic too short")
    return errors
