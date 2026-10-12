"""Production/in-memory API share preprocessing and scoring without output writes."""
import copy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import au_auto_orchestrator as auto


def test_in_memory_scoring_does_not_call_output_writers(tmp_path, monkeypatch):
    path = tmp_path / "Race_1_Logic.json"
    data = {"race_analysis": {"race_number": 1}, "horses": {"1": {"horse_name": "Audit Horse"}}}
    events = []
    monkeypatch.setattr(auto, "_facts_path_for_logic", lambda *args: None)
    monkeypatch.setattr(auto, "_prepare_logic_data", lambda value, **kwargs: (value, None))
    monkeypatch.setattr(auto, "backfill_pf_metrics", lambda *args: events.append("pf"))
    monkeypatch.setattr(auto, "normalise_field_barriers", lambda *args: events.append("barriers"))
    monkeypatch.setattr(auto, "_build_field_summary", lambda horses: {"count": len(horses)})
    class FakeEngine:
        def __init__(self, horse, context, **kwargs):
            assert context["field_summary"]["count"] == 1
        def analyze_horse(self):
            events.append("score")
            return {"ability_score": 63}
    monkeypatch.setattr(auto, "RacingEngine", FakeEngine)
    monkeypatch.setattr(auto, "ensure_verdict", lambda value: events.append("verdict"))
    monkeypatch.setattr(auto, "validate_logic_data", lambda value: [])
    def forbidden(*args, **kwargs):
        raise AssertionError("output writer called by score-only API")
    monkeypatch.setattr(auto, "_write_json_atomic", forbidden)
    monkeypatch.setattr(auto, "write_race_outputs", forbidden)
    before = copy.deepcopy(data)
    result = auto.score_logic_data(path, logic_data=data)
    assert events == ["pf", "barriers", "score", "verdict"]
    assert result["horses"]["1"]["python_auto"]["ability_score"] == 63
    assert before != result and result is data
    assert list(tmp_path.iterdir()) == []


def test_file_processing_delegates_to_same_scoring_api(tmp_path, monkeypatch):
    path = tmp_path / "Race_1_Logic.json"
    data = {"sentinel": "complete scorer output"}
    calls = []
    def score(source, going, *, logic_data):
        calls.append((source, going, logic_data))
        return data
    monkeypatch.setattr(auto, "score_logic_data", score)
    monkeypatch.setattr(auto, "_write_json_atomic", lambda source, value: calls.append((source, value)))
    report = tmp_path / "analysis.md"
    report.write_text("fixture")
    monkeypatch.setattr(auto, "write_race_outputs", lambda *args: (report, tmp_path / "score.csv"))
    monkeypatch.setattr(auto, "validate_report_text", lambda text: [])
    original = {"input": True}
    assert auto.process_logic_file(path, "Soft 5", logic_data=original) is data
    assert calls == [(path, "Soft 5", original), (path, data)]
