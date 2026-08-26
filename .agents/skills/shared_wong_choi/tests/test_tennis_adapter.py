from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[2]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.contracts import (  # noqa: E402
    Domain,
    DomainAdapter,
    Operation,
    RunIdentity,
    RunRequest,
    RunState,
)
from shared_wong_choi.tennis_adapter import TennisAdapter  # noqa: E402


def _request(
    operation: Operation = Operation.PREDICT,
    mode: str = "card",
    *,
    dry_run: bool = False,
) -> RunRequest:
    return RunRequest(
        identity=RunIdentity(Domain.TENNIS, mode, date(2026, 8, 26), "09:00"),
        operation=operation,
        dry_run=dry_run,
    )


def test_tennis_adapter_satisfies_protocol_and_builds_card_command(tmp_path: Path) -> None:
    adapter = TennisAdapter(REPO_ROOT, tmp_path)
    assert isinstance(adapter, DomainAdapter)
    command = adapter.execute(_request(dry_run=True)).detail["command"]
    assert command[-6:] == [
        "--today",
        "2026-08-26",
        "--source",
        "control-plane",
        "--control-json",
        "--refresh-today",
    ]


def test_tennis_recovery_uses_guarded_recovery_entrypoint(tmp_path: Path) -> None:
    command = TennisAdapter(REPO_ROOT, tmp_path).command(
        _request(Operation.RECOVER, "recovery", dry_run=True)
    )
    assert command[-3:] == ["--today", "2026-08-26", "--control-json"]
    assert command[1].endswith("tennis_card_recovery.py")


def test_tennis_blocked_envelope_maps_to_blocked(tmp_path: Path) -> None:
    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="scheduler busy\n"
            + json.dumps({"status": "blocked", "mode": "card", "exit_code": 0})
            + "\n",
            stderr="",
        )

    result = TennisAdapter(REPO_ROOT, tmp_path, runner=runner).execute(_request())
    assert result.state is RunState.BLOCKED

