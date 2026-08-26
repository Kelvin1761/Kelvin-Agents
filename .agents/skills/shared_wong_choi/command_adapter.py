"""Reusable manifest-backed subprocess boundary for domain schedulers."""

from __future__ import annotations

import hashlib
import json
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from .contracts import (
    AdapterSpec,
    OperationResult,
    RunRequest,
    RunState,
    normalize_run_state,
)
from .control import RunManifest, manifest_path, single_run_lock


Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def last_json_object(output: str) -> dict | None:
    """Return the last complete JSON object from mixed log/JSON stdout.

    NBA emits one-line JSON while AU emits an indented object after text logs.
    Searching candidate ``{`` positions from the end supports both without
    accepting a truncated object.
    """
    decoder = json.JSONDecoder()
    starts = [index for index, char in enumerate(output) if char == "{"]
    for index in reversed(starts):
        candidate = output[index:].lstrip()
        try:
            value, end = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and not candidate[end:].strip():
            return value
    return None


class ManifestCommandAdapter(ABC):
    """Execute one existing scheduler behind the canonical run contract."""

    spec: AdapterSpec

    def __init__(
        self,
        repo_root: Path,
        state_root: Path,
        *,
        runner: Runner | None = None,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.state_root = state_root.resolve()
        self._runner = runner or self._run_subprocess

    def _run_subprocess(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=self.repo_root,
            text=True,
            capture_output=True,
            timeout=7200,
            check=False,
        )

    def entrypoint(self, request: RunRequest) -> Path:
        identity = request.identity
        if identity.domain is not self.spec.domain:
            raise ValueError(
                f"{type(self).__name__} only accepts {self.spec.domain.value} run identities"
            )
        binding = self.spec.binding(request.operation)
        if identity.mode not in binding.modes:
            raise ValueError(
                f"{self.spec.domain.value.upper()} {request.operation.value} "
                f"does not support mode {identity.mode!r}"
            )
        resolved = (self.repo_root / binding.entrypoint).resolve()
        if not resolved.is_relative_to(self.repo_root) or not resolved.is_file():
            raise FileNotFoundError(
                f"{self.spec.domain.value.upper()} scheduler entrypoint missing: {resolved}"
            )
        return resolved

    @abstractmethod
    def command(self, request: RunRequest) -> list[str]:
        """Build the existing domain scheduler command for this request."""

    def source_payload(self, completed: subprocess.CompletedProcess[str]) -> dict:
        return last_json_object(completed.stdout) or {}

    def source_status(self, payload: dict) -> str:
        return str(payload.get("status") or payload.get("state") or "missing_status")

    def _lock_path(self, request: RunRequest) -> Path:
        digest = hashlib.sha256(
            request.identity.idempotency_key.encode("utf-8")
        ).hexdigest()
        return self.state_root / "locks" / f"{digest}.lock"

    def execute(self, request: RunRequest) -> OperationResult:
        command = self.command(request)
        if request.dry_run:
            return OperationResult(
                state=RunState.READY,
                status="dry_run",
                detail={"command": command},
            )

        path = manifest_path(self.state_root / "runs", request.identity)
        if path.exists():
            existing = RunManifest.load(path)
            active = existing.state is RunState.RUNNING
            return OperationResult(
                state=RunState.BLOCKED if active else existing.state,
                status="duplicate_active" if active else "duplicate_skipped",
                artifacts=(str(path),),
                detail={"run_id": existing.payload["run_id"]},
            )

        with single_run_lock(self._lock_path(request)) as acquired:
            if not acquired:
                return OperationResult(state=RunState.BLOCKED, status="locked")
            if path.exists():
                existing = RunManifest.load(path)
                return OperationResult(
                    state=existing.state,
                    status="duplicate_skipped",
                    artifacts=(str(path),),
                    detail={"run_id": existing.payload["run_id"]},
                )

            manifest = RunManifest.create(path, request.identity)
            manifest.transition(RunState.RUNNING)
            try:
                completed = self._runner(command)
            except Exception as exc:  # durable failure record before returning control
                status = f"adapter_exception:{type(exc).__name__}"
                manifest.record_operation(
                    request.operation,
                    status,
                    detail={"error": str(exc)},
                )
                manifest.transition(RunState.FAILED, error=f"{type(exc).__name__}: {exc}")
                return OperationResult(
                    state=RunState.FAILED,
                    status=status,
                    artifacts=(str(path),),
                    detail={"error": str(exc)},
                )

            payload = self.source_payload(completed)
            source_status = self.source_status(payload)
            error: str | None = None
            if completed.returncode in (75, 124):
                target = RunState.PARTIAL
            elif completed.returncode != 0:
                target = RunState.FAILED
            else:
                try:
                    target = normalize_run_state(source_status)
                except ValueError as exc:
                    target = RunState.FAILED
                    error = str(exc)

            detail = {
                "exit_code": completed.returncode,
                "source_payload": payload,
                "stderr_tail": completed.stderr[-2000:],
            }
            manifest.record_operation(request.operation, source_status, detail=detail)
            manifest.transition(
                target,
                warning=source_status if target is RunState.PARTIAL else None,
                error=error
                or (completed.stderr[-2000:] if target is RunState.FAILED else None),
            )
            return OperationResult(
                state=target,
                status=source_status,
                artifacts=(str(path),),
                detail=detail,
            )

