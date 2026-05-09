#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

from racing_content_guard import scan_text_for_dummy


AU_DIMS = ["stability", "sectional", "race_shape", "jockey_trainer", "class_weight", "track", "form_line"]
CORE_SEMI = {"stability", "sectional", "race_shape", "jockey_trainer"}
AUX = {"class_weight", "track", "form_line"}
CORE_SCORES = {"✅✅", "✅", "➖", "❌", "❌❌"}
AUX_SCORES = {"✅", "➖", "❌"}
CONF_ORDER = {"Unknown": 0, "Low": 1, "Medium": 2, "High": 3}
GENERIC_EVIDENCE = [
    "具備一定競爭力", "值得留意", "有望爭勝", "不容忽視",
    "實力不俗", "表現平穩", "近期走勢", "狀態有待觀察",
    "可爭一席", "尚算理想", "仍有機會", "good profile",
    "looks suitable", "positive setup", "strong chance",
]
CONCRETE_ANCHORS = [
    "L400", "L600", "距離", "班次", "Barrier", "Draw", "Gate",
    "負磅", "Weight", "Jockey", "Trainer", "騎師", "練馬師",
    "日期", "場次", "BM", "Good", "Soft", "Heavy", "trial", "正式賽",
]


def _rules() -> dict:
    path = Path(__file__).resolve().parent.parent / "skills" / "au_racing" / "au_wong_choi" / "config" / "au_matrix_trigger_rules.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _score(item: dict) -> str:
    return str(item.get("score", "")).strip()


def _confidence_ok(actual: str, minimum: str) -> bool:
    return CONF_ORDER.get(actual, -1) >= CONF_ORDER.get(minimum, 99)


def _evidence_min_for_score(score: str) -> int:
    return {"✅✅": 4, "✅": 2, "➖": 1, "❌": 2, "❌❌": 3}.get(score, 1)


def _blob(value) -> str:
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return " ".join(str(x) for x in value)
    return str(value or "")


def validate_au_matrix_confidence(horse_entry: dict) -> list[str]:
    errors: list[str] = []
    matrix = horse_entry.get("matrix")
    if not isinstance(matrix, dict):
        return ["matrix missing or not dict"]

    missing = [dim for dim in AU_DIMS if dim not in matrix]
    if missing:
        errors.append(f"missing AU matrix dimensions: {missing}")

    rules = _rules()
    for dim in AU_DIMS:
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
        evidence = item.get("trigger_evidence", [])
        evidence_list = evidence if isinstance(evidence, list) else []
        blob = _blob(item)

        allowed = CORE_SCORES if dim in CORE_SEMI else AUX_SCORES
        if confidence not in CONF_ORDER:
            errors.append(f"matrix.{dim}.confidence invalid: {confidence}")
        if score not in allowed:
            errors.append(f"matrix.{dim}.score invalid for dimension: {score}")
        if dim in AUX and score in {"✅✅", "❌❌"}:
            errors.append(f"matrix.{dim} auxiliary dimension cannot use {score}")
        if not isinstance(evidence, list):
            errors.append(f"matrix.{dim}.trigger_evidence must be list")

        rule = rules.get(dim, {}).get(trigger_rule)
        if not rule:
            errors.append(f"matrix.{dim}.trigger_rule unknown: {trigger_rule}")
        else:
            if rule.get("score") != score:
                errors.append(f"matrix.{dim}.trigger_rule score mismatch: {trigger_rule}={rule.get('score')} actual={score}")
            if not _confidence_ok(confidence, rule.get("min_confidence", "High")):
                errors.append(f"matrix.{dim}.confidence {confidence} below rule minimum {rule.get('min_confidence')}")

        min_ev = _evidence_min_for_score(score)
        if len(evidence_list) < min_ev:
            errors.append(f"matrix.{dim}.trigger_evidence count {len(evidence_list)} below {min_ev}")
        if confidence in {"Low", "Unknown"} and score in {"✅", "✅✅"}:
            errors.append(f"matrix.{dim} positive score cannot use {confidence} confidence")
        if score == "✅✅" and confidence != "High":
            errors.append(f"matrix.{dim} ✅✅ requires High confidence")
        for issue in scan_text_for_dummy(blob):
            errors.append(f"matrix.{dim} {issue}")
        if any(p.lower() in blob.lower() for p in GENERIC_EVIDENCE):
            errors.append(f"matrix.{dim} generic evidence phrase detected")
        if evidence_list and not any(any(anchor.lower() in str(ev).lower() for anchor in CONCRETE_ANCHORS) for ev in evidence_list):
            errors.append(f"matrix.{dim}.trigger_evidence has no concrete anchor")

    sectional = matrix.get("sectional", {})
    sectional_blob = _blob(sectional)
    if _score(sectional) == "✅✅" and re.search(r"trial-only|trial only|試閘", sectional_blob, re.I):
        if not re.search(r"formal race|正式賽|L400|L600", sectional_blob, re.I):
            errors.append("matrix.sectional ✅✅ cannot be trial-only")

    return errors


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("json_file")
    parser.add_argument("horse")
    args = parser.parse_args()
    data = json.loads(Path(args.json_file).read_text(encoding="utf-8"))
    errs = validate_au_matrix_confidence(data.get("horses", {}).get(str(args.horse), {}))
    for err in errs:
        print(err)
    raise SystemExit(1 if errs else 0)
