"""Control-plane adapter for the existing AU scheduler and healthcheck."""

from __future__ import annotations

import sys

from .command_adapter import ManifestCommandAdapter
from .contracts import Domain, RunRequest
from .registry import adapter_spec


class AUAdapter(ManifestCommandAdapter):
    spec = adapter_spec(Domain.AU)

    def command(self, request: RunRequest) -> list[str]:
        identity = request.identity
        entrypoint = self.entrypoint(request)
        if identity.mode == "healthcheck":
            command = [sys.executable, str(entrypoint), identity.target_date.isoformat()]
            command.extend(str(item) for item in request.metadata.get("scheduler_args", ()))
            return command
        command = [
            sys.executable,
            str(entrypoint),
            "--mode",
            identity.mode,
            "--today",
            identity.target_date.isoformat(),
            "--json",
        ]
        command.extend(str(item) for item in request.metadata.get("scheduler_args", ()))
        return command
