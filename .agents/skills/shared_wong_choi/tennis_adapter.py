"""Control-plane adapter for Tennis daily and guarded recovery schedulers."""

from __future__ import annotations

import sys

from .command_adapter import ManifestCommandAdapter
from .contracts import Domain, RunRequest
from .registry import adapter_spec


class TennisAdapter(ManifestCommandAdapter):
    spec = adapter_spec(Domain.TENNIS)

    def command(self, request: RunRequest) -> list[str]:
        identity = request.identity
        entrypoint = self.entrypoint(request)
        command = [sys.executable, str(entrypoint)]
        if identity.mode == "recovery":
            command.extend(
                ("--today", identity.target_date.isoformat(), "--control-json")
            )
            command.extend(str(item) for item in request.metadata.get("scheduler_args", ()))
            return command
        command.extend(
            (
                "--today",
                identity.target_date.isoformat(),
                "--source",
                "control-plane",
                "--control-json",
            )
        )
        if identity.mode == "card":
            command.append("--refresh-today")
        command.extend(str(item) for item in request.metadata.get("scheduler_args", ()))
        return command
