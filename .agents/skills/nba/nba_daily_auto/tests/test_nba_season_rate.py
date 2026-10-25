"""Season-rate model S is SHADOW ONLY: correct formula, isolated, changes no pick."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
from scipy.stats import nbinom

NBA_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA_ROOT))
sys.path.insert(0, str(NBA_ROOT / 'nba_data_extractor' / 'scripts'))
sys.path.insert(0, str(NBA_ROOT / 'nba_wong_choi' / 'scripts'))
sys.path.insert(0, str(NBA_ROOT / 'nba_daily_auto'))
import generate_nba_reports as reports
import nba_extractor as x
import nba_market_ledger as ledger
import nba_season_rate as S

KEYS = {"season_rate_prob_S", "season_rate_version", "season_rate_status", "season_rate_inputs"}


def log(pts, mins=None, kinds=None):
    n = len(pts)
    dates = [f"2026-{12 - i // 28:02d}-{28 - i % 28:02d}" for i in range(n)]  # strictly newest-first
    return {"dates": dates, "seasons": ["2026-27"] * n,
            "season_types": kinds or ["Regular Season"] * n,
            "MIN": mins or [30.0] * n, "PTS": pts, "REB": [5.0] * n, "AST": [4.0] * n,
            "FG3M": [2.0] * n, "FGA": [15.0] * n, "FG3A": [5.0] * n, "FTA": [4.0] * n}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("NBA_SEASON_RATE_SHADOW_ENABLED", raising=False)
    reports.reset_fit_status()
    reports.reset_ml_status("legacy")


def test_constant_player_matches_nb_with_frozen_dispersion():
    p, status, inputs = S.season_rate_prob(log([20.0] * 30), "PTS", 20)
    assert status == "ok" and inputs["mu"] == 20.0
    k = S.DISPERSION_K["PTS"]
    assert p == round(float(nbinom.sf(19, k, k / (k + 20.0))), 4)


def test_recent_games_weigh_more_and_probability_falls_with_line():
    rising, _, _ = S.season_rate_prob(log([30.0] * 15 + [15.0] * 15), "PTS", 20)
    falling, _, _ = S.season_rate_prob(log([15.0] * 15 + [30.0] * 15), "PTS", 20)
    assert rising > falling
    ladder = [S.season_rate_prob(log([20.0] * 30), "PTS", line)[0] for line in (10, 15, 20, 25, 30)]
    assert ladder == sorted(ladder, reverse=True)


def test_guards_short_preseason_dnp_and_bad_inputs():
    assert S.season_rate_prob(log([20.0] * 4), "PTS", 20)[1] == "insufficient_games"
    pre = log([20.0] * 8, kinds=["Pre Season"] * 4 + ["Regular Season"] * 4)
    assert S.season_rate_prob(pre, "PTS", 20)[1] == "insufficient_games"
    dnp = log([0.0] * 3 + [20.0] * 4, mins=[0.0] * 3 + [30.0] * 4)
    assert S.season_rate_prob(dnp, "PTS", 20)[1] == "insufficient_games"
    assert S.season_rate_prob(None, "PTS", 20)[1] == "no_season_log"
    assert S.season_rate_prob(log([20.0] * 10), "STL", 2)[1] == "stat_unsupported"
    assert S.season_rate_prob(log([20.0] * 10), "PTS", 19.5)[1] == "invalid_inputs"
    unordered = log([20.0] * 10); unordered["dates"] = list(reversed(unordered["dates"]))
    assert S.season_rate_prob(unordered, "PTS", 20)[1] == "invalid_inputs"


def test_extractor_keeps_every_fetched_game_newest_first():
    rows = [{"GAME_DATE": f"OCT {28 - i}, 2026", "_season": "2026-27", "_season_type": "Regular Season",
             "MIN": 30, "PTS": 20 + i, "REB": 5, "AST": 4, "FG3M": 2, "FGA": 15, "FG3A": 5, "FTA": 4}
            for i in range(14)]
    out = x.compact_season_log(pd.DataFrame(rows))
    assert len(out["dates"]) == 14 and out["dates"][0] == "2026-10-28" and out["PTS"][-1] == 33.0
    assert "error" in x.compact_season_log(pd.DataFrame([{"a": 1}]))


def card_for(ext):
    return reports.build_player_card(
        "Test Star", "DET", {"lines": {"20": "1.80", "25": "2.60"}}, ext, "points",
        opponent_abbr="BOS", team_stats={}, engine_mode="legacy")


def test_card_identical_with_shadow_on_and_off(monkeypatch):
    pts = [22.0, 25, 18, 24, 21, 26, 19, 23, 20, 27, 22, 24]
    ext = {"name": "Test Star", "position": "G",
           "gamelog": {"PTS": pts[:10], "MIN": [32] * 10, "season_log": log(pts)}}
    on = card_for(ext)["line_analysis"]
    monkeypatch.setenv("NBA_SEASON_RATE_SHADOW_ENABLED", "0")
    off = card_for(ext)["line_analysis"]
    strip = lambda d: {k: v for k, v in d.items() if k not in KEYS}
    assert all(strip(on[k]) == strip(off[k]) for k in on)
    assert all(v["season_rate_prob_S"] is not None and v["season_rate_status"] == "ok" for v in on.values())
    assert all(v["season_rate_status"] == "disabled" for v in off.values())


def test_module_failure_is_isolated(monkeypatch):
    monkeypatch.setattr(S, "season_rate_prob", lambda *a: 1 / 0)
    out = reports.compute_season_rate({"gamelog": {"season_log": log([20.0] * 10)}}, "PTS", 20)
    assert out["season_rate_status"] == "error" and out["season_rate_prob_S"] is None


def test_ledger_variants_untouched():
    assert not any("season_rate" in name for name in ledger.MODEL_VARIANTS)
