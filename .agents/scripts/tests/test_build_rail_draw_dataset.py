from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "build_rail_draw_dataset.py"
SPEC = importlib.util.spec_from_file_location("build_rail_draw_dataset", SCRIPT)
assert SPEC and SPEC.loader
rail = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rail)


def _result_payload(*, with_header: bool = False) -> dict:
    sectional = []
    if with_header:
        sectional = [
            ["第四班 - 1200米", "場地狀況 :", "好地"],
            ["測試讓賽", "賽道 :", '草地 - "C+3" 賽道'],
        ]
    return {
        "1": {
            "race_no": 1,
            "racedate": "2026-09-23" if with_header else "",
            "venue": "HappyValley" if with_header else "",
            "sectional_times": sectional,
            "results": [
                {"pos": "1", "horse_no": "4", "draw": "9", "running_positions": "11 10 8 1"},
                {"pos": "2", "horse_no": "2", "draw": "2", "running_positions": "3 3 2 2"},
            ],
        }
    }


def test_current_meeting_results_are_discovered(tmp_path: Path) -> None:
    meeting = tmp_path / "2026-09-23_HappyValley"
    meeting.mkdir()
    result = meeting / "2026-09-23_HappyValley_全日賽果.json"
    result.write_text(json.dumps(_result_payload(with_header=True)), encoding="utf-8")

    files = rail.result_files(hk_root=tmp_path, db_root=tmp_path / "db", legacy_root=tmp_path / "legacy")

    assert files == [result]


def test_logic_backfills_missing_result_metadata_and_position(tmp_path: Path) -> None:
    meeting = tmp_path / "2026-09-23_HappyValley"
    meeting.mkdir()
    result = meeting / "2026-09-23_HappyValley_全日賽果.json"
    result.write_text(json.dumps(_result_payload()), encoding="utf-8")
    (meeting / "Race_1_Logic.json").write_text(
        json.dumps(
            {
                "race_analysis": {
                    "race_date": "2026-09-23",
                    "venue": "跑馬地",
                    "track": "Turf",
                    "distance": "1650m",
                    "rail": "C",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows = rail.collect([result])

    assert len(rows) == 2
    assert rows[0]["Date"] == "2026-09-23"
    assert rows[0]["Venue"] == "跑馬地"
    assert rows[0]["Distance"] == 1650
    assert rows[0]["Rail"] == "C"
    assert rows[0]["FieldSize"] == 2
    assert rows[0]["FirstCall"] == 11
    assert rows[0]["EarlyGroup"] == "back_9_plus"
    assert rail.metadata_coverage(rows)["coverage"] == 1.0


def test_inline_result_header_handles_multi_digit_rail_offset(tmp_path: Path) -> None:
    result = tmp_path / "full_day_results.json"
    payload = _result_payload(with_header=True)
    payload["1"]["sectional_times"][1][1] = "草地 - C+12 賽道"
    result.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    rows = rail.collect([result])

    assert {row["Rail"] for row in rows} == {"C+12"}
    assert {row["Track"] for row in rows} == {"Turf"}
    assert {row["Going"] for row in rows} == {"好地"}


def test_dates_are_normalized_before_sorting_or_deduplication() -> None:
    assert rail.normalise_date("2026/05/13") == "2026-05-13"
    assert rail.normalise_date("meeting 2026-09-23 Happy Valley") == "2026-09-23"


def test_first_call_rejects_concatenated_positions():
    assert rail.first_call_position("4 5 5 1", 12) == 4
    assert rail.first_call_position("332", 14) == 0          # 3-3-2 or 33-2: refuse
    assert rail.first_call_position("101010093", 14) == 0
    assert rail.first_call_position("9", 12) == 9             # single short call is fine
    assert rail.first_call_position("15 14", 14) == 0         # beyond HK max field
    assert rail.first_call_position("", 12) == 0
