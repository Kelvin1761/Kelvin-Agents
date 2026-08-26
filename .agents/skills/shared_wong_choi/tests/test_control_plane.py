from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[2]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi import control_plane as M  # noqa: E402
from shared_wong_choi.contracts import (  # noqa: E402
    Domain,
    Operation,
    OperationResult,
    RunIdentity,
    RunRequest,
    RunState,
)
from shared_wong_choi.control import RetryPolicy  # noqa: E402


SYDNEY = ZoneInfo("Australia/Sydney")


def test_warmup_slot_targets_tomorrow_and_builds_role_command(
    tmp_path: Path, capsys
) -> None:
    code = M.main(
        [
            "--domain",
            "nba",
            "--mode",
            "pregame",
            "--freshness-role",
            "warmup",
            "--state-root",
            str(tmp_path),
            "--dry-run",
        ],
        now=datetime(2026, 10, 20, 21, 4, tzinfo=SYDNEY),
        repo_root=REPO_ROOT,
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["target_date"] == "2026-10-21"
    assert payload["scheduled_slot"] == "21:00"
    assert payload["severity"] == "info"
    assert payload["notification_dedup_key"].startswith("wc-op:")
    assert payload["detail"]["command"][-2:] == ["--freshness-role", "warmup"]
    assert not (tmp_path / "runs").exists()


def test_fixed_domain_slot_is_stable_when_launchd_wakes_late() -> None:
    now = datetime(2026, 8, 26, 22, 47, tzinfo=SYDNEY)
    assert M.infer_slot(Domain.AU, "evening", now=now) == "22:00"
    assert M.infer_slot(Domain.TENNIS, "daily", now=now) == "18:00"


def test_unknown_domain_mode_fails_closed() -> None:
    try:
        M.primary_operation(Domain.NBA, "mystery")
    except ValueError as exc:
        assert "no control-plane operation" in str(exc)
    else:
        raise AssertionError("unknown mode unexpectedly accepted")


def test_temporary_failure_retries_with_new_immutable_attempt() -> None:
    calls: list[int] = []

    class Adapter:
        def execute(self, request: RunRequest) -> OperationResult:
            calls.append(request.identity.attempt)
            if request.identity.attempt == 1:
                return OperationResult(
                    RunState.PARTIAL,
                    "temporary_failure",
                    detail={"exit_code": 75},
                )
            return OperationResult(RunState.SUCCEEDED, "complete", detail={"exit_code": 0})

    request = RunRequest(
        RunIdentity(Domain.NBA, "pregame", date(2026, 10, 21), "00:30"),
        Operation.PREDICT,
    )
    result = M.execute_with_retry(Adapter(), request, RetryPolicy(max_attempts=3))
    assert result.state is RunState.SUCCEEDED
    assert calls == [1, 2]


def test_scheduler_specific_options_are_forwarded_after_control_options(
    tmp_path: Path, capsys
) -> None:
    code = M.main(
        [
            "--domain",
            "au",
            "--mode",
            "morning",
            "--state-root",
            str(tmp_path),
            "--dry-run",
            "--rounds",
            "3",
            "--round-gap",
            "420",
        ],
        now=datetime(2026, 8, 26, 10, 1, tzinfo=SYDNEY),
        repo_root=REPO_ROOT,
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["detail"]["command"][-4:] == [
        "--rounds",
        "3",
        "--round-gap",
        "420",
    ]
