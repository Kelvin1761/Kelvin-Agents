from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.network_readiness import unresolved_hosts, wait_until_resolvable


def test_unresolved_hosts_reports_only_dns_failures() -> None:
    def resolver(host: str, *_args, **_kwargs):
        if host == "offline.example":
            raise socket.gaierror("not ready")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", 443))]

    assert unresolved_hosts(
        ["online.example", "offline.example"], resolver=resolver
    ) == ["offline.example"]


def test_wait_until_resolvable_retries_wake_dns_with_bounded_backoff() -> None:
    calls = 0
    sleeps: list[float] = []

    def resolver(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise socket.gaierror("network is still waking")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", 443))]

    assert wait_until_resolvable(
        ["example.test"],
        delays=(0, 15, 30, 60),
        resolver=resolver,
        sleeper=sleeps.append,
    ) == (True, [], 3)
    assert sleeps == [15, 30]


def test_wait_until_resolvable_stops_after_configured_attempts() -> None:
    def resolver(*_args, **_kwargs):
        raise socket.gaierror("still offline")

    assert wait_until_resolvable(
        ["example.test"],
        delays=(0, 1, 2),
        resolver=resolver,
        sleeper=lambda _delay: None,
    ) == (False, ["example.test"], 3)


def test_wait_until_resolvable_rejects_invalid_retry_plan() -> None:
    with pytest.raises(ValueError):
        wait_until_resolvable(["example.test"], delays=())
    with pytest.raises(ValueError):
        wait_until_resolvable(["example.test"], delays=(0, -1))
