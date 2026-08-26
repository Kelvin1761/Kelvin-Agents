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
from shared_wong_choi.hkjc_adapter import HKJCAdapter  # noqa: E402


def _request(*, dry_run: bool = False, metadata: dict | None = None) -> RunRequest:
    return RunRequest(
        identity=RunIdentity(Domain.HKJC, "prerace", date(2026, 9, 6), "21:30"),
        operation=Operation.PREDICT,
        dry_run=dry_run,
        metadata=metadata or {},
    )


def test_hkjc_adapter_satisfies_protocol_and_opts_into_control_json(tmp_path: Path) -> None:
    adapter = HKJCAdapter(REPO_ROOT, tmp_path)
    assert isinstance(adapter, DomainAdapter)
    command = adapter.execute(_request(dry_run=True)).detail["command"]
    assert command[-3:] == ["--mode", "prerace", "--control-json"]


def test_hkjc_adapter_passes_explicit_meeting_without_changing_scoring(tmp_path: Path) -> None:
    url = (
        "https://racing.hkjc.com/zh-hk/local/information/racecard"
        "?racedate=2026/09/06&Racecourse=ST&RaceNo=1"
    )
    command = HKJCAdapter(REPO_ROOT, tmp_path).command(
        _request(dry_run=True, metadata={"meeting_url": url, "force": True})
    )
    assert command[-3:] == ["--meeting-url", url, "--force"]


def test_hkjc_dormant_control_envelope_maps_to_dormant(tmp_path: Path) -> None:
    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="HKJC pre-race dormant\n"
            + json.dumps({"status": "dormant", "mode": "prerace", "exit_code": 0})
            + "\n",
            stderr="",
        )

    result = HKJCAdapter(REPO_ROOT, tmp_path, runner=runner).execute(_request())
    assert result.state is RunState.DORMANT

