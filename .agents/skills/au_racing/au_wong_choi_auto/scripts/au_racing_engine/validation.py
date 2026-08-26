from __future__ import annotations

from pathlib import Path

from .matrix_mapper import MATRIX_KEYS
from .scoring import (
    FEATURE_KEYS,
    MATRIX_ABILITY_SCALE,
    MATRIX_WEIGHTS,
    compute_grade,
)
from .source_alignment import normalize_horse_name


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
    if not isinstance(horses, dict) or not horses:
        return ["SCHEMA-000 horses must be a non-empty object"]
    normalized_names: dict[str, str] = {}
    for horse_num, horse in horses.items():
        if not isinstance(horse, dict):
            errors.append(f"SCHEMA-004 horse {horse_num} must be an object")
            continue
        declared_number = horse.get("horse_number")
        if declared_number is not None and str(declared_number) != str(horse_num):
            errors.append(
                f"ALIGN-001 horse key {horse_num} disagrees with horse_number "
                f"{declared_number}"
            )
        name_key = normalize_horse_name(horse.get("horse_name"))
        if not name_key:
            errors.append(f"ALIGN-002 horse {horse_num} has no usable name")
        elif name_key in normalized_names:
            errors.append(
                f"ALIGN-003 duplicate horse name for {normalized_names[name_key]} "
                f"and {horse_num}"
            )
        else:
            normalized_names[name_key] = str(horse_num)
        auto = horse.get("python_auto")
        if not isinstance(auto, dict):
            errors.append(f"SCHEMA-001 horse {horse_num} missing python_auto")
            continue
        errors.extend(_validate_auto_namespace(str(horse_num), auto))
    verdict = logic_data.get("python_auto_verdict")
    if not isinstance(verdict, dict):
        errors.append("VERDICT-001 missing python_auto_verdict")
    elif len(verdict.get("ranking") or []) != len(horses):
        errors.append("VERDICT-002 ranking count does not match horse count")
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
        # ⚠️ 一定要跟 `engine_core` 條 ability 公式。2026-08-26 加咗
        # `MATRIX_ABILITY_SCALE`（抵銷 pace_perf gain 修正之後嘅權重歸一），
        # 而呢度係條式喺 repo 嘅**第六份複本** —— 當時漏咗改，於是每次跑
        # orchestrator 都會逐匹馬報 SCORE-002 / SCORE-004。
        # `檢查.sh` 唔會跑 orchestrator，所以 golden 同單元測試都捉唔到。
        # 改任何一份就要六份一齊改：engine_core、au_eval ×2、au_matrix_refit ×2、
        # golden_scoring、同呢度。
        expected = 60.0 + (
            sum(float(matrix_scores.get(key, 60)) * weight
                for key, weight in MATRIX_WEIGHTS.items()) - 60.0
        ) / MATRIX_ABILITY_SCALE
        expected_score = float(base_7d if base_7d is not None else ability)
        if abs(expected_score - expected) > 0.06:
            errors.append(f"SCORE-002 horse {horse_num} clean six-dimension mismatch: {expected_score:.2f} != {expected:.2f}")
        # Legacy pure_7d field = matrix dimensions; wet form and locked exact-
        # class proof are explicit field-relative ranking overlays.
        wet_feat = float(auto.get("wet_form_feature", 0) or 0)
        class_feat = float(auto.get("proven_class_feature", 0) or 0)
        if abs(float(ability) - (expected + wet_feat + class_feat)) > 0.06:
            errors.append(
                f"SCORE-004 horse {horse_num} ability != clean matrix + wet_form "
                f"+ proven_class: {float(ability):.2f} != "
                f"{expected + wet_feat + class_feat:.2f}"
            )
        if auto.get("grade") != compute_grade(float(ability)):
            errors.append(f"SCORE-003 horse {horse_num} grade mismatch")
    if len(str(auto.get("core_logic", "")).strip()) < 40:
        errors.append(f"NLG-001 horse {horse_num} core_logic too short")
    return errors
