"""Control-plane adapter for the existing HKJC scheduler."""

from __future__ import annotations

import sys

from .command_adapter import ManifestCommandAdapter
from .contracts import Domain, RunRequest
from .registry import adapter_spec


class HKJCAdapter(ManifestCommandAdapter):
    spec = adapter_spec(Domain.HKJC)

    def command(self, request: RunRequest) -> list[str]:
        identity = request.identity
        entrypoint = self.entrypoint(request)
        command = [
            sys.executable,
            str(entrypoint),
            "--mode",
            identity.mode,
            "--control-json",
        ]
        meeting_url = request.metadata.get("meeting_url")
        if meeting_url:
            command.extend(("--meeting-url", str(meeting_url)))
        if request.metadata.get("force"):
            command.append("--force")
        command.extend(str(item) for item in request.metadata.get("scheduler_args", ()))
        return command
