from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[2]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.adapters import create_adapter  # noqa: E402
from shared_wong_choi.contracts import (  # noqa: E402
    Domain,
    Operation,
    RunIdentity,
    RunRequest,
    RunState,
)


@dataclass(frozen=True)
class Case:
    domain: Domain
    mode: str
    slot: str
    success_status: str


CASES = (
    Case(Domain.AU, "evening", "22:00", "ok"),
    Case(Domain.HKJC, "prerace", "21:30", "succeeded"),
    Case(Domain.TENNIS, "card", "09:00", "succeeded"),
    Case(Domain.NBA, "pregame", "00:30", "complete"),
)


def request(case: Case, *, attempt: int = 1) -> RunRequest:
    return RunRequest(
        identity=RunIdentity(
            case.domain,
            case.mode,
            date(2026, 10, 21),
            case.slot,
            attempt,
        ),
        operation=Operation.PREDICT,
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.domain.value)
def test_all_adapters_share_success_and_duplicate_semantics(
    case: Case, tmp_path: Path
) -> None:
    calls = 0

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"status": case.success_status}) + "\n",
            stderr="",
        )

    adapter = create_adapter(case.domain, REPO_ROOT, tmp_path, runner=runner)
    first = adapter.execute(request(case))
    duplicate = adapter.execute(request(case))
    retry = adapter.execute(request(case, attempt=2))

    assert first.state is RunState.SUCCEEDED
    assert duplicate.state is RunState.SUCCEEDED
    assert duplicate.status == "duplicate_skipped"
    assert retry.state is RunState.SUCCEEDED
    assert calls == 2


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.domain.value)
def test_all_adapters_treat_exit_75_as_partial(case: Case, tmp_path: Path) -> None:
    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            75,
            stdout='{"status":"partial"}\n',
            stderr="retry later",
        )

    result = create_adapter(case.domain, REPO_ROOT, tmp_path, runner=runner).execute(
        request(case)
    )
    assert result.state is RunState.PARTIAL


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.domain.value)
def test_all_adapters_fail_closed_on_exit_zero_without_status(
    case: Case, tmp_path: Path
) -> None:
    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout="ordinary log only\n", stderr="")

    result = create_adapter(case.domain, REPO_ROOT, tmp_path, runner=runner).execute(
        request(case)
    )
    assert result.state is RunState.FAILED
    assert result.status == "missing_status"


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.domain.value)
def test_all_adapters_treat_hard_exit_as_failed_even_if_payload_says_success(
    case: Case, tmp_path: Path
) -> None:
    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            1,
            stdout=json.dumps({"status": case.success_status}) + "\n",
            stderr="hard failure",
        )

    result = create_adapter(case.domain, REPO_ROOT, tmp_path, runner=runner).execute(
        request(case)
    )
    assert result.state is RunState.FAILED

