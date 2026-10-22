"""ML failures are counted and surfaced; empty-data caches are stale."""
from __future__ import annotations

import json
import sys
from pathlib import Path

NBA_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA_ROOT))
sys.path.insert(0, str(NBA_ROOT / 'nba_wong_choi' / 'scripts'))
import generate_nba_reports as reports
import nba_orchestrator as o


def test_ml_failure_is_counted_and_reported() -> None:
    reports.reset_ml_status("hybrid")
    reports.ML_STATUS["loaded"] = True
    reports.record_ml_failure("Test Star PTS 25", ValueError("boom"))
    reports.record_ml_failure("Test Star PTS 30", KeyError("x"))
    assert reports.ML_STATUS["failures"] == 2
    text = "\n".join(reports.ml_status_lines())
    assert "ML 預測失敗 2 次" in text
    assert "ValueError" in text


def test_ml_load_failure_is_reported_not_silent() -> None:
    reports.reset_ml_status("hybrid")
    reports.ML_STATUS.update(loaded=False, load_error="FileNotFoundError: model.pkl")
    text = "\n".join(reports.ml_status_lines())
    assert "載入失敗" in text and "model.pkl" in text


def test_no_ml_lines_when_legacy_or_healthy(monkeypatch) -> None:
    reports.reset_ml_status("legacy")
    assert reports.ml_status_lines() == []
    reports.reset_ml_status("hybrid")
    reports.ML_STATUS["loaded"] = True
    reports.ML_STATUS["predictions"] = 10
    monkeypatch.setenv("NBA_HYBRID_ML_ADJUST_ENABLED", "1")
    assert reports.ml_status_lines() == []


def test_header_says_ml_is_shadow_when_flag_off(monkeypatch) -> None:
    monkeypatch.delenv("NBA_HYBRID_ML_ADJUST_ENABLED", raising=False)
    reports.reset_ml_status("hybrid")
    reports.ML_STATUS["loaded"] = True
    text = "\n".join(reports.ml_status_lines())
    assert "shadow" in text and "未經驗證" in text


def test_failing_predictor_in_build_player_card_is_counted() -> None:
    class Broken:
        feature_names = []

        def build_features(self, *a, **k):
            raise RuntimeError("bad features")

    reports.reset_ml_status("hybrid")
    ext = {"name": "Test Star", "position": "G", "gamelog": {"PTS": [28, 31, 25, 33, 29, 27, 30, 26, 34, 28],
           "PTS_stats": {"avg": 29.1, "med": 28.5, "sd": 2.7, "cov": 0.09}, "MIN": [34] * 10}}
    reports.build_player_card("Test Star", "DET", {"lines": {"25": "1.30"}}, ext, "points",
                              opponent_abbr="BOS", ml_predictor=Broken(), team_stats={}, engine_mode="hybrid")
    assert reports.ML_STATUS["failures"] >= 1
    assert "bad features" in reports.ML_STATUS["failure_samples"][0]


def _cache(tmp_path, payload) -> str:
    p = tmp_path / "data.json"
    p.write_text(json.dumps(payload))
    return str(p)


def test_regular_season_cache_with_empty_team_stats_is_stale(tmp_path) -> None:
    payload = {"meta": {"season_phase": "EARLY_REGULAR"}, "team_stats": {"BOS": {}, "DET": {}},
               "players": {"BOS": [{"name": "A", "position": "G", "advanced": {}}]}}
    assert not o.extractor_cache_current(_cache(tmp_path, payload))


def test_regular_season_cache_with_zero_advanced_is_stale(tmp_path) -> None:
    payload = {"meta": {"season_phase": "EARLY_REGULAR"}, "team_stats": {"BOS": {"PACE": 99.0}},
               "players": {"BOS": [{"name": "A", "position": "G", "advanced": {}}]}}
    assert not o.extractor_cache_current(_cache(tmp_path, payload))


def test_regular_season_cache_with_data_is_current(tmp_path) -> None:
    payload = {"meta": {"season_phase": "EARLY_REGULAR"}, "team_stats": {"BOS": {"PACE": 99.0}},
               "players": {"BOS": [{"name": "A", "position": "G", "advanced": {"USG_PCT": 20.1}}]}}
    assert o.extractor_cache_current(_cache(tmp_path, payload))


