#!/usr/bin/env python3
"""Bounded DNS readiness gate for launchd-started schedulers.

macOS can fire a calendar job before networking and DNS have recovered after
wake. Starting the real workflow in that window produces several unrelated
looking failures at once, so wait here before any remote dependency is used.
"""

from __future__ import annotations

import argparse
import socket
import time
from collections.abc import Callable, Iterable, Sequence


DEFAULT_DELAYS = (0, 15, 30, 60, 60, 60, 60, 60)


def unresolved_hosts(
    hosts: Iterable[str],
    *,
    resolver: Callable[..., object] = socket.getaddrinfo,
) -> list[str]:
    """Return hosts that DNS cannot resolve right now."""
    unresolved: list[str] = []
    for host in hosts:
        try:
            resolver(host, 443, type=socket.SOCK_STREAM)
        except OSError:
            unresolved.append(host)
    return unresolved


def wait_until_resolvable(
    hosts: Sequence[str],
    *,
    delays: Sequence[int] = DEFAULT_DELAYS,
    resolver: Callable[..., object] = socket.getaddrinfo,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[bool, list[str], int]:
    """Wait for every host to resolve, returning status, failures and attempts."""
    if not hosts:
        raise ValueError("at least one host is required")
    if not delays or any(delay < 0 for delay in delays):
        raise ValueError("delays must contain non-negative values")

    missing = list(hosts)
    for attempt, delay in enumerate(delays, start=1):
        if delay:
            sleeper(delay)
        missing = unresolved_hosts(hosts, resolver=resolver)
        if not missing:
            return True, [], attempt
    return False, missing, len(delays)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", action="append", required=True)
    parser.add_argument(
        "--delays",
        default=",".join(str(delay) for delay in DEFAULT_DELAYS),
        help="comma-separated seconds before each DNS attempt",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        delays = tuple(int(value) for value in args.delays.split(","))
        ok, missing, attempts = wait_until_resolvable(args.host, delays=delays)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if ok:
        print(f"network ready after {attempts} DNS attempt(s)")
        return 0
    print(f"network still unavailable after {attempts} DNS attempt(s): {', '.join(missing)}")
    return 75


if __name__ == "__main__":
    raise SystemExit(main())
