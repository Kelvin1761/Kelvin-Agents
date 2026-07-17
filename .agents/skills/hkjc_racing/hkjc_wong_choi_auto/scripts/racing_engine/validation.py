from __future__ import annotations

from pathlib import Path

from scoring import DEBUT_MATRIX_WEIGHTS, FEATURE_KEYS, MATRIX_WEIGHTS, compute_grade


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
        # 12字下限：判讀而家係濃縮實句（例如檔位可以一句講完），唔靠塞字數；
        # gate 只攔真空/爛輸出。
        if not text or len(text.strip()) < 12:
            errors.append(f"MATRIX-001 horse {horse_num} {key} missing narrative reasoning")

    ability = auto.get("ability_score")
    if not _in_range(ability):
        errors.append(f"SCORE-003 horse {horse_num} ability outside 0-100: {ability}")
    elif not auto.get("sip_flags"):
        reason_codes = auto.get("reason_codes", [])
        is_debut = any("debut" in code for code in reason_codes)
        
        if is_debut:
            expected = sum(float(matrix_scores.get(key, 60)) * weight for key, weight in DEBUT_MATRIX_WEIGHTS.items())
        else:
            expected = sum(float(matrix_scores.get(key, 60)) * weight for key, weight in MATRIX_WEIGHTS.items())
            
        if abs(float(ability) - expected) > 0.05:
            errors.append(f"SCORE-004 horse {horse_num} ability formula mismatch: {ability} != {expected:.2f}")
    if _in_range(ability) and auto.get("grade") != compute_grade(float(ability)):
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
    errors.extend(_validate_mainline_health_slot(horse_num, auto))
    readiness_shadow = ((auto.get("shadow_profiles") or {}).get("readiness_health_slot") or {})
    if readiness_shadow:
        errors.extend(_validate_readiness_shadow(horse_num, auto, readiness_shadow))
    legacy_shadow = ((auto.get("shadow_profiles") or {}).get("legacy_health_slot") or {})
    if legacy_shadow:
        errors.extend(_validate_legacy_health_shadow(horse_num, auto, legacy_shadow))
    return errors


def _validate_mainline_health_slot(horse_num: str, auto: dict) -> list[str]:
    errors = []
    profile = auto.get("health_slot_profile")
    detail = auto.get("health_slot_detail")
    if profile not in {"readiness_health_slot", "legacy_health_v2"}:
        return [f"HEALTH-001 horse {horse_num} invalid health_slot_profile"]
    if not isinstance(detail, dict):
        return [f"HEALTH-002 horse {horse_num} missing health_slot_detail"]
    for key in ("score", "raw_score", "legacy_horse_health"):
        if not _in_range(detail.get(key)):
            errors.append(f"HEALTH-003 horse {horse_num} {key} outside 0-100")
    try:
        reliability = float(detail.get("reliability"))
        evidence_count = int(detail.get("evidence_count"))
        raw_score = float(detail.get("raw_score"))
        readiness_score = float(detail.get("score"))
    except (TypeError, ValueError):
        errors.append(f"HEALTH-004 horse {horse_num} readiness detail invalid")
        return errors
    if evidence_count not in {0, 1, 2} or abs(reliability - evidence_count / 2.0) > 0.001:
        errors.append(f"HEALTH-005 horse {horse_num} readiness reliability mismatch")
    expected_readiness = 60.0 + reliability * (raw_score - 60.0)
    if abs(readiness_score - expected_readiness) > 0.01:
        errors.append(f"HEALTH-006 horse {horse_num} readiness shrink formula mismatch")
    matrix_health = float((auto.get("matrix_scores") or {}).get("horse_health", -1))
    selected = readiness_score if profile == "readiness_health_slot" else float(detail.get("legacy_horse_health", -2))
    if abs(matrix_health - selected) > 0.01:
        errors.append(f"HEALTH-007 horse {horse_num} mainline health slot mismatch")
    return errors


