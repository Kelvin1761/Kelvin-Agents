#!/usr/bin/env python3
"""
Racing Agent Runner
===================
External agent invocation for LangGraph autopilot mode.

This module only dispatches an external command. It does not analyse horses,
fill JSON, generate templates, or bypass validation.
"""
from __future__ import annotations

import os
import shlex
import subprocess
from typing import Any


TAIL_LIMIT = 1000


def _tail(value: str | None, limit: int = TAIL_LIMIT) -> str:
    return (value or "")[-limit:]


def get_agent_command() -> str | None:
    return os.environ.get("RACING_AGENT_CMD")


def build_agent_args(
    agent_cmd: str,
    domain: str,
    target_dir: str,
    race: int,
    horse: int,
    workcard_path: str,
    logic_json_path: str,
) -> list[str]:
    """Build argv for the external horse-analysis agent."""
    return [
        *shlex.split(agent_cmd),
        "--domain", domain,
        "--target-dir", target_dir,
        "--race", str(race),
        "--horse", str(horse),
        "--workcard", workcard_path,
        "--logic-json", logic_json_path,
    ]


def invoke_agent(
    domain: str,
    target_dir: str,
    race: int,
    horse: int,
    workcard_path: str,
    logic_json_path: str,
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    agent_cmd = get_agent_command()
    base = {
        "domain": domain,
        "target_dir": target_dir,
        "race": race,
        "horse": horse,
        "workcard_path": workcard_path,
        "logic_json_path": logic_json_path,
        "timeout_seconds": timeout_seconds,
    }

    if not agent_cmd:
        return {**base, "status": "missing_command"}

    try:
        args = build_agent_args(
            agent_cmd, domain, target_dir, race, horse,
            workcard_path, logic_json_path,
        )
    except ValueError as exc:
        return {**base, "status": "failed", "returncode": None, "stderr_tail": str(exc)}

    try:
        res = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            **base,
            "status": "timeout",
            "stdout_tail": _tail(exc.stdout if isinstance(exc.stdout, str) else ""),
            "stderr_tail": _tail(exc.stderr if isinstance(exc.stderr, str) else ""),
        }
    except Exception as exc:  # noqa: BLE001 - caller receives controlled failure
        return {**base, "status": "failed", "returncode": None, "stderr_tail": str(exc)}

    status = "pass" if res.returncode == 0 else "failed"
    return {
        **base,
        "status": status,
        "returncode": res.returncode,
        "stdout_tail": _tail(res.stdout),
        "stderr_tail": _tail(res.stderr),
    }


def format_agent_result(result: dict[str, Any]) -> str:
    status = result.get("status")
    if status == "pass":
        return f"pass returncode={result.get('returncode', 0)}"
    if status == "failed":
        detail = result.get("stderr_tail") or result.get("stdout_tail") or ""
        detail = detail.replace("\n", " ").strip()
        suffix = f" stderr={detail}" if detail else ""
        return f"failed returncode={result.get('returncode')}{suffix}"
    if status == "timeout":
        return f"timeout after {result.get('timeout_seconds', '?')}s"
    if status == "missing_command":
        return "missing RACING_AGENT_CMD"
    return str(status or "unknown")
