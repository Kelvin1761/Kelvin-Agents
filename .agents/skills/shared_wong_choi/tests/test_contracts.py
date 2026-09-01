from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[2]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.contracts import (  # noqa: E402
    Domain,
    EventIdentity,
    Operation,
    RunIdentity,
    RunState,
    can_transition,
    normalize_run_state,
)
from shared_wong_choi.registry import ADAPTER_SPECS, adapter_spec  # noqa: E402


def test_all_four_domains_are_registered_with_every_control_capability() -> None:
    assert set(ADAPTER_SPECS) == set(Domain)
    required = set(Operation)
    for spec in ADAPTER_SPECS.values():
        assert spec.capabilities == required


def test_every_declared_entrypoint_exists_inside_repo() -> None:
    for spec in ADAPTER_SPECS.values():
        paths = [spec.orchestrator, *(binding.entrypoint for binding in spec.bindings)]
        for relative in paths:
            resolved = (REPO_ROOT / relative).resolve()
            assert resolved.is_relative_to(REPO_ROOT)
            assert resolved.is_file(), f"missing {spec.domain.value} entrypoint: {relative}"


def test_registry_lookup_accepts_enum_or_string() -> None:
    assert adapter_spec(Domain.NBA) is adapter_spec("nba")


def test_ids_are_stable_and_attempt_is_not_part_of_idempotency_key() -> None:
    first = RunIdentity(Domain.NBA, "pregame", date(2026, 10, 21), "00:30", attempt=1)
    retry = RunIdentity(Domain.NBA, "pregame", date(2026, 10, 21), "00:30", attempt=2)
    assert first.idempotency_key == retry.idempotency_key
    assert first.run_id != retry.run_id
    assert first.idempotency_key == "wc:nba:run:2026-10-21:pregame:00%3A30"


def test_event_id_preserves_domain_source_and_external_identity() -> None:
    event = EventIdentity(Domain.HKJC, date(2026, 9, 6), "HKJC", "ST/R1")
    assert event.canonical_id == "wc:hkjc:event:2026-09-06:hkjc:st%2Fr1"


def test_state_machine_is_fail_closed_after_terminal_state() -> None:
    assert can_transition(RunState.READY, RunState.RUNNING)
    assert can_transition(RunState.RUNNING, RunState.PARTIAL)
    assert can_transition(RunState.RUNNING, RunState.DORMANT)
    assert not can_transition(RunState.SUCCEEDED, RunState.RUNNING)
    assert not can_transition(RunState.FAILED, RunState.SUCCEEDED)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("ok", RunState.SUCCEEDED),
        ("temporary_failure", RunState.PARTIAL),
        ("dormant", RunState.DORMANT),
        ("skipped_locked", RunState.BLOCKED),
    ],
)
def test_current_domain_statuses_normalize_explicitly(source: str, expected: RunState) -> None:
    assert normalize_run_state(source) is expected


def test_unknown_domain_status_does_not_default_to_success() -> None:
    with pytest.raises(ValueError, match="unknown Wong Choi run status"):
        normalize_run_state("probably-fine")
