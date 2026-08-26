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
from shared_wong_choi.control import RunManifest  # noqa: E402
from shared_wong_choi.nba_adapter import NBAAdapter  # noqa: E402


def _request(*, attempt: int = 1, dry_run: bool = False) -> RunRequest:
    return RunRequest(
        identity=RunIdentity(
            Domain.NBA,
            "pregame",
            date(2026, 10, 21),
            "00:30",
            attempt,
        ),
        operation=Operation.PREDICT,
        dry_run=dry_run,
    )


def test_nba_adapter_satisfies_protocol_and_builds_dry_run_command(tmp_path: Path) -> None:
    adapter = NBAAdapter(REPO_ROOT, tmp_path)
    assert isinstance(adapter, DomainAdapter)
    result = adapter.execute(_request(dry_run=True))
    command = result.detail["command"]
    assert result.state is RunState.READY
    assert command[-6:] == [
        "--mode",
        "pregame",
        "--date",
        "2026-10-21",
        "--freshness-role",
        "production",
    ]
    assert not (tmp_path / "runs").exists()


def test_nba_adapter_writes_success_manifest_and_deduplicates(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"status": "complete", "target_date": "2026-10-21"}) + "\n",
            stderr="",
        )

    adapter = NBAAdapter(REPO_ROOT, tmp_path, runner=runner)
    first = adapter.execute(_request())
    second = adapter.execute(_request())

    assert first.state is RunState.SUCCEEDED
    assert second.state is RunState.SUCCEEDED
    assert second.status == "duplicate_skipped"
    assert len(calls) == 1
    manifest = RunManifest.load(Path(first.artifacts[0]))
    assert manifest.state is RunState.SUCCEEDED
    assert manifest.payload["operations"][0]["operation"] == "predict"


def test_nba_adapter_records_temporary_exit_as_partial(tmp_path: Path) -> None:
    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            75,
            stdout=json.dumps({"status": "temporary_failure", "error": "odds unavailable"}) + "\n",
            stderr="",
        )

    result = NBAAdapter(REPO_ROOT, tmp_path, runner=runner).execute(_request())
    assert result.state is RunState.PARTIAL
    assert RunManifest.load(Path(result.artifacts[0])).payload["warnings"] == [
        "temporary_failure"
    ]


def test_nba_adapter_fails_closed_when_exit_zero_has_unknown_status(tmp_path: Path) -> None:
    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout='{"status":"probably_fine"}\n', stderr="")

    result = NBAAdapter(REPO_ROOT, tmp_path, runner=runner).execute(_request())
    manifest = RunManifest.load(Path(result.artifacts[0]))
    assert result.state is RunState.FAILED
    assert "unknown Wong Choi run status" in manifest.payload["errors"][0]
