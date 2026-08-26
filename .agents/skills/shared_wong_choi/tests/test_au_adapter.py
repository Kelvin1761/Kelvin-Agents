from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[2]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.au_adapter import AUAdapter  # noqa: E402
from shared_wong_choi.contracts import (  # noqa: E402
    Domain,
    DomainAdapter,
    Operation,
    RunIdentity,
    RunRequest,
    RunState,
)


def _request(
    operation: Operation = Operation.PREDICT,
    mode: str = "evening",
    *,
    dry_run: bool = False,
) -> RunRequest:
    return RunRequest(
        identity=RunIdentity(Domain.AU, mode, date(2026, 8, 26), "22:00"),
        operation=operation,
        dry_run=dry_run,
    )


def test_au_adapter_satisfies_protocol_and_builds_scheduler_command(tmp_path: Path) -> None:
    adapter = AUAdapter(REPO_ROOT, tmp_path)
    assert isinstance(adapter, DomainAdapter)
    result = adapter.execute(_request(dry_run=True))
    assert result.state is RunState.READY
    assert result.detail["command"][-5:] == [
        "--mode",
        "evening",
        "--today",
        "2026-08-26",
        "--json",
    ]


def test_au_healthcheck_uses_positional_date(tmp_path: Path) -> None:
    command = AUAdapter(REPO_ROOT, tmp_path).command(
        _request(Operation.HEALTH, "healthcheck", dry_run=True)
    )
    assert command[-1] == "2026-08-26"
    assert "--mode" not in command


def test_au_pretty_runlog_maps_to_success(tmp_path: Path) -> None:
    payload = {"status": "ok", "mode": "evening", "steps": []}

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="log before json\n" + json.dumps(payload, indent=2) + "\n",
            stderr="",
        )

    result = AUAdapter(REPO_ROOT, tmp_path, runner=runner).execute(_request())
    assert result.state is RunState.SUCCEEDED
    assert result.detail["source_payload"] == payload


def test_au_health_degraded_is_partial_even_with_exit_one(tmp_path: Path) -> None:
    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            1,
            stdout=json.dumps({"state": "degraded"}, indent=2) + "\n",
            stderr="",
        )

    result = AUAdapter(REPO_ROOT, tmp_path, runner=runner).execute(
        _request(Operation.HEALTH, "healthcheck")
    )
    # Non-temporary non-zero exit always wins over source wording.
    assert result.state is RunState.FAILED
