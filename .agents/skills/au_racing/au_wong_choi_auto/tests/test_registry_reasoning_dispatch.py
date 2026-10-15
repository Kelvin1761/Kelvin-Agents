"""Registry reasoning: legacy context preserved and new dimensions dispatched."""
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from au_racing_engine import engine_core
from au_racing_engine.dimensions import DIMENSION_SPECS, DimensionSpec

class Probe:
    def _reason_bundle(self, key, score, feature_scores, feature_notes, *components):
        return {"score": score, "components": components}

def test_registered_reasoning_includes_preparation_and_legacy_context():
    values = {s.key: 63.25 for s in DIMENSION_SPECS}
    actual = engine_core.RacingEngine._matrix_reasoning(Probe(), values, {}, {})
    assert tuple(actual) == tuple(s.key for s in DIMENSION_SPECS if s.shown_in_report)
    assert actual["preparation"] == {"score": 63.25, "components": ("preparation_score",)}
    assert actual["pace_perf"]["components"] == ("pace_figure_score", "sectional_score")
    assert actual["class_weight"]["components"] == ("class_score", "rating_score", "weight_score")
    assert actual["form_line"]["components"] == ("formline_score", "form_score")

def test_plugin_reasoning_uses_spec_without_dispatch_edit(monkeypatch):
    fake = DimensionSpec("audit_fake", "測試維度", (("form_score", 1.0),))
    monkeypatch.setattr(engine_core, "DIMENSION_SPECS", DIMENSION_SPECS + (fake,))
    values = {s.key: 60 for s in DIMENSION_SPECS}
    values["audit_fake"] = 19.5
    actual = engine_core.RacingEngine._matrix_reasoning(Probe(), values, {}, {})
    assert actual["audit_fake"] == {"score": 19.5, "components": ("form_score",)}
    assert tuple(s.key for s in DIMENSION_SPECS) == tuple(k for k in actual if k != "audit_fake")


def test_missing_required_matrix_raises_and_legacy_pace_default_survives():
    values = {s.key: 60 for s in DIMENSION_SPECS}
    del values["pace_perf"]
    result = engine_core.RacingEngine._matrix_reasoning(Probe(), values, {}, {})
    assert result["pace_perf"]["score"] == 60
    del values["stability"]
    with pytest.raises(KeyError, match="stability"):
        engine_core.RacingEngine._matrix_reasoning(Probe(), values, {}, {})
