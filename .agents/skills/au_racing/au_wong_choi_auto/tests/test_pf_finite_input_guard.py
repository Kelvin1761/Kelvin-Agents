from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import au_auto_orchestrator as auto  # noqa: E402
from au_racing_engine.engine_core import RacingEngine  # noqa: E402

FIELDS = ("race_time_diff", "l800_delta", "l600_delta", "l400_delta", "l200_delta", "tempo_qrank", "own_l600_delta")
BAD = ("broken", "", float("nan"), "NaN", float("inf"), -float("inf"), True, False, [], {})


def horse(number, value=0.25):
    return {"horse_name": f"Numeric Fixture {number}", "horse_number": number,
            "jockey": "Fixture Rider", "trainer": "Fixture Trainer", "weight": 55,
            "rating": 60, "barrier": number, "career_race_starts": 1,
            "_data": {"pf_metrics": {"pf_aggregates": {
                **{field + "_avg": value for field in FIELDS},
                "pf_run_count": 1, "source": "audit_numeric_fixture",
            }}}}


def horses(value=0.25):
    return {str(i): horse(i, value if i == 4 else [-0.2, 0.1, 0.4][i - 1]) for i in range(1, 5)}


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("value", BAD)
def test_invalid_aggregate_refuses_field_summary(field, value):
    data = horses()
    data["4"]["_data"]["pf_metrics"]["pf_aggregates"][field + "_avg"] = value
    with pytest.raises(ValueError, match="PF"):
        auto._build_field_summary(data)


@pytest.mark.parametrize("value", BAD)
def test_direct_pace_scoring_refuses_invalid_runner_value(value):
    summary = auto._build_field_summary(horses())
    runner = horse(4, value)
    with pytest.raises(ValueError, match="PF"):
        RacingEngine(runner, {"field_summary": summary})._pace_figure_score()


@pytest.mark.parametrize("key", ["own_l600_delta_field_mean", "own_l600_delta_field_stdev"])
@pytest.mark.parametrize("value", BAD)
def test_direct_pace_scoring_refuses_invalid_precomputed_field(key, value):
    summary = auto._build_field_summary(horses())
    summary[key] = value
    with pytest.raises(ValueError, match="PF"):
        RacingEngine(horse(4), {"field_summary": summary})._pace_figure_score()


@pytest.mark.parametrize("value", [0, 0.0, "0.0", 0.25, "0.25", None])
def test_missing_and_finite_numeric_values_preserve_existing_semantics(value):
    data = horses(value)
    summary = auto._build_field_summary(copy.deepcopy(data))
    assert summary["pf_complete_profile_field_count"] == (3 if value is None else 4)
    assert summary["l600_delta_field_count"] == (3 if value is None else 4)
    engine = RacingEngine(data["4"], {"field_summary": summary})
    score, _, _ = engine._pace_figure_score()
    assert 0 <= score <= 100
    assert engine.pace_figure_detail["state"] == ("no_pf" if value is None else "ok")


def test_own_absence_retains_race_level_fallback():
    data = horses()
    data["4"]["_data"]["pf_metrics"]["pf_aggregates"]["own_l600_delta_avg"] = None
    summary = auto._build_field_summary(copy.deepcopy(data))
    engine = RacingEngine(data["4"], {"field_summary": summary})
    engine._pace_figure_score()
    assert engine.pace_figure_detail["basis"] == "race"
    assert engine.pace_figure_detail["state"] == "ok"


def test_file_processing_stops_before_scoring_or_any_output_on_invalid_pf(tmp_path):
    path = tmp_path / "Race_1_Logic.json"
    data = {"race_analysis": {"race_number": 1, "going": "Good 4"}, "horses": horses(float("nan"))}
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    # Actual process -> score -> preprocessing -> field summary. The engine/writer
    # spies prove the failure occurs before any horse score or output is created.
    with patch.object(auto.RacingEngine, "analyze_horse", side_effect=AssertionError("scorer reached")) as scored, \
         patch.object(auto, "_write_json_atomic", side_effect=AssertionError("writer reached")) as written:
        with pytest.raises(ValueError, match="PF"):
            auto.process_logic_file(path)
    assert scored.call_count == written.call_count == 0
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]
