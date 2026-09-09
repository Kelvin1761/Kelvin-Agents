from __future__ import annotations

import json
import sys
from dataclasses import replace
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


def _write_manifest(state_root: Path, identity: RunIdentity, state: RunState,
                    *, exit_code: int | None = None) -> Path:
    from shared_wong_choi.control import RunManifest, manifest_path

    path = manifest_path(state_root / "runs", identity)
    manifest = RunManifest.create(path, identity)
    manifest.transition(RunState.RUNNING)
    if exit_code is not None:
        # `_next_request` 嘅 PARTIAL 分支要讀到 exit code 先肯前進 —— 唔記錄
        # 就係測緊另一件事。
        manifest.record_operation(
            operation=Operation.PREDICT,
            status="temporary_failure",
            detail={"exit_code": exit_code},
        )
    manifest.transition(state)
    return path


def test_a_failed_manifest_blocks_the_next_run_unless_forced(tmp_path: Path) -> None:
    """復原 job 存在嘅唯一目的就係重試一個失敗咗嘅 run。

    2026-09-09：09:00 網球咭 `failed`，10:30 同 12:30 兩個復原時段全部攞返同一個
    identity → `duplicate_skipped`，一步都冇行過，兩個 attempt 燒晒，當日冇咭。
    自動重試只認 `PARTIAL` 係刻意嘅（唔好無限重試一個真 bug），所以修法係俾
    明確嘅復原調用一個 `--force` 出口，唔係放寬自動政策。
    """
    identity = RunIdentity(Domain.TENNIS, "card", date(2026, 9, 9), "09:00")
    _write_manifest(tmp_path, identity, RunState.FAILED)
    request = RunRequest(identity, Operation.PREDICT)
    retry = RetryPolicy(max_attempts=3)

    # 預設：政策不變 —— 唔跳，之後就會撞返 duplicate_skipped。
    assert M._next_request(request, tmp_path, retry).identity.attempt == 1
    # 明確復原：開一個新 attempt，有自己嘅 manifest，真係行得到。
    assert M._next_request(request, tmp_path, retry, force=True).identity.attempt == 2


def test_force_walks_past_every_terminal_attempt_and_is_bounded(tmp_path: Path) -> None:
    identity = RunIdentity(Domain.TENNIS, "card", date(2026, 9, 9), "09:00")
    for attempt, state in ((1, RunState.FAILED), (2, RunState.SUCCEEDED),
                           (3, RunState.PARTIAL)):
        _write_manifest(tmp_path, replace(identity, attempt=attempt), state)
    request = RunRequest(identity, Operation.PREDICT)
    forced = M._next_request(request, tmp_path, RetryPolicy(max_attempts=3), force=True)
    assert forced.identity.attempt == 4
    assert M.FORCE_ATTEMPT_CEILING >= 2  # 有上限，唔會無限行落去


def test_force_does_not_disturb_the_partial_retry_path(tmp_path: Path) -> None:
    """暫時性失敗照舊自己前進 —— `--force` 唔可以改到呢條路。"""
    identity = RunIdentity(Domain.NBA, "pregame", date(2026, 10, 21), "00:30")
    _write_manifest(tmp_path, identity, RunState.PARTIAL, exit_code=75)
    request = RunRequest(identity, Operation.PREDICT)
    retry = RetryPolicy(max_attempts=3)
    assert M._next_request(request, tmp_path, retry).identity.attempt == 2
    assert M._next_request(request, tmp_path, retry, force=True).identity.attempt == 2
