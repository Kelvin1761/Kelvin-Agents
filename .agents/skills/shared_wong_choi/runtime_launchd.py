"""Read-only proof that installed macOS automation runs approved checkouts."""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
from xml.parsers.expat import ExpatError
from pathlib import Path
from typing import Any, Mapping


RUNTIME_SCHEMA = "wong-choi-runtime-launchd/v1"
DOMAIN_LABELS: dict[str, dict[str, tuple[str, ...]]] = {
    "au": {
        "com.antigravity.au-wong-choi.bot": (
            ".agents/skills/au_racing/au_daily_auto/run_au_auxiliary.sh",
        ),
        "com.antigravity.au-wong-choi.evening": (
            ".agents/skills/au_racing/au_daily_auto/run_au_daily_schedule.sh",
        ),
        "com.antigravity.au-wong-choi.healthcheck": (
            ".agents/skills/au_racing/au_daily_auto/run_au_auxiliary.sh",
        ),
        "com.antigravity.au-wong-choi.morning": (
            ".agents/skills/au_racing/au_daily_auto/run_au_daily_schedule.sh",
        ),
    },
    "hkjc": {
        label: (
            ".agents/skills/hkjc_racing/hkjc_daily_auto/"
            "run_hkjc_daily_schedule.sh",
        )
        for label in (
            "com.antigravity.hkjc-wong-choi.postrace",
            "com.antigravity.hkjc-wong-choi.prerace",
            "com.antigravity.hkjc-wong-choi.recovery",
            "com.antigravity.hkjc-wong-choi.startup",
            "com.antigravity.hkjc-wong-choi.watch",
            "com.antigravity.hkjc-wong-choi.weekly",
        )
    },
    "nba": {
        label: (
            ".agents/skills/nba/nba_daily_auto/run_nba_daily_schedule.sh",
        )
        for label in (
            "com.antigravity.nba-wong-choi.final-refresh",
            "com.antigravity.nba-wong-choi.health",
            "com.antigravity.nba-wong-choi.postgame",
            "com.antigravity.nba-wong-choi.production",
            "com.antigravity.nba-wong-choi.startup",
            "com.antigravity.nba-wong-choi.warmup",
        )
    },
    "tennis": {
        "com.antigravity.tennis-wong-choi.card": (
            "tennis-wong-choi/scripts/run_tennis_daily_schedule.sh",
        ),
        "com.antigravity.tennis-wong-choi.daily": (
            "tennis-wong-choi/scripts/run_tennis_daily_schedule.sh",
        ),
        "com.antigravity.tennis-wong-choi.recovery": (
            "tennis-wong-choi/scripts/tennis_card_recovery.py",
        ),
    },
}
CENTRAL_LABELS = {
    "com.antigravity.central-wong-choi.durability": (
        ".agents/skills/central_wong_choi/scripts/"
        "run_central_daily_maintenance.sh",
    )
}


def _load_plist(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with path.open("rb") as handle:
            value = plistlib.load(handle)
    except ExpatError as exc:
        # launchd/plutil accept a few legacy plist comments that Python's
        # strict XML parser rejects (notably `--` inside comments).  The
        # installed job is the authority, so use Apple's read-only parser as
        # a fallback before calling the plist invalid.
        try:
            converted = subprocess.run(
                ["/usr/bin/plutil", "-convert", "json", "-o", "-", str(path)],
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
            value = json.loads(converted.stdout) if converted.returncode == 0 else None
        except (OSError, ValueError, subprocess.SubprocessError):
            value = None
        if not isinstance(value, dict):
            return None, f"{type(exc).__name__}: {exc}"
    except (OSError, plistlib.InvalidFileException) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(value, dict):
        return None, "plist root is not a dictionary"
    return value, None


def _loaded(label: str) -> bool:
    try:
        result = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{label}"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _label_status(
    launch_agents_root: Path,
    *,
    label: str,
    expected_root: Path,
    relative_paths: tuple[str, ...],
    probe_loaded: bool,
) -> dict[str, Any]:
    plist_path = launch_agents_root / f"{label}.plist"
    payload, error = _load_plist(plist_path)
    if payload is None:
        return {
            "label": label,
            "status": "missing" if not plist_path.exists() else "invalid",
            "plist": str(plist_path),
            "error": error,
        }
    arguments = [str(value) for value in payload.get("ProgramArguments") or []]
    working = str(payload.get("WorkingDirectory") or "")
    actual = set(arguments + ([working] if working else []))
    expected = [str(expected_root / relative) for relative in relative_paths]
    mismatches = [path for path in expected if path not in actual]
    is_loaded = _loaded(label) if probe_loaded else None
    status = (
        "misaligned"
        if mismatches
        else "unloaded"
        if probe_loaded and not is_loaded
        else "aligned"
    )
    return {
        "label": label,
        "status": status,
        "plist": str(plist_path),
        "loaded": is_loaded,
        "expected_paths": expected,
        "program_arguments": arguments,
        "working_directory": working or None,
        "mismatches": mismatches,
    }


def collect_runtime_alignment(
    production_roots: Mapping[str, Path],
    *,
    control_root: Path,
    launch_agents_root: Path | None = None,
    probe_loaded: bool = True,
) -> dict[str, Any]:
    """Compare installed launchd code paths with configured production roots."""
    agents = (
        launch_agents_root.expanduser().resolve()
        if launch_agents_root is not None
        else Path.home() / "Library" / "LaunchAgents"
    )
    domains: dict[str, Any] = {}
    attention: list[str] = []
    for domain, labels in DOMAIN_LABELS.items():
        configured = production_roots.get(domain)
        if configured is None:
            domains[domain] = {"status": "not_configured", "labels": []}
            attention.append(f"runtime_root_not_configured:{domain}")
            continue
        expected_root = Path(configured).expanduser().resolve()
        entries = [
            _label_status(
                agents,
                label=label,
                expected_root=expected_root,
                relative_paths=relative,
                probe_loaded=probe_loaded,
            )
            for label, relative in labels.items()
        ]
        status = (
            "aligned"
            if entries and all(item["status"] == "aligned" for item in entries)
            else "attention"
        )
        domains[domain] = {
            "status": status,
            "production_root": str(expected_root),
            "labels": entries,
        }
        if status != "aligned":
            attention.append(f"runtime_launchd_not_aligned:{domain}")

    control = Path(control_root).expanduser().resolve()
    central_entries = [
        _label_status(
            agents,
            label=label,
            expected_root=control,
            relative_paths=relative,
            probe_loaded=probe_loaded,
        )
        for label, relative in CENTRAL_LABELS.items()
    ]
    central_status = (
        "aligned"
        if central_entries
        and all(item["status"] == "aligned" for item in central_entries)
        else "attention"
    )
    if central_status != "aligned":
        attention.append("runtime_launchd_not_aligned:central")
    return {
        "schema_version": RUNTIME_SCHEMA,
        "status": "aligned" if not attention else "attention",
        "launch_agents_root": str(agents),
        "domains": domains,
        "central": {"status": central_status, "labels": central_entries},
        "attention": attention,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--production-root", type=Path)
    parser.add_argument("--launch-agents-root", type=Path)
    parser.add_argument("--no-probe", action="store_true")
    args = parser.parse_args(argv)
    root = (args.production_root or args.repo_root).expanduser().resolve()
    payload = collect_runtime_alignment(
        {name: root for name in DOMAIN_LABELS},
        control_root=args.repo_root,
        launch_agents_root=args.launch_agents_root,
        probe_loaded=not args.no_probe,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["status"] == "aligned" else 1


if __name__ == "__main__":
    raise SystemExit(main())
