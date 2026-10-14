"""Reference control-plane adapter for the existing NBA scheduler."""

from __future__ import annotations

import sys

from .contracts import (
    Domain,
    RunRequest,
)
from .command_adapter import ManifestCommandAdapter
from .registry import adapter_spec
from .schedule_policy import NBA_ROLE_SLOTS


class NBAAdapter(ManifestCommandAdapter):
    """Wrap NBA lifecycle execution without importing its scoring engine."""

    spec = adapter_spec(Domain.NBA)

    def command(self, request: RunRequest) -> list[str]:
        identity = request.identity
        scheduler = self.entrypoint(request)
        command = [sys.executable, str(scheduler), "--mode", identity.mode]
        if identity.mode != "startup":
            command.extend(("--date", identity.target_date.isoformat()))
        if identity.mode == "pregame":
            role_by_slot = {
                "21:00": "warmup",
                "00:30": "production",
                "06:30": "final_refresh",
            }
            role_by_slot.update({slot: role for role, slot in NBA_ROLE_SLOTS.items()})
            role = request.metadata.get("freshness_role") or role_by_slot.get(identity.scheduled_slot)
            if role:
                command.extend(("--freshness-role", role))
        command.extend(str(item) for item in request.metadata.get("scheduler_args", ()))
        return command