# ── Hybrid ML adjustment is shadow-only unless explicitly enabled ──
class _FixedML:
    feature_names: list = []

    def __init__(self, prob):
        self.prob = prob

    def build_features(self, *a, **k):
        return {}

    def predict(self, feats):
        return self.prob


def _leg(monkeypatch, engine, ml_prob, flag, stat="points", line="25", layer=False):
    # These tests pin the LEGACY 10-factor/hybrid path. The calibrated probability layer
    # (EXP-20261022-03) replaces estimated_prob when on, so it is switched off here and
    # covered separately by test_calibrated_layer_replaces_legacy_probability.
    if layer:
        monkeypatch.delenv("NBA_WC_PROB_LAYER", raising=False)
    else:
        monkeypatch.setenv("NBA_WC_PROB_LAYER", "0")
    if flag is None:
        monkeypatch.delenv("NBA_HYBRID_ML_ADJUST_ENABLED", raising=False)
    else:
        monkeypatch.setenv("NBA_HYBRID_ML_ADJUST_ENABLED", flag)
    reports.reset_ml_status(engine)
    key = {"points": "PTS", "rebounds": "REB", "assists": "AST", "threes_made": "FG3M"}[stat]
    arr = [28, 31, 25, 33, 29, 27, 30, 26, 34, 28]
    ext = {"name": "Test Star", "position": "G", "gamelog": {key: arr,
           f"{key}_stats": {"avg": 29.1, "med": 28.5, "sd": 2.7, "cov": 0.09}, "MIN": [34] * 10}}
    card = reports.build_player_card(
        "Test Star", "DET", {"lines": {line: "1.30"}}, ext, stat, opponent_abbr="BOS",
        ml_predictor=_FixedML(ml_prob) if engine != "legacy" else None,
        team_stats={}, engine_mode=engine)
    return card["line_analysis"][line]


def test_flag_off_final_probability_equals_ten_factor(monkeypatch) -> None:
    legacy = _leg(monkeypatch, "legacy", 0.0, None)
    shadow = _leg(monkeypatch, "hybrid", 0.02, None)      # ml_delta far below -10
    assert shadow["ml_delta_pp"] <= -10
    assert shadow["hybrid_adj_applied_pp"] == 0.0
    assert shadow["hybrid_adj_shadow_pp"] == -5.0          # what the rule WOULD do
    assert shadow["estimated_prob"] == legacy["estimated_prob"]
    assert shadow["det_prob"] == legacy["det_prob"]


def test_flag_on_old_rule_still_applies(monkeypatch) -> None:
    legacy = _leg(monkeypatch, "legacy", 0.0, None)
    live = _leg(monkeypatch, "hybrid", 0.02, "1")
    assert live["hybrid_adj_applied_pp"] == -5.0
    assert live["estimated_prob"] == round(legacy["estimated_prob"] - 5.0, 1)


def test_calibrated_layer_replaces_legacy_probability(monkeypatch) -> None:
    legacy = _leg(monkeypatch, "legacy", 0.0, None)
    live = _leg(monkeypatch, "hybrid", 0.02, "1", layer=True)
    # market-anchored: a 10/10-ish L10 star at 1.30 is nowhere near the legacy 98% cap
    assert live["calibrated_prob"] is not None
    assert live["estimated_prob"] == live["calibrated_prob"]
    assert live["estimated_prob"] < legacy["estimated_prob"]
    assert live["legacy_prob"] == round(legacy["estimated_prob"] - 5.0, 1)  # old ML rule, kept for audit only
    assert live["engine"].startswith("calibrated(")


def test_ml_delta_recorded_when_off_for_both_directions(monkeypatch) -> None:
    low = _leg(monkeypatch, "hybrid", 0.02, None)
    high = _leg(monkeypatch, "hybrid", 0.99, None, line="30")
    assert low["ml_delta_pp"] < 0 < high["ml_delta_pp"]
    assert high["hybrid_adj_applied_pp"] == 0.0
    assert high["hybrid_adj_shadow_pp"] == 2.0


def test_hybrid_rule_table() -> None:
    f = reports.hybrid_adjustment
    assert f("REB", 12, "REGULAR_SEASON") == 3.0 and f("REB", -15, "REGULAR_SEASON") == -5.0
    assert f("PTS", -10, "REGULAR_SEASON") == -5.0 and f("PTS", 20, "REGULAR_SEASON") == 2.0
    assert f("PTS", 20, "PLAYOFFS") == 0.0 and f("AST", 0, "REGULAR_SEASON") == 0.0
