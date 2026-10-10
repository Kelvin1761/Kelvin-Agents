"""Synthetic cache fixtures, never live prediction evidence."""
import json
import sys
from pathlib import Path
from unittest import mock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import nba_orchestrator as o

@pytest.fixture
def inputs(tmp_path, monkeypatch):
    monkeypatch.setenv("NBA_WC_MODEL_DIR", str(tmp_path / "model"))
    (tmp_path / "model").mkdir()
    (tmp_path / "model" / "model.pkl").write_bytes(b"fixture model")
    (tmp_path / "model" / "feature_names.json").write_text("[]")
    odds = tmp_path / "Sportsbet_Odds_MEM_CHI.json"
    odds.write_text(json.dumps({"player_props":{"points":{"Fixture Player":{"lines":{"15":"1.74"}}}}}))
    extractor = tmp_path / "nba_game_data_MEM_CHI.json"
    extractor.write_text(json.dumps({"meta":{"season_phase":"PRESEASON","preseason_rookie_history_contract":1},"players":{}}))
    report = tmp_path / "Game_MEM_CHI_Full_Analysis.md"
    report.write_text("verified synthetic report\n" + "x" * 6000)
    cache = Path(str(report) + ".inputs.json")
    cache.write_text(json.dumps({"inputs":o.report_inputs(str(odds), str(extractor), False), "report":o._file_digest(str(report))}))
    return odds, extractor, report, cache

@pytest.mark.parametrize("change", ["odds", "extractor", "report", "model", "features", "legacy", "malformed", "absent"])
def test_changed_inputs_or_report_cannot_reuse(inputs, change):
    odds, extractor, report, cache = inputs
    if change in ("odds", "extractor", "report"):
        path = {"odds":odds, "extractor":extractor, "report":report}[change]
        path.write_text(path.read_text() + " ")
    elif change in ("model", "features"):
        name = "model.pkl" if change == "model" else "feature_names.json"
        (odds.parent / "model" / name).write_bytes(b"changed fixture")
    elif change == "malformed":
        cache.write_text("[]")
    elif change == "absent":
        cache.unlink()
    assert not o.report_cache_current(str(report), str(odds), str(extractor), change == "legacy")


def test_unchanged_report_reuses_with_firewall(inputs):
    odds, extractor, report, cache = inputs
    with mock.patch.object(o, "run_script", return_value=True) as run:
        assert o.process_single_game("MEM_CHI", str(odds), str(odds.parent), "2026-10-11")
    assert any(c.args[0] == o.VALIDATE_OUTPUT for c in run.call_args_list)
    assert not any(c.args[0] == o.GENERATE_REPORTS for c in run.call_args_list)


@pytest.mark.parametrize("mutate_during_generation", [False, True])
def test_changed_odds_regenerates_and_binds_verified_inputs(inputs, mutate_during_generation):
    odds, extractor, report, cache = inputs
    odds.write_text(odds.read_text().replace("1.74", "1.85"))
    def run(script, args, **kwargs):
        if script == o.GENERATE_REPORTS:
            report.write_text("refreshed synthetic report\n" + "y" * 6000)
            if mutate_during_generation:
                odds.write_text(odds.read_text().replace("1.85", "1.95"))
        return True
    with mock.patch.object(o, "run_script", side_effect=run) as calls:
        result = o.process_single_game("MEM_CHI", str(odds), str(odds.parent), "2026-10-11")
    assert any(c.args[0] == o.GENERATE_REPORTS for c in calls.call_args_list)
    assert result is (not mutate_during_generation)
    assert o.report_cache_current(str(report), str(odds), str(extractor), False) is result
