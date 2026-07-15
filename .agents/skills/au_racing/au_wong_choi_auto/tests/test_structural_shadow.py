import copy
import hashlib
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/au_structural_shadow.py"
SPEC = importlib.util.spec_from_file_location("au_structural_shadow", SCRIPT)
shadow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shadow)


def sample_logic():
    horses = {}
    for number in range(1, 5):
        horses[str(number)] = {
            "horse_name": f"Horse {number}",
            "_data": {
                "current_market_first": float(number),
                "current_market_trend": "firming",
                "timing_600m_recent_speed": 16.5 + number * 0.1,
                "timing_600m_avg_speed": 16.4 + number * 0.1,
                "pf_metrics": {
                    "pf_aggregates": {
                        "race_time_diff_avg": 0.2 - number * 0.1,
                        "race_time_diff_best": 0.1 - number * 0.1,
                        "l600_delta_avg": -0.2 * number,
                        "l600_delta_best": -0.3 * number,
                        "pf_run_count": 3,
                    }
                },
            },
            "python_auto": {
                "ability_score": 60.0 + number,
                "matrix_scores": {
                    "stability": 58.0 + number,
                    "pace_perf": 57.0 + number,
                    "race_shape": 56.0 + number,
                    "jockey_trainer": 55.0 + number,
                    "class_weight": 54.0 + number,
                    "track": 53.0 + number,
                    "form_line": 52.0 + number,
                },
            },
        }
    return {
        "race_analysis": {
            "race_number": 1,
            "speed_map": {
                "predicted_pace": "正常",
                "leaders": [1],
                "pressers": [2],
                "mid_pack": [3],
                "closers": [4],
            },
        },
        "horses": horses,
    }


def test_shadow_scores_ignore_market_fields(tmp_path):
    config = json.loads(shadow.DEFAULT_CONFIG.read_text(encoding="utf-8"))
    assert config["market_inputs"] is False
    path = tmp_path / "Race_1_Logic.json"
    logic = sample_logic()
    path.write_text(json.dumps(logic), encoding="utf-8")
    first = shadow.score_logic(path, config)

    changed = copy.deepcopy(logic)
    for number, horse in changed["horses"].items():
        horse["_data"]["current_market_first"] = 10000.0 + int(number)
        horse["_data"]["current_market_trend"] = "drifting"
    path.write_text(json.dumps(changed), encoding="utf-8")
    second = shadow.score_logic(path, config)

    score_keys = ("performance_shadow_score", "pairwise_shape_shadow_score")
    assert [[row[key] for key in score_keys] for row in first] == [[row[key] for key in score_keys] for row in second]


def test_meeting_shadow_does_not_mutate_logic(tmp_path):
    path = tmp_path / "Race_1_Logic.json"
    path.write_text(json.dumps(sample_logic(), indent=2), encoding="utf-8")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    output, rows = shadow.write_meeting_shadow(tmp_path)
    after = hashlib.sha256(path.read_bytes()).hexdigest()

    assert before == after
    assert output.exists()
    assert len(rows) == 4
    assert all("baseline_rank" in row and "pairwise_shape_shadow_rank" in row for row in rows)
