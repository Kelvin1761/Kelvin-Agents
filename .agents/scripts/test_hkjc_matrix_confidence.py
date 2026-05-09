#!/usr/bin/env python3
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".agents" / "scripts"))

from validate_hkjc_matrix_confidence import apply_hkjc_matrix_caps, validate_hkjc_matrix_confidence


RULES = {
    "stability": ("STAB_POS_01", "✅"),
    "sectional": ("SEC_POS_01", "✅"),
    "race_shape": ("SHAPE_POS_01", "✅"),
    "trainer_signal": ("TS_POS_01", "✅"),
    "horse_health": ("HEALTH_POS_01", "✅"),
    "form_line": ("FL_POS_01", "✅"),
    "class_advantage": ("CLASS_POS_01", "✅"),
}


def dim(rule, score, confidence="High", evidence=None, reasoning=None):
    return {
        "score": score,
        "confidence": confidence,
        "trigger_rule": rule,
        "trigger_evidence": evidence or ["L400 22.59 日期 2026-04-01", "檔位 3 沿途位 2-2-2"],
        "disqualifiers": [],
        "reasoning": reasoning or "有具體日期、檔位、L400及對手後續支持。",
    }


def valid_horse():
    h = {"horse_name": "Valid", "core_logic": "有具體數據支持。", "fine_tune": {"direction": "無"}}
    h["matrix"] = {k: dim(rule, score) for k, (rule, score) in RULES.items()}
    h["matrix"]["race_shape"]["trigger_evidence"] = ["檔位 3 有上名率支持", "沿途位 2-2-2 走位順"]
    h["matrix"]["form_line"]["reasoning"] = "對手後續有兩匹再上名，日期及場次清楚。"
    h["matrix"]["form_line"]["trigger_evidence"] = ["對手後續 A 日期 2026-04-01", "對手後續 B 場次 R3"]
    return h


def check(name, fn):
    try:
        fn()
        print(f"PASS {name}")
    except Exception as exc:
        print(f"FAIL {name}: {exc}")
        raise


def ok(expr):
    assert expr


def has_err(h, text):
    return any(text in e for e in validate_hkjc_matrix_confidence(h))


def main():
    check("valid full 7D passes", lambda: assert_no_errors(valid_horse()))
    check("sectional ✅✅ High passes", _sectional_strong_passes)
    check("sectional ✅✅ Medium fails", lambda: ok(has_err(_mut("sectional", confidence="Medium", score="✅✅", rule="SEC_STRONG_01"), "✅✅ requires High")))
    check("sectional ✅ Low fails", lambda: ok(has_err(_mut("sectional", confidence="Low"), "positive score")))
    check("trainer famous only fails", lambda: ok(has_err(_mut("trainer_signal", score="✅✅", rule="TS_STRONG_01", evidence=["潘頓 famous jockey 日期 2026-04-01"], reasoning="潘頓名氣大。"), "famous jockey")))
    check("form_line no opponent fails", lambda: ok(has_err(_mut("form_line", evidence=["日期 2026-04-01 班次強"], reasoning="班次強。"), "opponent")))
    check("health medical cap", lambda: ok(apply_hkjc_matrix_caps("A", _mut("horse_health", score="❌", rule="HEALTH_NEG_01", reasoning="健康 unresolved red flag 流鼻血", evidence=["健康 unresolved 日期 2026-04-01", "體重 -20"]))[0] == "B"))
    check("race_shape fatal caps B+", lambda: ok(apply_hkjc_matrix_caps("A", _mut("race_shape", score="❌❌", rule="SHAPE_FATAL_01", evidence=["外檔 wide 14", "塞車 風險", "檔位 死位"], reasoning="外檔 wide traffic"))[0] == "B+"))
    check("aux ✅✅ fails", lambda: ok(has_err(_mut("horse_health", score="✅✅", rule="HEALTH_POS_01"), "invalid")))
    check("missing confidence fails", lambda: ok(has_err(_drop_field("confidence"), "confidence missing")))
    check("missing trigger_rule fails", lambda: ok(has_err(_drop_field("trigger_rule"), "trigger_rule missing")))
    check("rule mismatch fails", lambda: ok(has_err(_mut("sectional", score="❌", rule="SEC_POS_01"), "score mismatch")))
    check("generic evidence fails", lambda: ok(has_err(_mut("sectional", evidence=["具備一定競爭力"]), "generic")))
    check("fill evidence fails", lambda: ok(has_err(_mut("sectional", evidence=["[FILL]"]), "FILL")))
    check("class fine_tune reuse fails", _class_reuse)
    check("debut cap A", lambda: ok(apply_hkjc_matrix_caps("S", {**valid_horse(), "career_tag": "DEBUT"})[0] == "A"))
    check("race_shape pace evidence fails", lambda: ok(has_err(_mut("race_shape", evidence=["predicted_pace fast"], reasoning="speed map predicted_pace"), "predicted pace")))
    check("race_shape no draw anchor fails", lambda: ok(has_err(_mut("race_shape", evidence=["日期 2026-04-01 班次"], reasoning="只有日期與班次資料"), "draw/trip")))


def assert_no_errors(h):
    errs = validate_hkjc_matrix_confidence(h)
    assert not errs, errs


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


def _drop_field(field):
    h = valid_horse()
    del h["matrix"]["sectional"][field]
    return h


def _sectional_strong_passes():
    h = _mut("sectional", score="✅✅", rule="SEC_STRONG_01", confidence="High", evidence=[
        "L400 22.59 日期 2026-04-01", "L600 34.10 同程距離",
        "班次 Class 3 above par", "完成時間偏差 -0.30",
    ], reasoning="正式賽 L400/L600 明顯高於班次。")
    assert_no_errors(h)


def _class_reuse():
    h = valid_horse()
    h["fine_tune"] = {"direction": "+", "trigger": "class weight 負磅"}
    assert has_err(h, "fine_tune")


if __name__ == "__main__":
    main()
