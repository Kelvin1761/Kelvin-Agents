"""The health gate's AU feature set must follow the engine, not a copy of it.

This file's own header records 2026-08-21, when the AU set held six key names
that did not exist and `deploy_allowed` was permanently False. The same drift
recurred a release later in the other direction: EXP-20260902-07 added
`preparation_score` to `ABILITY_FEATURE_KEYS` and the hand-copied set stayed at
ten, so one of the engine's eleven scoring leaves was outside the gate.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # .agents/skills
sys.path.insert(0, str(ROOT / "shared_racing" / "scripts"))
sys.path.insert(0, str(ROOT / "au_racing" / "au_wong_choi_auto" / "scripts"))

from au_racing_engine.scoring import ABILITY_FEATURE_KEYS  # noqa: E402
from racing_data_health import EXPECTED_FEATURES  # noqa: E402


def test_au_expected_features_are_exactly_the_engine_ability_keys():
    assert EXPECTED_FEATURES["au"] == set(ABILITY_FEATURE_KEYS)


def test_the_au_set_is_not_empty_and_covers_the_dimension_leaves():
    # A silently empty set would make the gate pass everything.
    assert len(EXPECTED_FEATURES["au"]) >= 10
    for key in ("form_score", "pace_figure_score", "preparation_score"):
        assert key in EXPECTED_FEATURES["au"], key


def test_hkjc_set_is_independent_of_au():
    """The two platforms have genuinely different leaves; do not merge them."""
    assert EXPECTED_FEATURES["hkjc"] != EXPECTED_FEATURES["au"]
    assert "speed_score" in EXPECTED_FEATURES["hkjc"]
    assert "speed_score" not in EXPECTED_FEATURES["au"]
