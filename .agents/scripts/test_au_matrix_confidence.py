#!/usr/bin/env python3
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".agents" / "scripts"))

from validate_au_matrix_confidence import validate_au_matrix_confidence


RULES = {
    "stability": ("STAB_POS_01", "✅"),
    "sectional": ("SEC_POS_01", "✅"),
    "race_shape": ("SHAPE_POS_01", "✅"),
    "jockey_trainer": ("JT_POS_01", "✅"),
    "class_weight": ("CW_POS_01", "✅"),
    "track": ("TRACK_POS_01", "✅"),
    "form_line": ("FL_POS_01", "✅"),
}


def ok(expr):
    assert expr


def dim(rule, score, confidence="High", evidence=None, reasoning=None):
    return {
        "score": score,
        "confidence": confidence,
        "trigger_rule": rule,
        "trigger_evidence": evidence or ["L400 22.59 日期 2026-04-01", "Barrier 3 BM70"],
        "disqualifiers": [],
        "reasoning": reasoning or "正式賽 L400 與 BM 班次支持。",
    }


def valid_horse():
    return {
        "horse_name": "Valid",
        "core_logic": "real",
        "matrix": {k: dim(rule, score) for k, (rule, score) in RULES.items()},
    }


def check(name, fn):
    try:
        fn()
        print(f"PASS {name}")
    except Exception as exc:
        print(f"FAIL {name}: {exc}")
        raise


def has_err(h, text):
    return any(text in e for e in validate_au_matrix_confidence(h))


def _mut(dim_name, score=None, rule=None, confidence=None, evidence=None, reasoning=None):
    h = copy.deepcopy(valid_horse())
    item = h["matrix"][dim_name]
    if score is not None:
        item["score"] = score
    if rule is not None:
        item["trigger_rule"] = rule
    if confidence is not None:
        item["confidence"] = confidence
    if evidence is not None:
        item["trigger_evidence"] = evidence
    if reasoning is not None:
        item["reasoning"] = reasoning
    return h


def _drop(field):
    h = valid_horse()
    del h["matrix"]["sectional"][field]
    return h


def main():
    check("valid full 7D passes", lambda: ok(not validate_au_matrix_confidence(valid_horse())))
    check("sectional ✅✅ High passes", _sectional_strong)
    check("sectional ✅✅ Medium fails", lambda: ok(has_err(_mut("sectional", score="✅✅", rule="SEC_STRONG_01", confidence="Medium"), "✅✅ requires High")))
    check("sectional ✅ Low fails", lambda: ok(has_err(_mut("sectional", confidence="Low"), "positive score")))
    check("class_weight ✅✅ fails", lambda: ok(has_err(_mut("class_weight", score="✅✅", rule="CW_POS_01"), "invalid")))
    check("missing confidence fails", lambda: ok(has_err(_drop("confidence"), "confidence missing")))
    check("missing trigger_rule fails", lambda: ok(has_err(_drop("trigger_rule"), "trigger_rule missing")))
    check("rule score mismatch fails", lambda: ok(has_err(_mut("sectional", score="❌", rule="SEC_POS_01"), "score mismatch")))
    check("generic evidence fails", lambda: ok(has_err(_mut("sectional", evidence=["具備一定競爭力"]), "generic")))
    check("trial-only sectional ✅✅ fails", lambda: ok(has_err(_mut("sectional", score="✅✅", rule="SEC_STRONG_01", evidence=["trial-only barrier 3", "trial only BM", "試閘 日期", "試閘 Trainer"], reasoning="trial-only 試閘"), "trial-only")))
    check("valid debut form_line neutral passes", _debut_neutral)


def _sectional_strong():
    h = _mut("sectional", score="✅✅", rule="SEC_STRONG_01", confidence="High", evidence=[
        "formal race L400 22.59", "L600 34.10 similar distance",
        "BM70 class par clear", "race shape supports engine Barrier 3",
    ], reasoning="formal race sectional above par, no interference.")
    assert not validate_au_matrix_confidence(h), validate_au_matrix_confidence(h)


def _debut_neutral():
    h = valid_horse()
    h["career_tag"] = "DEBUT"
    h["matrix"]["form_line"] = dim("FL_NEUTRAL_01", "➖", "Unknown", ["DEBUT no formal race 日期 2026-04-01"], "初出無正式賽績線。")
    assert not validate_au_matrix_confidence(h), validate_au_matrix_confidence(h)


if __name__ == "__main__":
    main()
