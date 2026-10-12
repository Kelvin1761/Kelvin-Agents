from __future__ import annotations

from dataclasses import replace
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from au_racing_engine import dimensions as reg, renderer  # noqa: E402


def validate(leaves, dimensions):
    function = getattr(reg, "validate_registry", None)
    assert callable(function), "registry requires validation before deriving dictionaries"
    function(leaves, dimensions)


def test_current_special_roles_and_zero_hidden_dimension_are_valid():
    validate(reg.LEAF_SPECS, reg.DIMENSION_SPECS)
    class_leaf = next(s for s in reg.LEAF_SPECS if s.key == "class_score")
    assert class_leaf.report_only and not class_leaf.counts_as_evidence
    validate(reg.LEAF_SPECS, reg.DIMENSION_SPECS + (
        reg.DimensionSpec("zero_probe", "Zero", (("form_score", 1.0),), 0.0, 6, shown_in_report=False),
    ))


@pytest.mark.parametrize("change", [
    {"key": "form_score"}, {"key": "bad key"}, {"label": ""},
    {"legacy_ability_order": 0}, {"legacy_ability_order": True},
    {"legacy_ability_order": -1}, {"report_only": "yes"},
    {"counts_as_evidence": 1}, {"shown_in_report": None},
    {"safety_default": float("nan")}, {"safety_default": float("inf")},
    {"safety_default": True}, {"safety_default": -1}, {"safety_default": 101},
])
def test_malformed_leaf_fails_before_derived_consumers(change):
    probe = reg.LeafSpec("contract_probe_score", "Probe", 11, False, False)
    with pytest.raises(ValueError):
        validate(reg.LEAF_SPECS + (replace(probe, **change),), reg.DIMENSION_SPECS)


@pytest.mark.parametrize("change", [
    {"key": "stability"}, {"key": "bad key"}, {"label": ""},
    {"leaves": (("unknown_score", 1.0),)},
    {"leaves": (("form_score", 0.5), ("form_score", 0.5))},
    {"leaves": (("form_score", float("nan")),)},
    {"leaves": (("form_score", True),)}, {"leaves": ()},
    {"coefficient": float("inf")}, {"coefficient": True},
    {"coefficient": "0.2"}, {"ranking_order": 0},
    {"ranking_order": True}, {"ranking_order": -1},
    {"ranking_order": None}, {"shown_in_report": "no"},
    {"reasoning_components": ("unknown_score",)},
    {"reasoning_score_default": float("nan")},
])
def test_malformed_dimension_fails_before_derived_consumers(change):
    probe = reg.DimensionSpec("contract_probe", "Probe", (("form_score", 1.0),), 0.2, 6)
    with pytest.raises(ValueError):
        validate(reg.LEAF_SPECS, reg.DIMENSION_SPECS + (replace(probe, **change),))


@pytest.mark.parametrize("default", [0.0, 56.0, 60.0])
def test_renderer_uses_registered_numeric_default_with_existing_tolerance(monkeypatch, default):
    key = "jockey_score"
    monkeypatch.setitem(reg.SAFETY_DEFAULTS, key, default)
    monkeypatch.setattr(renderer, "THIN_EVIDENCE_SCORED_LEAVES", (key,))
    assert renderer._default_leaf_count({"feature_scores": {key: default}}) == 1
    assert renderer._default_leaf_count({"feature_scores": {key: default + 0.004}}) == 1
    assert renderer._default_leaf_count({"feature_scores": {key: default + 0.006}}) == 0
    assert renderer._default_leaf_count({"feature_scores": {key: None}}) == 0
    assert renderer._default_leaf_count({"feature_scores": {}}) == 0
    assert renderer._default_leaf_count({}) == 0


def test_report_uses_generic_default_wording_when_profile_defaults_differ(monkeypatch):
    monkeypatch.setitem(reg.SAFETY_DEFAULTS, "jockey_score", 0.0)
    text = renderer._decision_trace_text({"decision_trace": {"thin_evidence_swap": {
        "demoted": "1", "promoted": "2", "default_leaf_count": 2,
    }}})
    assert "預設 60" not in text
    assert "預設" in text


def test_default_profile_preserves_exact_trace_wording():
    text = renderer._decision_trace_text({"decision_trace": {"thin_evidence_swap": {
        "demoted": "1", "promoted": "2", "default_leaf_count": 2,
    }}})
    assert text == "證據厚度安全欄：首選 #1 有 2 個計分維度冇實測數據（停留預設 60），已同 #2 對調（top-3／top-4 成員不變）"
