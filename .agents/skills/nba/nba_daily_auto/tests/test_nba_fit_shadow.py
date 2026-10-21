"""Fitted probability layer is SHADOW ONLY: correct, isolated, and changes no pick."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

NBA_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA_ROOT))
sys.path.insert(0, str(NBA_ROOT / 'nba_data_extractor' / 'scripts'))
sys.path.insert(0, str(NBA_ROOT / 'nba_wong_choi' / 'scripts'))
import generate_nba_reports as reports
import nba_extractor as x
import nba_fit_layer as layer
import nba_market_ledger as ledger

PTS10 = [28, 31, 25, 33, 29, 27, 30, 26, 34, 28]


def fit_inputs(games=40, m10=34.0, pts_total=1100.0, minutes=1300.0, mean=29.1):
    return {"season": "2026-27", "same_season_rs_games": games, "minutes_total": minutes,
            "totals": {"PTS": pts_total, "REB": 200.0, "AST": 250.0, "FG3M": 90.0},
            "prior10_games": 10, "prior10_mean_min": m10,
            "prior10_mean": {"PTS": mean, "REB": 5.0, "AST": 6.0, "FG3M": 2.0}}


def player(fi="default"):
    gl = {"PTS": PTS10, "PTS_stats": {"avg": 29.1, "med": 28.5, "sd": 2.7, "cov": 0.09}, "MIN": [34] * 10}
    if fi == "default":
        gl["fit_inputs"] = fit_inputs()
    elif fi is not None:
        gl["fit_inputs"] = fi
    return {"name": "Test Star", "position": "G", "gamelog": gl}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("NBA_FIT_LAYER_SHADOW_ENABLED", raising=False)
    reports.reset_fit_status()
    reports.reset_ml_status("legacy")


def card_for(ext, lines=("25", "30")):
    return reports.build_player_card(
        "Test Star", "DET", {"lines": {l: "1.30" for l in lines}}, ext, "points",
        opponent_abbr="BOS", team_stats={}, engine_mode="legacy")


# 1. parity with the reference function ---------------------------------------
@pytest.mark.parametrize("line", [20, 25, 29, 30, 35])
def test_live_value_equals_reference_function(line):
    out = reports.compute_shadow_fit(player(), "PTS", line)
    expected = layer.p_fit_A("PTS", line, 1100.0, 1300.0, 34.0)
    assert out["shadow_fit_prob_A"] == round(expected, 4)
    assert out["shadow_fit_version"] == layer.MODEL_ID


def test_status_inside_and_outside_validated_lines():
    inside = reports.compute_shadow_fit(player(), "PTS", 29)
    outside = reports.compute_shadow_fit(player(), "PTS", 40)
    assert inside["shadow_fit_status"] == "ok"
    assert outside["shadow_fit_status"] == "ok_outside_validated_lines"
    assert outside["shadow_fit_prob_A"] is not None            # computed, never nulled for this reason alone
    assert outside["shadow_fit_inputs"]["line_minus_mean"] == round(40 - 29.1, 3)
    assert outside["shadow_fit_inputs"]["mu"] > 0 and outside["shadow_fit_inputs"]["l10_mean"] == 29.1


# 2. no pick changes ----------------------------------------------------------
SHADOW_KEYS = {"shadow_fit_prob_A", "shadow_fit_version", "shadow_fit_status", "shadow_fit_inputs"}


def test_card_identical_with_shadow_on_and_off(monkeypatch):
    on = card_for(player())["line_analysis"]
    monkeypatch.setenv("NBA_FIT_LAYER_SHADOW_ENABLED", "0")
    off = card_for(player())["line_analysis"]
    assert on.keys() == off.keys()
    for key in on:
        strip = lambda d: {k: v for k, v in d.items() if k not in SHADOW_KEYS}
        assert strip(on[key]) == strip(off[key])
    assert all(v["shadow_fit_prob_A"] is not None for v in on.values())
    assert all(v["shadow_fit_status"] == "disabled" for v in off.values())


def test_ledger_variants_untouched_and_field_recorded_separately():
    assert ledger.MODEL_VARIANTS == ("p_final", "p_hit_rate_10f", "p_ml", "p_monte_carlo")
    assert not any("shadow_fit" in name for name in ledger.MODEL_VARIANTS)


# 3. failure isolation --------------------------------------------------------
def test_layer_exception_is_counted_and_card_unchanged(monkeypatch):
    baseline = card_for(player())["line_analysis"]

    def boom():
        raise RuntimeError("layer exploded")
    monkeypatch.setattr(reports, "_fit_layer_module", boom)
    reports.reset_fit_status()
    broken = card_for(player())["line_analysis"]
    assert reports.FIT_STATUS["errors"] == len(broken)
    assert all(v["shadow_fit_status"] == "error" for v in broken.values())
    for key in baseline:
        strip = lambda d: {k: v for k, v in d.items() if k not in SHADOW_KEYS}
        assert strip(baseline[key]) == strip(broken[key])
    assert "錯誤" in "\n".join(reports.fit_status_lines())


def test_corrupt_artifact_gives_null_not_exception():
    model, reason = layer.load_model(expected_sha256="0" * 64)
    assert model is None and "sha256" in reason

    class Bad:
        MODEL_ID = "x"

        @staticmethod
        def fit_prob_A(*a, **k):
            return None, "sha256 mismatch: expected"
    out = reports.compute_shadow_fit(player(), "PTS", 25, layer=Bad)
    assert out["shadow_fit_status"] == "artifact_invalid" and out["shadow_fit_prob_A"] is None


# 4. insufficient games / population ------------------------------------------
def test_nine_same_season_games_is_null_with_reason():
    out = reports.compute_shadow_fit(player(fit_inputs(games=9)), "PTS", 25)
    assert out["shadow_fit_prob_A"] is None
    assert out["shadow_fit_status"] == "insufficient_same_season_games"


def test_low_minutes_is_out_of_population():
    out = reports.compute_shadow_fit(player(fit_inputs(m10=19.9)), "PTS", 25)
    assert out["shadow_fit_status"] == "low_minutes_out_of_population"


def test_missing_or_broken_fit_inputs_do_not_break_the_card():
    for ext, status in ((player(None), "no_fit_inputs"), (player({"error": "ValueError: x"}), "no_fit_inputs"),
                        ({"name": "Test Star", "position": "G"}, "no_gamelog")):
        out = reports.compute_shadow_fit(ext, "PTS", 25)
        assert out["shadow_fit_prob_A"] is None and out["shadow_fit_status"] == status
    base = card_for(player())["line_analysis"]
    no_fi = card_for(player(None))["line_analysis"]
    for key in base:
        strip = lambda d: {k: v for k, v in d.items() if k not in SHADOW_KEYS}
        assert strip(base[key]) == strip(no_fi[key])


def test_header_line_states_shadow_and_counts():
    reports.compute_shadow_fit(player(), "PTS", 25)
    reports.compute_shadow_fit(player(fit_inputs(games=3)), "PTS", 25)
    text = "\n".join(reports.fit_status_lines())
    assert "shadow" in text and "已計 1" in text and "空值 1" in text


# 5. extractor fit_inputs (point-in-time, same-season only) --------------------
def frame(rows):
    return pd.DataFrame(rows).assign(**{})


def test_fit_inputs_exclude_prior_season_preseason_playoffs_and_dnp():
    rows = []
    for i in range(12):   # same-season regular season, newest first
        rows.append({"_season": "2026-27", "_season_type": "Regular Season", "MIN": 30, "PTS": 20, "REB": 5, "AST": 4, "FG3M": 2})
    rows += [{"_season": "2025-26", "_season_type": "Regular Season", "MIN": 35, "PTS": 99, "REB": 9, "AST": 9, "FG3M": 9}] * 40
    rows += [{"_season": "2026-27", "_season_type": "Playoffs", "MIN": 35, "PTS": 99, "REB": 9, "AST": 9, "FG3M": 9}]
    rows += [{"_season": "2026-27", "_season_type": "Pre Season", "MIN": 35, "PTS": 99, "REB": 9, "AST": 9, "FG3M": 9}]
    rows += [{"_season": "2026-27", "_season_type": "Regular Season", "MIN": 0, "PTS": 0, "REB": 0, "AST": 0, "FG3M": 0}]
    out = x.compute_fit_inputs(pd.DataFrame(rows), "2026-27")
    assert out["same_season_rs_games"] == 12
    assert out["totals"]["PTS"] == 240.0 and out["minutes_total"] == 360.0
    assert out["prior10_games"] == 10 and out["prior10_mean_min"] == 30.0


def test_player_with_prior_season_history_but_three_current_games_is_null():
    rows = [{"_season": "2026-27", "_season_type": "Regular Season", "MIN": 30, "PTS": 20, "REB": 5, "AST": 4, "FG3M": 2}] * 3
    rows += [{"_season": "2025-26", "_season_type": "Regular Season", "MIN": 32, "PTS": 25, "REB": 5, "AST": 4, "FG3M": 2}] * 60
    fi = x.compute_fit_inputs(pd.DataFrame(rows), "2026-27")
    ext = player(fi)
    assert fi["same_season_rs_games"] == 3
    assert reports.compute_shadow_fit(ext, "PTS", 20)["shadow_fit_status"] == "insufficient_same_season_games"


def test_fit_inputs_failure_is_an_error_dict_not_an_exception():
    out = x.compute_fit_inputs(pd.DataFrame([{"a": 1}]), "2026-27")
    assert "error" in out
