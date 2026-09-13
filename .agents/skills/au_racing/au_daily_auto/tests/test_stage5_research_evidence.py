from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from au_research_evidence import build_feature_projection, settlement_artifacts  # noqa: E402


CUTOFF = datetime(2026, 9, 13, 0, 30, tzinfo=timezone.utc)
EVENT = "2026-09-13 Test Race 1-1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _meeting(root: Path, *, odds: bool = True) -> Path:
    folder = root / EVENT
    folder.mkdir()
    for kind in ("Racecard", "Formguide", "Facts"):
        (folder / f"09-13 Race 1 {kind}.md").write_text(
            f"# Race 1 {kind}\nHorse 7 Fast Horse\n", encoding="utf-8"
        )
    (folder / "Race_1_Logic.json").write_text(json.dumps({
        "race_analysis": {"race_number": 1},
        "horses": {"7": {"horse_name": "Fast Horse", "python_auto": {
            "score_provenance": {
                "form_score": "recent_form+class_weighted",
                "pace_figure_score": "facts_form_rows",
            },
        }}},
    }) + "\n", encoding="utf-8")
    if odds:
        (folder / "odds_history.json").write_text(json.dumps({
            "1": {
                "2026-09-13T00:20:00|morning-refresh": {"7": ["3.0", "1.5"]},
                "2026-09-12T23:55:00|analysis": {"7": ["4.0", "1.8"]},
                "2026-09-12T23:50:00|analysis": {"7": ["4.2", "1.9"]},
            }
        }) + "\n", encoding="utf-8")
    return folder


def test_projection_pins_all_pre_race_inputs_and_earliest_analysis_odds(tmp_path: Path) -> None:
    folder = _meeting(tmp_path)
    before = {path.name: path.read_bytes() for path in folder.iterdir()}

    payload = json.loads(build_feature_projection(folder, captured_at=CUTOFF))

    assert payload["event_id"] == EVENT
    assert payload["model_promotion_allowed"] is False
    logic = payload["logic_files"][0]
    assert logic["sha256"] == _sha(folder / "Race_1_Logic.json")
    sources = logic["horses"]["7"]["form_score"]["sources"]
    assert {item["artifact"] for item in sources} == {
        "09-13 Race 1 Racecard.md",
        "09-13 Race 1 Formguide.md",
        "09-13 Race 1 Facts.md",
    }
    assert all(item["sha256"] == _sha(folder / item["artifact"]) for item in sources)
    assert payload["market"]["earliest_analysis"]["1"]["snapshot_key"] == (
        "2026-09-12T23:50:00|analysis"
    )
    assert payload["market"]["earliest_analysis"]["1"]["prices"] == {
        "7": ["4.2", "1.9"]
    }
    assert before == {path.name: path.read_bytes() for path in folder.iterdir()}


def test_projection_never_substitutes_morning_price_for_missing_analysis_price(tmp_path: Path) -> None:
    folder = _meeting(tmp_path)
    odds = folder / "odds_history.json"
    odds.write_text(json.dumps({
        "1": {"2026-09-13T00:20:00|morning-refresh": {"7": ["3.0", "1.5"]}}
    }) + "\n", encoding="utf-8")

    payload = json.loads(build_feature_projection(folder, captured_at=CUTOFF))

    assert payload["market"]["status"] == "missing_analysis"
    assert payload["market"]["earliest_analysis"] == {}


@pytest.mark.parametrize("missing", ["Racecard", "Formguide", "Facts"])
def test_missing_required_prediction_input_fails_closed(tmp_path: Path, missing: str) -> None:
    folder = _meeting(tmp_path)
    next(folder.glob(f"* {missing}.md")).unlink()

    with pytest.raises(ValueError, match="missing pre-race input"):
        build_feature_projection(folder, captured_at=CUTOFF)


def test_naive_or_pre_input_cutoff_is_rejected(tmp_path: Path) -> None:
    folder = _meeting(tmp_path)
    with pytest.raises(ValueError, match="timezone-aware"):
        build_feature_projection(folder, captured_at=CUTOFF.replace(tzinfo=None))
    odds = folder / "odds_history.json"
    odds.write_text(json.dumps({
        "1": {"2026-09-13T12:00:00|analysis": {"7": ["3.0", "1.5"]}}
    }) + "\n", encoding="utf-8")
    payload = json.loads(build_feature_projection(folder, captured_at=CUTOFF))
    assert payload["market"]["status"] == "missing_analysis"


def test_settlement_artifacts_require_canonical_results_and_reflector(tmp_path: Path) -> None:
    event = "2026-09-12 Test Race 1-1"
    folder = tmp_path / event
    folder.mkdir(parents=True)
    result = folder / "Race_Results_Reflector.md"
    report = folder / f"{event}_Reflector_Report.md"
    result.write_text("# canonical result\n", encoding="utf-8")
    report.write_text("# review\n", encoding="utf-8")

    assert settlement_artifacts(folder, event_id=event) == (result, report)


def test_settlement_artifacts_fail_closed_when_canonical_result_is_missing(tmp_path: Path) -> None:
    event = "2026-09-12 Test Race 1-1"
    folder = tmp_path / event
    folder.mkdir(parents=True)
    (folder / f"{event}_Reflector_Report.md").write_text("# review\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Race_Results_Reflector.md"):
        settlement_artifacts(folder, event_id=event)
