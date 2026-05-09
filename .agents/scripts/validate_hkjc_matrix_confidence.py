#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from racing_content_guard import scan_text_for_dummy


HKJC_DIMS = [
    "stability",
    "sectional",
    "race_shape",
    "trainer_signal",
    "horse_health",
    "form_line",
    "class_advantage",
]
CORE_SEMI = {"stability", "sectional", "race_shape", "trainer_signal"}
AUX = {"horse_health", "form_line", "class_advantage"}
CORE_SCORES = {"✅✅", "✅", "➖", "❌", "❌❌"}
AUX_SCORES = {"✅", "➖", "❌"}
CONF_ORDER = {"Unknown": 0, "Low": 1, "Medium": 2, "High": 3}
LEGACY_8D_KEYS = {
    "distance_fit", "gear_distance", "gear_and_distance",
    "裝備與距離", "距離適性", "gearDistance",
}
GENERIC_EVIDENCE = [
    "具備一定競爭力", "值得留意", "有望爭勝", "不容忽視",
    "實力不俗", "表現平穩", "近期走勢", "狀態有待觀察",
    "可爭一席", "尚算理想", "仍有機會", "good profile",
    "looks suitable", "positive setup", "strong chance",
]
CONCRETE_ANCHORS = [
    "L400", "L600", "完成時間偏差", "距離", "班次", "檔位", "負磅",
    "騎師", "練馬師", "晨操", "體重", "健康", "對手後續", "沿途位",
    "走位", "XW", "日期", "場次",
]
RACE_SHAPE_BANNED = [
    "predicted_pace", "expected_pace", "步速預測", "預計步速",
    "快步速", "慢步速", "pace collapse", "speed map",
]
RACE_SHAPE_ANCHORS = [
    "檔", "barrier", "draw", "XW", "沿途位", "走位", "外疊",
    "塞車", "遮擋", "內欄", "外檔", "wide", "cover",
]
GRADE_ORDER = ["S+", "S", "S-", "A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D"]


def _rules() -> dict:
    path = Path(__file__).resolve().parent.parent / "skills" / "hkjc_racing" / "hkjc_wong_choi" / "config" / "hkjc_matrix_trigger_rules.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _score(item: dict) -> str:
    return str(item.get("score", "")).strip()


def _confidence_ok(actual: str, minimum: str) -> bool:
    return CONF_ORDER.get(actual, -1) >= CONF_ORDER.get(minimum, 99)


def _evidence_list(item: dict) -> list[str]:
    ev = item.get("trigger_evidence", [])
    return ev if isinstance(ev, list) else []


def _text_blob(value) -> str:
    if isinstance(value, list):
        return " ".join(str(x) for x in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "")


def _is_debut(horse_entry: dict) -> bool:
    if horse_entry.get("debut_runner") or horse_entry.get("is_debut"):
        return True
    if str(horse_entry.get("career_tag", "")).upper() == "DEBUT":
        return True
    try:
        return int(horse_entry.get("career_race_starts", horse_entry.get("hk_starts", 999))) == 0
    except (TypeError, ValueError):
        return False


