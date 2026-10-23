"""Synthetic cache fixtures, never live prediction evidence."""
import json
import sys
from pathlib import Path
from unittest import mock
import pytest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import nba_orchestrator as o

@pytest.fixture
def inputs(tmp_path, monkeypatch):
    # Cache hashing tests isolate the independently tested availability gate.
    monkeypatch.setattr(o, "availability_current", lambda payload: True)
    for name in ("NBA_WC_ENGINE", "NBA_WC_PROB_LAYER", "NBA_HYBRID_ML_ADJUST_ENABLED", "NBA_FIT_LAYER_SHADOW_ENABLED"):
        monkeypatch.delenv(name, raising=False)
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


@pytest.mark.parametrize("name,value", [
    ("NBA_WC_ENGINE", "ml"),
    ("NBA_WC_PROB_LAYER", "0"),
    ("NBA_HYBRID_ML_ADJUST_ENABLED", "1"),
    ("NBA_FIT_LAYER_SHADOW_ENABLED", "0"),
])
def test_runtime_model_switch_invalidates_report(inputs, monkeypatch, name, value):
    odds, extractor, report, _cache = inputs
    assert o.report_cache_current(str(report), str(odds), str(extractor), False)
    monkeypatch.setenv(name, value)
    assert not o.report_cache_current(str(report), str(odds), str(extractor), False)


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


def _availability_payload(extractor, captured):
    payload = json.loads(extractor.read_text())
    payload["meta"]["availability"] = {"contract": 1, "status": "verified", "captured_at": captured.isoformat(),
                                        "rosters": {team: [f"player{i}" for i in range(5)] for team in ("MEM", "CHI")}}
    payload["injuries"] = {"MEM": {}, "CHI": {}}
    return payload


def test_stale_availability_is_refreshed_before_cache_reuse(inputs, monkeypatch):
    from nba_availability import availability_current
    monkeypatch.setattr(o, "availability_current", availability_current)
    odds, extractor, report, cache = inputs
    payload = _availability_payload(extractor, datetime.now(timezone.utc) - timedelta(hours=2))
    extractor.write_text(json.dumps(payload))
    cache.write_text(json.dumps({"inputs": o.report_inputs(str(odds), str(extractor), False),
                                 "report": o._file_digest(str(report))}))
    def run(script, args, **kwargs):
        if "--refresh-availability" in args:
            updated = _availability_payload(extractor, datetime.now(timezone.utc))
            updated["injuries"]["MEM"] = {"Fixture Player": "Out"}
            extractor.write_text(json.dumps(updated))
        if script == o.GENERATE_REPORTS:
            report.write_text("refreshed availability report\n" + "x" * 6000)
        return True
    with mock.patch.object(o, "run_script", side_effect=run) as calls:
        assert o.process_single_game("MEM_CHI", str(odds), str(odds.parent), "2026-10-11")
    assert any("--refresh-availability" in c.args[1] for c in calls.call_args_list)
    assert any(c.args[0] == o.GENERATE_REPORTS for c in calls.call_args_list)
    assert not any(c.args[0] == o.NBA_EXTRACTOR and "--date" in c.args[1] for c in calls.call_args_list)


def test_source_failure_blocks_old_report_without_reextracting_history(inputs, monkeypatch):
    from nba_availability import availability_current
    monkeypatch.setattr(o, "availability_current", availability_current)
    odds, extractor, report, _cache = inputs
    before = extractor.read_bytes(), report.read_bytes()
    def run(script, args, **kwargs):
        assert "--refresh-availability" in args
        kwargs["failure_codes"].append(75)
        return False
    with mock.patch.object(o, "run_script", side_effect=run) as calls:
        assert not o.process_single_game("MEM_CHI", str(odds), str(odds.parent), "2026-10-11")
    assert calls.call_count == 1
    assert (extractor.read_bytes(), report.read_bytes()) == before


def test_roster_change_reextracts_history_before_generating_a_report(inputs, monkeypatch):
    from nba_availability import availability_current
    monkeypatch.setattr(o, "availability_current", availability_current)
    odds, extractor, report, _cache = inputs
    def run(script, args, **kwargs):
        if "--refresh-availability" in args:
            kwargs["failure_codes"].append(2)
            return False
        if script == o.NBA_EXTRACTOR:
            payload = _availability_payload(extractor, datetime.now(timezone.utc))
            payload["meta"]["availability"]["rosters"]["MEM"].append("new signing")
            extractor.write_text(json.dumps(payload))
        if script == o.GENERATE_REPORTS:
            assert "new signing" in json.loads(extractor.read_text())["meta"]["availability"]["rosters"]["MEM"]
            report.write_text("new roster report\n" + "x" * 6000)
        return True
    with mock.patch.object(o, "run_script", side_effect=run) as calls:
        assert o.process_single_game("MEM_CHI", str(odds), str(odds.parent), "2026-10-11")
    stages = [(c.args[0], c.args[1]) for c in calls.call_args_list]
    assert any(script == o.NBA_EXTRACTOR and "--date" in args for script, args in stages)
