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


def test_no_ml_lines_when_legacy_or_healthy() -> None:
    reports.reset_ml_status("legacy")
    assert reports.ml_status_lines() == []
    reports.reset_ml_status("hybrid")
    reports.ML_STATUS["loaded"] = True
    reports.ML_STATUS["predictions"] = 10
    assert reports.ml_status_lines() == []


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