def _validate_readiness_shadow(horse_num: str, auto: dict, shadow: dict) -> list[str]:
    errors = []
    shadow_matrix = shadow.get("matrix_scores", {})
    if sorted(shadow_matrix) != sorted(MATRIX_KEYS):
        errors.append(f"SHADOW-001 horse {horse_num} readiness matrix keys mismatch")
        return errors
    for key in MATRIX_KEYS:
        if not _in_range(shadow_matrix.get(key)):
            errors.append(f"SHADOW-002 horse {horse_num} readiness matrix {key} outside 0-100")
    health_score = shadow.get("readiness_health_score")
    reliability = shadow.get("reliability")
    if not _in_range(health_score):
        errors.append(f"SHADOW-003 horse {horse_num} readiness health outside 0-100")
    try:
        reliability_value = float(reliability)
    except (TypeError, ValueError):
        reliability_value = -1.0
    if not 0.0 <= reliability_value <= 1.0:
        errors.append(f"SHADOW-004 horse {horse_num} readiness reliability outside 0-1")
    if _in_range(health_score) and abs(float(shadow_matrix.get("horse_health", -1)) - float(health_score)) > 0.01:
        errors.append(f"SHADOW-005 horse {horse_num} readiness health slot mismatch")
    mainline_matrix = auto.get("matrix_scores", {})
    for key in MATRIX_KEYS:
        if key == "horse_health":
            continue
        if abs(float(shadow_matrix.get(key, -1)) - float(mainline_matrix.get(key, -2))) > 0.01:
            errors.append(f"SHADOW-006 horse {horse_num} readiness changed non-health matrix {key}")
    reason_codes = auto.get("reason_codes", [])
    is_debut = any("debut" in code for code in reason_codes)
    weights = DEBUT_MATRIX_WEIGHTS if is_debut else MATRIX_WEIGHTS
    expected = sum(float(shadow_matrix.get(key, 60)) * weight for key, weight in weights.items())
    expected += sum(float(item.get("boost", 0) or 0) for item in shadow.get("sip_flags", []))
    ability = shadow.get("ability_score")
    if not _in_range(ability) or abs(float(ability) - expected) > 0.05:
        errors.append(f"SHADOW-007 horse {horse_num} readiness ability formula mismatch")
    if _in_range(ability) and shadow.get("grade") != compute_grade(float(ability)):
        errors.append(f"SHADOW-008 horse {horse_num} readiness grade mismatch")
    try:
        expected_delta = float(ability) - float(auto.get("ability_score"))
        actual_delta = float(shadow.get("ability_delta"))
        if abs(actual_delta - expected_delta) > 0.05:
            errors.append(f"SHADOW-009 horse {horse_num} readiness ability delta mismatch")
    except (TypeError, ValueError):
        errors.append(f"SHADOW-009 horse {horse_num} readiness ability delta invalid")
    return errors


def _validate_legacy_health_shadow(horse_num: str, auto: dict, shadow: dict) -> list[str]:
    errors = []
    shadow_matrix = shadow.get("matrix_scores", {})
    if sorted(shadow_matrix) != sorted(MATRIX_KEYS):
        return [f"SHADOW-010 horse {horse_num} legacy matrix keys mismatch"]
    mainline_matrix = auto.get("matrix_scores", {})
    for key in MATRIX_KEYS:
        if not _in_range(shadow_matrix.get(key)):
            errors.append(f"SHADOW-011 horse {horse_num} legacy matrix {key} outside 0-100")
        if key != "horse_health" and abs(float(shadow_matrix.get(key, -1)) - float(mainline_matrix.get(key, -2))) > 0.01:
            errors.append(f"SHADOW-012 horse {horse_num} legacy changed non-health matrix {key}")
    expected_health = float((auto.get("health_slot_detail") or {}).get("legacy_horse_health", -1))
    if abs(float(shadow_matrix.get("horse_health", -2)) - expected_health) > 0.01:
        errors.append(f"SHADOW-013 horse {horse_num} legacy health slot mismatch")
    reason_codes = auto.get("reason_codes", [])
    weights = DEBUT_MATRIX_WEIGHTS if any("debut" in code for code in reason_codes) else MATRIX_WEIGHTS
    expected = sum(float(shadow_matrix.get(key, 60)) * weight for key, weight in weights.items())
    expected += sum(float(item.get("boost", 0) or 0) for item in shadow.get("sip_flags", []))
    ability = shadow.get("ability_score")
    if not _in_range(ability) or abs(float(ability) - expected) > 0.05:
        errors.append(f"SHADOW-014 horse {horse_num} legacy ability formula mismatch")
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
