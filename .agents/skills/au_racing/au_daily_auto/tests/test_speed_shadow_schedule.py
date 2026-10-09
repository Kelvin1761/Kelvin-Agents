from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import au_daily_schedule as schedule  # noqa: E402


class RunLog:
    def __init__(self) -> None:
        self.steps = []
        self.warnings = []

    def step(self, name: str, status: str, **detail) -> None:
        self.steps.append({"step": name, "status": status, **detail})

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def test_schedule_records_blind_shadow_health_without_outcomes(tmp_path: Path) -> None:
    work = tmp_path / "work"

    def fake_run(cmd, **_kwargs):
        output = Path(cmd[cmd.index("--output") + 1])
        output.parent.mkdir(parents=True)
        output.write_text(json.dumps({
            "state": "collecting",
            "outcomes_visible": False,
            "races_collected": 123,
            "race_days": 8,
            "runner_coverage_pct": 76.5,
            "config": {"target_races": 2000},
        }), encoding="utf-8")
        return 0, "blind collection"

    runlog = RunLog()
    with mock.patch.multiple(schedule, WORK_DIR=work, run_cmd=fake_run):
        assert schedule.step_speed_shadow(runlog) is True

    final = runlog.steps[-1]
    assert final["status"] == "collecting"
    assert final["races"] == 123
    assert final["outcomes_visible"] is False
    assert runlog.warnings == []


def test_schedule_never_blocks_live_work_when_shadow_fails(tmp_path: Path) -> None:
    runlog = RunLog()
    with mock.patch.multiple(
            schedule, WORK_DIR=tmp_path, run_cmd=lambda *_args, **_kwargs: (1, "boom")):
        assert schedule.step_speed_shadow(runlog) is False

    assert runlog.steps[-1]["status"] == "failed"
    assert "唔影響 live 排名" in runlog.warnings[0]


def test_passed_stage4_writes_one_immutable_candidate_gate(tmp_path: Path) -> None:
    work = tmp_path / "work"
    proposal = {
        "status": "passed",
        "proposal_sha256": "a" * 64,
        "candidate": {
            "name": "global_add",
            "formula": "final_rank_score + 0.5 * within_race_z(speed_best3)",
        },
    }

    def fake_run(cmd, **_kwargs):
        output = Path(cmd[cmd.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({
            "state": "ready_for_manual_stage4_review",
            "outcomes_visible": True,
            "races_collected": 2003,
            "race_days": 55,
            "runner_coverage_pct": 78.2,
            "sample_sha256": "b" * 64,
            "config": {
                "experiment_id": "EXP-20260927-02",
                "target_races": 2000,
                "config_sha256": "c" * 64,
            },
            "stage4_decision": {
                "verdict": "PRIMARY_WIN",
                "reason": "gold_or_good_supported_gain",
                "development_evidence": {"gold_delta_pp": 0.43},
                "terminal_primary": {"gold_delta_pp": 0.8},
                "guardrails": {"supported_regressions": []},
                "release_proposal": proposal,
            },
        }), encoding="utf-8")
        return 0, "terminal locked"

    runlog = RunLog()
    with mock.patch.multiple(schedule, WORK_DIR=work, run_cmd=fake_run):
        assert schedule.step_speed_shadow(runlog) is True
        assert schedule.step_speed_shadow(runlog) is True

    gate = json.loads((work / "AU_Speed_Candidate_Gate.json").read_text())
    assert gate["status"] == "passed"
    assert gate["verdict"] == "PRIMARY_WIN"
    assert gate["approval_required"] is True
    assert gate["automatic_activation"] is False
    assert gate["stage4_evidence"]["terminal_primary"]["gold_delta_pp"] == 0.8
    assert len(gate["gate_sha256"]) == 64
    assert sum("/approve SHA" in message for message in runlog.warnings) == 1


def test_recency_arm_records_counts_only_while_blind(tmp_path):
    """EXP-20261009-05：未揭盲只記場數，唔出 verdict。"""
    import json as _json
    from unittest import mock as _mock

    def fake_run(cmd, timeout=None):
        out = Path(cmd[cmd.index("--output") + 1])
        out.write_text(_json.dumps({"state": "collecting", "races_collected": 457,
                                    "outcomes_visible": False}), encoding="utf-8")
        return 0, ""

    steps = []

    class Log:
        def step(self, name, status, **kw):
            steps.append((name, status, kw))

        def warn(self, message):
            steps.append(("warn", message, {}))

    with _mock.patch.multiple(schedule, WORK_DIR=tmp_path, run_cmd=fake_run):
        assert schedule.step_speed_recency_shadow(Log()) is True
    assert steps == [("speed-recency-shadow", "collecting",
                      {"races": 457, "outcomes_visible": False, "verdict": ""})]
