"""EXP-20261022-03 candidate C wired into the live leg probability.

Values below are computed independently from the harness formula (prob_layer.py) so a
coefficient or formula drift fails loudly.
"""
from __future__ import annotations

import json
import math
import sys
import copy
import pytest
import runpy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import nba_prob_layer as layer  # noqa: E402

CONFIG = json.loads((Path(__file__).resolve().parents[1] / "resources" / "nba_prob_layer.json").read_text())
ON = {**CONFIG, "enabled": True}


def _expected(stat: str, odds: float, hit_pct: float) -> float:
    a = {"PTS": -0.295, "REB": -0.160, "AST": -0.320, "FG3M": -0.287}[stat]
    m = min(max(1 / odds, 0.02), 0.98)
    h = min(max(hit_pct / 100, 0.05), 0.95)
    z = a + 0.755 * math.log(m / (1 - m)) + 0.140 * math.log(h / (1 - h))
    return round(100 / (1 + math.exp(-z)), 1)


def test_matches_experiment_formula() -> None:
    for stat, odds, hit in [("PTS", 1.36, 100.0), ("REB", 1.52, 90.0), ("AST", 1.87, 70.0), ("FG3M", 1.43, 80.0)]:
        assert layer.calibrated_prob(stat, odds, hit, ON) == _expected(stat, odds, hit)


def test_perfect_l10_no_longer_means_98_percent() -> None:
    # live engine printed 98.0 for RJ Barrett PTS 15+ @1.36 with 10/10 hits
    assert layer.calibrated_prob("PTS", 1.36, 100.0, ON) < 80.0


def test_disabled_config_returns_none() -> None:
    assert layer.calibrated_prob("PTS", 1.5, 90.0, {**ON, "enabled": False}) is None


def test_env_kill_switch(monkeypatch) -> None:
    monkeypatch.setenv("NBA_WC_PROB_LAYER", "0")
    assert layer.calibrated_prob("PTS", 1.5, 90.0, ON) is None


def test_unknown_stat_or_bad_price_falls_back() -> None:
    assert layer.calibrated_prob("STL", 1.5, 90.0, ON) is None
    assert layer.calibrated_prob("PTS", None, 90.0, ON) is None
    assert layer.calibrated_prob("PTS", 1.0, 90.0, ON) is None
    assert layer.calibrated_prob("PTS", 1.5, float("nan"), ON) is None


def test_monotone_in_price_and_hit_rate() -> None:
    assert layer.calibrated_prob("REB", 1.3, 80.0, ON) > layer.calibrated_prob("REB", 1.8, 80.0, ON)
    assert layer.calibrated_prob("REB", 1.5, 90.0, ON) > layer.calibrated_prob("REB", 1.5, 50.0, ON)


def test_shipped_config_is_complete() -> None:
    for key in ("intercepts", "beta_market", "gamma_l10", "clip_market", "clip_l10"):
        assert key in CONFIG
    assert set(CONFIG["intercepts"]) == {"PTS", "REB", "AST", "FG3M"}


@pytest.mark.parametrize("field,value", [
    ("enabled", "true"), ("version", ""), ("intercepts", {"PTS": 0}),
    ("beta_market", float("nan")), ("gamma_l10", float("inf")),
    ("clip_market", [0, 1]), ("clip_l10", [0.9, 0.1]), ("clip_l10", [False, 0.9]),
])
def test_invalid_configuration_blocks_instead_of_falling_back(field, value):
    bad = {**ON, field: value}
    with pytest.raises(layer.ProbabilityConfigError):
        layer.calibrated_prob("PTS", 1.5, 90, bad)


@pytest.mark.parametrize("content", ["{", "[]", '{"enabled": true}'])
def test_unreadable_or_invalid_config_can_recover_without_sticky_failure(tmp_path, content):
    path = tmp_path / "config.json"
    path.write_text(content)
    with pytest.raises(layer.ProbabilityConfigError):
        layer.load_config(str(path))
    path.write_text(json.dumps(ON))
    assert layer.load_config(str(path)) == ON


def test_missing_config_fails_but_explicit_kill_switch_does_not_read_it(tmp_path, monkeypatch):
    monkeypatch.setattr(layer, "_CONFIG_PATH", str(tmp_path / "missing.json"))
    with pytest.raises(layer.ProbabilityConfigError, match="cannot load"):
        layer.calibrated_prob("PTS", 1.5, 90)
    monkeypatch.setenv("NBA_WC_PROB_LAYER", "0")
    assert layer.calibrated_prob("PTS", 1.5, 90) is None
    assert layer.probability_model_id() is None


def test_identity_tracks_actual_coefficients_but_not_editorial_notes():
    identity = layer.probability_model_id(ON)
    assert identity.startswith("calibrated:C-2026-10-22:")
    assert layer.probability_model_id({**ON, "fit": {"note": "changed"}}) == identity
    changed = copy.deepcopy(ON)
    changed["intercepts"]["PTS"] -= 0.01
    assert layer.probability_model_id(changed) != identity


@pytest.mark.parametrize("odds,hit", [(float("nan"), 50), (float("inf"), 50), (1.5, -1), (1.5, 101)])
def test_nonfinite_or_impossible_inputs_cannot_generate_a_probability(odds, hit):
    assert layer.calibrated_prob("PTS", odds, hit, ON) is None


def test_report_cli_blocks_before_reading_inputs_when_config_is_broken(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("NBA_WC_PROB_LAYER", raising=False)
    monkeypatch.setattr(layer, "_CONFIG_PATH", str(tmp_path / "missing-model-config.json"))
    renderer = Path(__file__).resolve().parents[1] / "scripts" / "generate_nba_reports.py"
    monkeypatch.setattr(sys, "argv", [str(renderer)])
    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(renderer), run_name="__main__")
    assert error.value.code == 1
    assert "probability_config_invalid" in capsys.readouterr().err
