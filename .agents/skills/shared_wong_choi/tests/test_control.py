from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.contracts import Domain, Operation, RunIdentity, RunState  # noqa: E402
from shared_wong_choi.control import (  # noqa: E402
    ManifestExistsError,
    RetryPolicy,
    RunManifest,
    manifest_path,
    single_run_lock,
)


def _identity(attempt: int = 1) -> RunIdentity:
    return RunIdentity(Domain.AU, "evening", date(2026, 8, 26), "22:00", attempt)


def test_manifest_is_attempt_specific_and_idempotency_stays_stable(tmp_path: Path) -> None:
    first = manifest_path(tmp_path, _identity(1))
    retry = manifest_path(tmp_path, _identity(2))
    assert first != retry
    assert first.name == "attempt-1.json"
    assert retry.name == "attempt-2.json"


def test_manifest_records_operations_and_freezes_at_terminal_state(tmp_path: Path) -> None:
    path = manifest_path(tmp_path, _identity())
    started = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
    manifest = RunManifest.create(path, _identity(), at=started)
    manifest.transition(RunState.RUNNING, at=started)
    manifest.record_operation(
        Operation.DISCOVER,
        "ok",
        at=started,
        artifacts=("meeting-index.json",),
        detail={"events": 3},
    )
    manifest.transition(RunState.SUCCEEDED, at=started)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["state"] == "succeeded"
    assert saved["operations"][0]["detail"] == {"events": 3}
    assert saved["completed_at"] == started.isoformat()
    assert not list(path.parent.glob("*.tmp"))

    with pytest.raises(ValueError, match="invalid run transition"):
        manifest.transition(RunState.RUNNING)
    with pytest.raises(ValueError, match="only be recorded"):
        manifest.record_operation(Operation.PUBLISH, "late")


def test_existing_attempt_manifest_cannot_be_overwritten(tmp_path: Path) -> None:
    path = manifest_path(tmp_path, _identity())
    RunManifest.create(path, _identity())
    with pytest.raises(ManifestExistsError):
        RunManifest.create(path, _identity())


def test_manifest_requires_timezone_aware_timestamp(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        RunManifest.create(
            manifest_path(tmp_path, _identity()),
            _identity(),
            at=datetime(2026, 8, 26, 12, 0),
        )


def test_retry_policy_only_retries_temporary_codes_before_last_attempt() -> None:
    policy = RetryPolicy(max_attempts=3)
    assert policy.should_retry(exit_code=75, attempt=1)
    assert policy.should_retry(exit_code=124, attempt=2)
    assert not policy.should_retry(exit_code=1, attempt=1)
    assert not policy.should_retry(exit_code=75, attempt=3)


def test_single_run_lock_rejects_overlap_and_releases_afterward(tmp_path: Path) -> None:
    path = tmp_path / "control.lock"
    with single_run_lock(path) as first:
        assert first is True
        with single_run_lock(path) as second:
            assert second is False
    with single_run_lock(path) as third:
        assert third is True
