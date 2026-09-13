from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from hkjc_research_evidence import build_feature_projection, settlement_artifacts  # noqa: E402


CUTOFF = datetime(2026, 9, 13, 1, 22, 6, tzinfo=timezone.utc)
EVENT = "2026-09-13|ShaTin"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _meeting(root: Path) -> Path:
    folder = root / "2026-09-13_ShaTin"
    folder.mkdir()
    (folder / "09-13 Race 1 Facts.md").write_text(
        "# Facts\nHorse 7 快馬\nlast_6_finishes: 1,2,3\n", encoding="utf-8"
    )
    (folder / "09-13 Race 1 排位表.md").write_text(
        "# Racecard\nHorse 7 barrier 3\n", encoding="utf-8"
    )
    (folder / "2026-09-13 Race 1 晨操.json").write_text(
        json.dumps({"7": {"digest": "positive"}}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (folder / "2026-09-13 Race 1 晨操.md").write_text(
        "# Trackwork\n7 快馬 positive\n", encoding="utf-8"
    )
    (folder / "Race_1_Logic.json").write_text(json.dumps({
        "race_analysis": {"race_number": 1},
        "horses": {"7": {"horse_name": "快馬", "python_auto": {
            "score_provenance": {
                "form_score": "last_6_finishes",
                "draw_score": "barrier",
                "trackwork_trend_score": "trackwork_digest",
            },
        }}},
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    return folder


def test_projection_pins_exact_feature_inputs_without_mutating_meeting(tmp_path: Path) -> None:
    folder = _meeting(tmp_path)
    before = {path.name: path.read_bytes() for path in folder.iterdir()}

    payload = json.loads(build_feature_projection(
        folder, event_id=EVENT, captured_at=CUTOFF,
    ))

    assert payload["event_id"] == EVENT
    assert payload["model_promotion_allowed"] is False
    logic = payload["logic_files"][0]
    assert logic["sha256"] == _sha(folder / "Race_1_Logic.json")
    features = logic["horses"]["7"]
    assert [item["artifact"] for item in features["form_score"]["sources"]] == [
        "09-13 Race 1 Facts.md"
    ]
    assert [item["artifact"] for item in features["draw_score"]["sources"]] == [
        "09-13 Race 1 排位表.md"
    ]
    assert [item["artifact"] for item in features["trackwork_trend_score"]["sources"]] == [
        "2026-09-13 Race 1 晨操.json"
    ]
    for feature in features.values():
        assert all(item["sha256"] == _sha(folder / item["artifact"])
                   for item in feature["sources"])
    assert before == {path.name: path.read_bytes() for path in folder.iterdir()}


@pytest.mark.parametrize(
    ("missing", "match"),
    [
        ("09-13 Race 1 Facts.md", "Facts"),
        ("09-13 Race 1 排位表.md", "Racecard"),
        ("2026-09-13 Race 1 晨操.json", "Trackwork"),
    ],
)
def test_missing_feature_input_fails_closed(tmp_path: Path, missing: str, match: str) -> None:
    folder = _meeting(tmp_path)
    (folder / missing).unlink()

    with pytest.raises(ValueError, match=match):
        build_feature_projection(folder, event_id=EVENT, captured_at=CUTOFF)


def test_unknown_feature_identity_fails_closed(tmp_path: Path) -> None:
    folder = _meeting(tmp_path)
    logic_path = folder / "Race_1_Logic.json"
    logic = json.loads(logic_path.read_text(encoding="utf-8"))
    logic["horses"]["7"]["python_auto"]["score_provenance"]["new_score"] = "new_source"
    logic_path.write_text(json.dumps(logic, ensure_ascii=False) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown HKJC feature"):
        build_feature_projection(folder, event_id=EVENT, captured_at=CUTOFF)


def test_event_identity_and_timezone_cutoff_are_required(tmp_path: Path) -> None:
    folder = _meeting(tmp_path)
    with pytest.raises(ValueError, match="event/folder"):
        build_feature_projection(folder, event_id="2026-09-13|HappyValley", captured_at=CUTOFF)
    with pytest.raises(ValueError, match="timezone-aware"):
        build_feature_projection(
            folder, event_id=EVENT, captured_at=CUTOFF.replace(tzinfo=None),
        )


def test_settlement_artifacts_require_full_results_and_reflector(tmp_path: Path) -> None:
    folder = tmp_path / "2026-09-09_HappyValley"
    folder.mkdir()
    result = folder / "2026-09-09_HappyValley_全日賽果.json"
    report = folder / "HKJC_Reflection_Report.md"
    result.write_text('{"1":{"results":[]}}\n', encoding="utf-8")
    report.write_text("# Reflection\n", encoding="utf-8")

    assert settlement_artifacts(
        folder, event_id="2026-09-09|HappyValley",
    ) == (result, report)


def test_settlement_artifacts_reject_missing_or_ambiguous_results(tmp_path: Path) -> None:
    folder = tmp_path / "2026-09-09_HappyValley"
    folder.mkdir()
    (folder / "HKJC_Reflection_Report.md").write_text("# Reflection\n", encoding="utf-8")
    with pytest.raises(ValueError, match="canonical HKJC result"):
        settlement_artifacts(folder, event_id="2026-09-09|HappyValley")
    for name in ("one_全日賽果.json", "two_全日賽果.json"):
        (folder / name).write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        settlement_artifacts(folder, event_id="2026-09-09|HappyValley")
