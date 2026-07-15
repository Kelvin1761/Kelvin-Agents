import copy
import hashlib
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/au_dual_objective_shadow.py"
SPEC = importlib.util.spec_from_file_location("au_dual_objective_shadow", SCRIPT)
shadow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shadow)


def sample_logic():
    horses = {}
    for number in range(1, 5):
        horses[str(number)] = {
            "horse_name": f"Horse {number}",
            "_data": {"current_market_first": number, "current_market_trend": "firming"},
            "python_auto": {
                "ability_score": 64.0 - number,
                "matrix_scores": {
                    "stability": 54.0 + number,
                    "pace_perf": 55.0 + number,
                    "race_shape": 56.0 + number,
                    "jockey_trainer": 57.0 + number,
                    "class_weight": 58.0 + number,
                    "track": 59.0 + number,
                    "form_line": 60.0 + number,
                },
            },
        }
    return {
        "race_analysis": {
            "race_number": 1,
            "distance": "1200m",
            "going": "Soft 5",
            "meeting_intelligence": {"venue": "Test Track", "date": "2026-07-12"},
        },
        "horses": horses,
    }


def write_formguide(meeting: Path, flucs="$4 $5"):
    lines = []
    for number in range(1, 5):
        lines.extend([
            f"[{number}] Horse {number} ({number})",
            (
                f"Test Track R1 2026-06-01 1200m cond:5 $30,000 Jockey ({number}) 57kg "
                f"Flucs:{flucs} 01:10.000 margin:{number} PF[Last600: 35.0 Runner Time: 70.0 "
                f"Race Time: {number / 10:.2f} Early Runner Pace: Moderate. Early Race Pace: Fast. "
                f"L800 Delta: {-number / 10:.2f} L600 Delta: {-number / 8:.2f} "
                f"L400 Delta: {-number / 12:.2f} L200 Delta: {-number / 15:.2f} Tempo QRank: 0.5]"
            ),
        ])
    (meeting / "Test Race 1 Formguide.md").write_text("\n".join(lines), encoding="utf-8")


def score_values(rows):
    keys = (
        "place_rating_score", "coverage_7d_score", "coverage_pf_score",
        "place_rating_rank", "coverage_7d_rank", "coverage_pf_rank",
    )
    return [[row[key] for key in keys] for row in sorted(rows, key=lambda row: row["horse_number"])]


def test_model_pack_checksum_and_market_free_metadata():
    pack = shadow.load_model_pack()
    assert pack["version"] == "AU_DUAL_OBJECTIVE_SHADOW_V1"
    assert pack["market_inputs"] is False


def test_scores_ignore_logic_market_and_formguide_flucs(tmp_path):
    logic_path = tmp_path / "Race_1_Logic.json"
    logic = sample_logic()
    logic_path.write_text(json.dumps(logic), encoding="utf-8")
    write_formguide(tmp_path, "$2 $3")
    first = shadow.score_meeting(tmp_path)

    changed = copy.deepcopy(logic)
    for horse in changed["horses"].values():
        horse["_data"]["current_market_first"] = 9999
        horse["_data"]["current_market_trend"] = "drifting"
    logic_path.write_text(json.dumps(changed), encoding="utf-8")
    write_formguide(tmp_path, "$101 $151")
    second = shadow.score_meeting(tmp_path)
    assert score_values(first) == score_values(second)


def test_shadow_does_not_mutate_logic(tmp_path):
    logic_path = tmp_path / "Race_1_Logic.json"
    logic_path.write_text(json.dumps(sample_logic(), indent=2), encoding="utf-8")
    write_formguide(tmp_path)
    before = hashlib.sha256(logic_path.read_bytes()).hexdigest()
    output, rows = shadow.write_meeting_shadow(tmp_path)
    after = hashlib.sha256(logic_path.read_bytes()).hexdigest()
    assert before == after
    assert output.exists()
    assert len(rows) == 4


def test_review_updates_tracker_and_persistent_status(tmp_path):
    meeting = tmp_path / "2026-07-12 Test Track Race 1-1"
    meeting.mkdir()
    (meeting / "Race_1_Logic.json").write_text(json.dumps(sample_logic()), encoding="utf-8")
    write_formguide(meeting)
    results = meeting / "Race_Results_Test.md"
    results.write_text(
        "## Race 1: Test\n\n| Finish | No | Horse |\n|---:|---:|---|\n"
        "| 1 | 1 | Horse 1 |\n| 2 | 2 | Horse 2 |\n| 3 | 3 | Horse 3 |\n| 4 | 4 | Horse 4 |\n",
        encoding="utf-8",
    )
    _, review_path, status_path = shadow.run_review(meeting, results)
    # Re-running the same reflector meeting replaces its batch JSON; it must
    # not double-count forward races.
    shadow.run_review(meeting, results)
    tracker = json.loads((tmp_path / shadow.TRACKER_JSON).read_text(encoding="utf-8"))
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert review_path.exists()
    assert tracker["forward_races"] == 1
    assert tracker["official_model_changed"] is False
    assert tracker["distance_family_counts"]["Sprint <=1400m"] == 1
    assert not any(item["promotion_eligible"] for item in tracker["candidates"].values())
    assert status["status"] == "updated"
    assert status["official_model_changed"] is False


def test_canary_cannot_start_before_gate_passes(tmp_path):
    tracker = {
        "model_version": "AU_DUAL_OBJECTIVE_SHADOW_V1",
        "forward_races": 8,
        "candidates": {candidate: {"promotion_eligible": False} for candidate in shadow.CANDIDATES},
    }
    (tmp_path / shadow.TRACKER_JSON).write_text(json.dumps(tracker), encoding="utf-8")
    try:
        shadow.approve_canary(tmp_path, "place_rating")
    except ValueError as exc:
        assert "not promotion-eligible" in str(exc)
    else:
        raise AssertionError("Canary approval should be rejected before the gate passes")
