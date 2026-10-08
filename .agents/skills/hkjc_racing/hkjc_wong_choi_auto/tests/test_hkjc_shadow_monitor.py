from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import hkjc_shadow_monitor as monitor  # noqa: E402


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> Path:
    meeting = tmp_path / "2026-10-01_HappyValley"
    snapshot = meeting / "Prediction_Snapshots" / "20261001T120000+1000"
    snapshot.mkdir(parents=True)
    ranking = [1, 2, 3, 4, 5, 6]
    candidate = [1, 2, 5, 3, 4, 6]

    def rows(values: list[int], *, applied: bool) -> list[dict]:
        return [
            {"horse_number": str(number), "ability_score": 90 - index, "applied": applied}
            for index, number in enumerate(values)
        ]

    logic = {
        "race_analysis": {"race_number": 1, "venue": "跑馬地"},
        "python_auto_verdict": {"ranking": rows(ranking, applied=False)},
        "python_auto_shadow_verdicts": {
            profile: {"profile": profile, "ranking": rows(candidate, applied=True)}
            for profile in monitor.PROFILE_MINIMUMS
        },
    }
    logic_path = snapshot / "Race_1_Logic.json"
    logic_path.write_text(json.dumps(logic), encoding="utf-8")
    manifest = {
        "immutable_prediction_snapshot": True,
        "created_at": "2026-10-01T12:00:00+10:00",
        "signature": "fixture-signature",
        "files": [
            {
                "name": logic_path.name,
                "size": logic_path.stat().st_size,
                "sha256": _digest(logic_path),
            }
        ],
    }
    (snapshot / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    results = {
        "1": {
            "results": [
                {"pos": 1, "horse_no": 1},
                {"pos": 2, "horse_no": 2},
                {"pos": 3, "horse_no": 5},
                {"pos": 4, "horse_no": 3},
                {"pos": 5, "horse_no": 4},
                {"pos": 6, "horse_no": 6},
            ]
        }
    }
    (meeting / "2026-10-01_HV_全日賽果.json").write_text(json.dumps(results), encoding="utf-8")
    return meeting


def test_monitor_uses_immutable_snapshot_and_upserts_idempotently(tmp_path: Path) -> None:
    meeting = _fixture(tmp_path)
    ledger = tmp_path / "ledger.json"

    first = monitor.update_ledger(meeting, ledger)
    second = monitor.update_ledger(meeting, ledger)

    assert len(first["rows"]) == len(monitor.PROFILE_MINIMUMS)
    assert len(second["rows"]) == len(monitor.PROFILE_MINIMUMS)
    assert all(row["delta"]["gold"] == 1.0 for row in second["rows"])
    assert second["summary"]["weight_refit_t02"]["active_races"] == 1
    assert second["summary"]["weight_refit_t02"]["status"] == "collecting"
    assert second["summary"]["weight_refit_t02"]["promotion_blocked"] is True
    assert second["summary"]["race_shape_v2_legacy_hv"]["decision_role"] == "rollback_comparator"
    assert second["summary"]["race_shape_st_draw70"]["decision_role"] == "sha_tin_forward_candidate"
    assert second["summary"]["race_shape_legacy_unbounded"]["decision_role"] == "whole_field_robustness_rollback_comparator"
    assert second["summary"]["complete_strength_legacy_ability_only"]["decision_role"] == "complete_strength_rollback_comparator"
    assert second["summary"]["trainer_recency_st_early90"]["decision_role"] == "sha_tin_early_season_trainer_candidate"
    assert second["summary"]["pre_race_draw_context_v2"]["decision_role"] == "all_turf_pre_race_draw_candidate"
    assert second["summary"]["pre_race_draw_context_v1_generic"]["decision_role"] == "rail_draw_v1_rollback_comparator"


def test_monitor_rejects_snapshot_tampering(tmp_path: Path) -> None:
    meeting = _fixture(tmp_path)
    logic = next((meeting / "Prediction_Snapshots").glob("*/Race_1_Logic.json"))
    logic.write_text(logic.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="snapshot hash mismatch"):
        monitor.update_ledger(meeting, tmp_path / "ledger.json")


def test_whole_field_rollback_gate_requires_80_races_and_two_primary_wins() -> None:
    def row(*, gold: float, good: float) -> dict:
        return {
            "profile": "race_shape_legacy_unbounded",
            "profile_applied": True,
            "venue": "沙田",
            "surface": "草地",
            "baseline": {metric: 0.0 for metric in monitor.METRICS},
            "candidate": {metric: 0.0 for metric in monitor.METRICS},
            "delta": {
                **{metric: 0.0 for metric in monitor.METRICS},
                "gold": gold,
                "good": good,
            },
        }

    collecting = monitor.summarize([row(gold=1.0, good=0.0) for _ in range(79)])
    assert collecting["race_shape_legacy_unbounded"]["rollback_gate"]["status"] == "retain_experimental_live"

    ready = monitor.summarize(
        [row(gold=1.0, good=0.0), row(gold=1.0, good=0.0)]
        + [row(gold=0.0, good=0.0) for _ in range(78)]
    )
    profile = ready["race_shape_legacy_unbounded"]
    assert profile["status"] == "ready_for_locked_review"
    assert profile["rollback_gate"]["status"] == "recommend_rollback"
    assert profile["rollback_gate"]["automatic_activation"] is False
