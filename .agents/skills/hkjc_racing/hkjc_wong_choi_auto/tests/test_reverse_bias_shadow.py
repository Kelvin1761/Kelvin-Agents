import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "hkjc_reverse_bias_shadow.py"
SPEC = importlib.util.spec_from_file_location("hkjc_reverse_bias_shadow", SCRIPT)
shadow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shadow)


def _logic(race_no: int) -> dict:
    horses = {}
    for horse_no in range(1, 9):
        horses[str(horse_no)] = {
            "horse_name": f"馬{horse_no}",
            "barrier": horse_no,
            "python_auto": {
                "rank": horse_no,
                "ability_score": 80.0 - horse_no,
            },
        }
    return {
        "race_analysis": {
            "race_number": race_no,
            "venue": "跑馬地",
            "track": "Turf",
        },
        "horses": horses,
    }


def _race(race_no: int, top3: tuple[int, int, int]) -> dict:
    finish_order = list(top3) + [horse for horse in range(1, 9) if horse not in top3]
    rows = []
    for position, horse_no in enumerate(finish_order, start=1):
        rows.append(
            {
                "pos": str(position),
                "horse_no": str(horse_no),
                "horse_name": f"馬{horse_no}(K{horse_no:03d})",
                "draw": str(horse_no),
                "running_positions": f"{horse_no} {horse_no} {position}",
                "win_odds": "99",
            }
        )
    return {"racedate": "2026-10-07", "race_no": race_no, "results": rows}


def _meeting(tmp_path: Path) -> Path:
    meeting = tmp_path / "2026-10-07_HappyValley"
    meeting.mkdir()
    for race_no in range(1, 5):
        (meeting / f"Race_{race_no}_Logic.json").write_text(
            json.dumps(_logic(race_no), ensure_ascii=False), encoding="utf-8"
        )
    return meeting


def test_reverse_bias_snapshot_is_immutable_and_mainline_noop(tmp_path: Path) -> None:
    meeting = _meeting(tmp_path)
    results = tmp_path / "partial.json"
    results.write_text(
        json.dumps(
            {"1": _race(1, (8, 7, 6)), "2": _race(2, (8, 7, 6))},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    before = {
        path.name: path.read_bytes() for path in meeting.glob("Race_*_Logic.json")
    }

    snapshot = shadow.build_snapshot(meeting, results)
    assert snapshot["completed_prefix"] == [1, 2]
    assert [target["race_number"] for target in snapshot["targets"]] == [3, 4]
    for target in snapshot["targets"]:
        assert target["bias"]["status"] == "reverse_bias"
        assert target["baseline_top4"] == [1, 2, 3, 4]
        assert target["shadow_top4"] == [1, 2, 3, 6]
        assert target["alternate"]["horse_number"] == 6
        assert target["candidate_applied"] is True
        assert target["live_score_changed"] is False
        assert [
            row["race_number"] for row in target["bias"]["source_observations"]
        ] == [1, 2]
    assert snapshot["contract"]["draw_is_only_a_proxy_for_lane"] is True
    assert snapshot["contract"]["actual_lane_observed"] is False
    assert "odds" not in json.dumps(snapshot).lower()

    snapshot_dir = tmp_path / "snapshots"
    path, created = shadow.persist_snapshot(snapshot, snapshot_dir)
    assert created is True and path is not None
    reused, created_again = shadow.persist_snapshot(snapshot, snapshot_dir)
    assert reused == path and created_again is False
    assert before == {
        path.name: path.read_bytes() for path in meeting.glob("Race_*_Logic.json")
    }


def test_less_than_two_prior_races_cannot_create_candidate(tmp_path: Path) -> None:
    meeting = _meeting(tmp_path)
    results = tmp_path / "partial.json"
    results.write_text(
        json.dumps({"1": _race(1, (8, 7, 6))}, ensure_ascii=False),
        encoding="utf-8",
    )
    snapshot = shadow.build_snapshot(meeting, results)
    assert snapshot["completed_prefix"] == [1]
    assert snapshot["targets"] == []
    path, created = shadow.persist_snapshot(snapshot, tmp_path / "snapshots")
    assert path is None and created is False


def test_settlement_uses_latest_pre_target_shadow_and_updates_ledger(tmp_path: Path) -> None:
    meeting = _meeting(tmp_path)
    partial = tmp_path / "partial.json"
    partial.write_text(
        json.dumps(
            {"1": _race(1, (8, 7, 6)), "2": _race(2, (8, 7, 6))},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    snapshot = shadow.build_snapshot(meeting, partial)
    snapshot_dir = tmp_path / "snapshots"
    shadow.persist_snapshot(snapshot, snapshot_dir)

    full = tmp_path / "full.json"
    full.write_text(
        json.dumps(
            {
                "1": _race(1, (8, 7, 6)),
                "2": _race(2, (8, 7, 6)),
                "3": _race(3, (1, 2, 6)),
                "4": _race(4, (1, 2, 6)),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    report = shadow.settle(meeting, full, snapshot_dir)
    assert len(report["active_records"]) == 2
    for record in report["active_records"]:
        assert record["baseline"]["gold"] == 0.0
        assert record["candidate"]["gold"] == 1.0

    ledger_path = tmp_path / "ledger.json"
    ledger = shadow.update_ledger(ledger_path, report)
    assert ledger["summary"]["active_races"] == 2
    assert ledger["summary"]["baseline_gold_rate"] == 0.0
    assert ledger["summary"]["candidate_gold_rate"] == 1.0
    assert ledger["summary"]["status"] == "collecting"
    assert ledger["summary"]["auto_promotion"] is False
