"""Capability registry for the four production Wong Choi domains."""

from __future__ import annotations

from .contracts import (
    AdapterSpec,
    CapabilityReadiness,
    Domain,
    Operation,
    OperationBinding,
)


def _binding(
    operation: Operation,
    entrypoint: str,
    *modes: str,
    readiness: CapabilityReadiness = CapabilityReadiness.IMPLEMENTED,
    note: str = "",
) -> OperationBinding:
    return OperationBinding(operation, entrypoint, tuple(modes), readiness, note)


AU_SCHEDULER = ".agents/skills/au_racing/au_daily_auto/au_daily_schedule.py"
AU_HEALTH = ".agents/skills/au_racing/au_daily_auto/au_healthcheck.py"
HKJC_SCHEDULER = ".agents/skills/hkjc_racing/hkjc_daily_auto/hkjc_daily_schedule.py"
TENNIS_SCHEDULER = "tennis-wong-choi/scripts/tennis_daily_schedule.py"
TENNIS_RECOVERY = "tennis-wong-choi/scripts/tennis_card_recovery.py"
NBA_SCHEDULER = ".agents/skills/nba/nba_daily_auto/nba_daily_schedule.py"


ADAPTER_SPECS: dict[Domain, AdapterSpec] = {
    Domain.AU: AdapterSpec(
        domain=Domain.AU,
        display_name="AU Wong Choi",
        owner="au_daily_auto",
        orchestrator=".agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py",
        bindings=(
            _binding(Operation.DISCOVER, AU_SCHEDULER, "evening", "morning"),
            _binding(Operation.PREDICT, AU_SCHEDULER, "evening", "morning"),
            _binding(Operation.VALIDATE, AU_SCHEDULER, "evening", "morning"),
            _binding(Operation.PUBLISH, AU_SCHEDULER, "evening", "morning"),
            _binding(Operation.SETTLE, AU_SCHEDULER, "evening"),
            _binding(Operation.HEALTH, AU_HEALTH, "healthcheck"),
            _binding(Operation.NOTIFY, AU_SCHEDULER, "evening", "morning"),
            _binding(Operation.CALENDAR_STATE, AU_SCHEDULER, "evening"),
            _binding(Operation.RECOVER, AU_HEALTH, "healthcheck"),
        ),
    ),
    Domain.HKJC: AdapterSpec(
        domain=Domain.HKJC,
        display_name="HKJC Wong Choi",
        owner="hkjc_daily_auto",
        orchestrator=".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py",
        bindings=(
            _binding(Operation.DISCOVER, HKJC_SCHEDULER, "watch", "prerace"),
            _binding(Operation.PREDICT, HKJC_SCHEDULER, "prerace"),
            _binding(Operation.VALIDATE, HKJC_SCHEDULER, "prerace"),
            _binding(Operation.PUBLISH, HKJC_SCHEDULER, "prerace", "postrace"),
            _binding(Operation.SETTLE, HKJC_SCHEDULER, "postrace"),
            _binding(
                Operation.HEALTH,
                HKJC_SCHEDULER,
                "prerace",
                "recovery",
                readiness=CapabilityReadiness.PARTIAL,
                note="Health gates exist, but there is no canonical standalone run manifest yet.",
            ),
            _binding(Operation.NOTIFY, HKJC_SCHEDULER, "watch", "prerace", "postrace"),
            _binding(Operation.CALENDAR_STATE, HKJC_SCHEDULER, "watch"),
            _binding(Operation.RECOVER, HKJC_SCHEDULER, "recovery", "startup"),
        ),
    ),
    Domain.TENNIS: AdapterSpec(
        domain=Domain.TENNIS,
        display_name="Tennis Wong Choi",
        owner="tennis_daily_schedule",
        orchestrator="tennis-wong-choi/src/tennis_wc/cli.py",
        bindings=(
            _binding(Operation.DISCOVER, TENNIS_SCHEDULER, "daily", "card"),
            _binding(Operation.PREDICT, TENNIS_SCHEDULER, "daily", "card"),
            _binding(Operation.VALIDATE, TENNIS_SCHEDULER, "daily", "card"),
            _binding(Operation.PUBLISH, TENNIS_SCHEDULER, "daily", "card"),
            _binding(Operation.SETTLE, TENNIS_SCHEDULER, "daily"),
            _binding(
                Operation.HEALTH,
                TENNIS_SCHEDULER,
                "daily",
                "card",
                readiness=CapabilityReadiness.PARTIAL,
                note="Structured HEALTH_JSON exists in a text log, not a canonical run manifest.",
            ),
            _binding(Operation.NOTIFY, TENNIS_SCHEDULER, "daily", "card"),
            _binding(Operation.CALENDAR_STATE, TENNIS_SCHEDULER, "daily", "card"),
            _binding(Operation.RECOVER, TENNIS_RECOVERY, "recovery"),
        ),
    ),
    Domain.NBA: AdapterSpec(
        domain=Domain.NBA,
        display_name="NBA Wong Choi",
        owner="nba_daily_auto",
        orchestrator=".agents/skills/nba/nba_orchestrator.py",
        bindings=(
            _binding(Operation.DISCOVER, NBA_SCHEDULER, "pregame", "health"),
            _binding(
                Operation.PREDICT,
                NBA_SCHEDULER,
                "pregame",
                readiness=CapabilityReadiness.DEFERRED_LIVE_GATE,
                note="Engineering complete; 2026-27 live coverage acceptance remains open.",
            ),
            _binding(Operation.VALIDATE, NBA_SCHEDULER, "pregame", "health"),
            _binding(Operation.PUBLISH, NBA_SCHEDULER, "pregame", "postgame"),
            _binding(
                Operation.SETTLE,
                NBA_SCHEDULER,
                "postgame",
                readiness=CapabilityReadiness.DEFERRED_LIVE_GATE,
                note="First completed-day reflector smoke remains open.",
            ),
            _binding(Operation.HEALTH, NBA_SCHEDULER, "health"),
            _binding(Operation.NOTIFY, NBA_SCHEDULER, "pregame", "postgame", "health"),
            _binding(Operation.CALENDAR_STATE, NBA_SCHEDULER, "pregame", "health"),
            _binding(
                Operation.RECOVER,
                NBA_SCHEDULER,
                "startup",
                readiness=CapabilityReadiness.PARTIAL,
                note="Single-day startup catch-up exists; multi-day backlog policy is not authorised.",
            ),
        ),
    ),
}


def adapter_spec(domain: Domain | str) -> AdapterSpec:
    return ADAPTER_SPECS[Domain(domain)]
