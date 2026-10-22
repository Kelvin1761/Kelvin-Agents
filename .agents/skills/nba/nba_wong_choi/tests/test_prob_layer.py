"""EXP-20261022-03 candidate C wired into the live leg probability.

Values below are computed independently from the harness formula (prob_layer.py) so a
coefficient or formula drift fails loudly.
"""
from __future__ import annotations

import json
import math
import sys
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