def validate_hkjc_matrix_confidence(horse_entry: dict) -> list[str]:
    errors: list[str] = []
    matrix = horse_entry.get("matrix")
    if not isinstance(matrix, dict):
        return ["matrix missing or not dict"]

    missing = [dim for dim in HKJC_DIMS if dim not in matrix]
    if missing:
        errors.append(f"missing HKJC matrix dimensions: {missing}")
    legacy = sorted(set(matrix) & LEGACY_8D_KEYS)
    if legacy:
        errors.append(f"legacy 8D matrix keys are not allowed: {legacy}")

    rules = _rules()
    for dim in HKJC_DIMS:
        item = matrix.get(dim)
        if not isinstance(item, dict):
            errors.append(f"matrix.{dim} missing or not dict")
            continue
        for field in ("score", "confidence", "trigger_rule", "trigger_evidence", "reasoning"):
            if field not in item:
                errors.append(f"matrix.{dim}.{field} missing")
        score = _score(item)
        confidence = str(item.get("confidence", "")).strip()
        trigger_rule = str(item.get("trigger_rule", "")).strip()
        evidence = _evidence_list(item)
        reasoning = str(item.get("reasoning", ""))
        blob = _text_blob(evidence) + " " + reasoning

        allowed_scores = CORE_SCORES if dim in CORE_SEMI else AUX_SCORES
        if confidence not in CONF_ORDER:
            errors.append(f"matrix.{dim}.confidence invalid: {confidence}")
        if score not in allowed_scores:
            errors.append(f"matrix.{dim}.score invalid for dimension: {score}")
        if dim in AUX and score in {"✅✅", "❌❌"}:
            errors.append(f"matrix.{dim} auxiliary dimension cannot use {score}")
        rule = rules.get(dim, {}).get(trigger_rule)
        if not rule:
            errors.append(f"matrix.{dim}.trigger_rule unknown: {trigger_rule}")
        else:
            if rule.get("score") != score:
                errors.append(f"matrix.{dim}.trigger_rule score mismatch: {trigger_rule}={rule.get('score')} actual={score}")
            if not _confidence_ok(confidence, rule.get("min_confidence", "High")):
                errors.append(f"matrix.{dim}.confidence {confidence} below rule minimum {rule.get('min_confidence')}")
            if len(evidence) < int(rule.get("min_evidence_count", 1)):
                errors.append(f"matrix.{dim}.trigger_evidence count {len(evidence)} below {rule.get('min_evidence_count')}")
        if not isinstance(item.get("trigger_evidence"), list):
            errors.append(f"matrix.{dim}.trigger_evidence must be list")
        if score in {"✅", "✅✅"} and confidence in {"Low", "Unknown"}:
            errors.append(f"matrix.{dim} positive score cannot use {confidence} confidence")
        if score == "✅✅" and confidence != "High":
            errors.append(f"matrix.{dim} ✅✅ requires High confidence")
        for issue in scan_text_for_dummy(blob):
            errors.append(f"matrix.{dim} {issue}")
        if any(p.lower() in blob.lower() for p in GENERIC_EVIDENCE):
            errors.append(f"matrix.{dim} generic evidence phrase detected")
        if evidence and not any(any(anchor.lower() in str(ev).lower() for anchor in CONCRETE_ANCHORS) for ev in evidence):
            errors.append(f"matrix.{dim}.trigger_evidence has no concrete anchor")

    sectional_blob = _text_blob(matrix.get("sectional", {}))
    if _score(matrix.get("sectional", {})) == "✅✅" and re.search(r"trial-only|試閘|晨操", sectional_blob, re.I):
        if not re.search(r"L400|L600|正式賽|formal race", sectional_blob, re.I):
            errors.append("matrix.sectional ✅✅ cannot be trial-only or trackwork-only")

    trainer = matrix.get("trainer_signal", {})
    trainer_blob = _text_blob(trainer)
    if _score(trainer) == "✅✅" and re.search(r"名氣|famous|star jockey|潘頓|莫雷拉|布文", trainer_blob, re.I):
        if not re.search(r"部署|晨操|配備|練馬師|勝率|位率|組合|deployment|gear|trainer", trainer_blob, re.I):
            errors.append("matrix.trainer_signal ✅✅ cannot rely only on famous jockey")

    form_line = matrix.get("form_line", {})
    if _score(form_line) == "✅" and not re.search(r"對手後續|follow-up|subsequent|後續", _text_blob(form_line), re.I):
        errors.append("matrix.form_line ✅ requires opponent follow-up evidence")

    fine_tune = _text_blob(horse_entry.get("fine_tune", {}))
    if _score(matrix.get("class_advantage", {})) == "✅" and re.search(r"class|weight|班|負磅|級數", fine_tune, re.I):
        errors.append("matrix.class_advantage ✅ cannot be reused for fine_tune upgrade")

    shape_blob = _text_blob(matrix.get("race_shape", {}))
    if any(p.lower() in shape_blob.lower() for p in RACE_SHAPE_BANNED):
        errors.append("matrix.race_shape cannot use predicted pace / speed map evidence")
    if not any(anchor.lower() in shape_blob.lower() for anchor in RACE_SHAPE_ANCHORS):
        errors.append("matrix.race_shape requires draw/trip anchor")

    return errors


def _grade_idx(grade: str) -> int:
    return GRADE_ORDER.index(grade) if grade in GRADE_ORDER else len(GRADE_ORDER)


def _cap_grade(grade: str, cap: str) -> str:
    return cap if _grade_idx(grade) < _grade_idx(cap) else grade


def apply_hkjc_matrix_caps(final_grade: str, horse_entry: dict) -> tuple[str, list[str]]:
    notes: list[str] = []
    grade = final_grade
    matrix = horse_entry.get("matrix", {}) if isinstance(horse_entry, dict) else {}

    def apply(cap: str, reason: str) -> None:
        nonlocal grade
        new_grade = _cap_grade(grade, cap)
        if new_grade != grade:
            notes.append(f"{reason}: {grade}->{new_grade}")
            grade = new_grade

    race_shape = matrix.get("race_shape", {})
    sectional = _score(matrix.get("sectional", {}))
    if _score(race_shape) == "❌❌":
        apply("B+", "race_shape ❌❌ cap")
    if _score(race_shape) == "❌" and sectional not in {"✅", "✅✅"}:
        apply("A-", "race_shape ❌ without sectional support cap")
    health_blob = _text_blob(matrix.get("horse_health", {}))
    if _score(matrix.get("horse_health", {})) == "❌" and re.search(r"未解決|unresolved|red flag|流鼻血|喘鳴|跛", health_blob, re.I):
        apply("B", "unresolved medical red flag cap")
    stability_blob = _text_blob(matrix.get("stability", {}))
    if _score(matrix.get("stability", {})) == "❌❌" and not re.search(r"寬恕|forgive|forgiveness", stability_blob, re.I):
        apply("B+", "stability ❌❌ no forgiveness cap")
    if _is_debut(horse_entry):
        apply("A", "debut runner cap")
    if str(matrix.get("sectional", {}).get("confidence", "")) == "Unknown":
        apply("A+", "sectional Unknown cannot be S-tier")
    if str(matrix.get("trainer_signal", {}).get("confidence", "")) in {"Low", "Unknown"}:
        apply("A+", "trainer_signal Low/Unknown cannot be S-tier")

    horse_entry["rating_cap_notes"] = notes
    return grade, notes


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("json_file")
    parser.add_argument("horse")
    args = parser.parse_args()
    data = json.loads(Path(args.json_file).read_text(encoding="utf-8"))
    errs = validate_hkjc_matrix_confidence(data.get("horses", {}).get(str(args.horse), {}))
    for err in errs:
        print(err)
    raise SystemExit(1 if errs else 0)
