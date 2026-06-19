#!/usr/bin/env python3
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import subprocess
import sys
from typing import Any


def bounded_workers(value: int | None, *, default: int = 3, maximum: int = 4) -> int:
    if value is None:
        value = default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def run_labeled_commands(
    tasks: list[dict[str, Any]],
    *,
    cwd: Path,
    max_workers: int = 1,
    timeout: int | None = None,
) -> list[dict[str, Any]]:
    if not tasks:
        return []

    workers = bounded_workers(max_workers)
    if workers == 1 or len(tasks) == 1:
        results = []
        for task in tasks:
            result = _run_task(task, cwd=cwd, timeout=timeout, stream=True)
            results.append(result)
            if result["returncode"] != 0:
                raise SystemExit(result["returncode"] or 1)
        return results

    print(f"⚙️ Running {len(tasks)} task(s) with {workers} worker(s)")
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_run_task, task, cwd=cwd, timeout=timeout, stream=False) for task in tasks]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            _print_result(result)

    failures = [result for result in results if result["returncode"] != 0]
    if failures:
        first = failures[0]
        print(f"❌ Parallel task failed: {first['label']}", file=sys.stderr)
        raise SystemExit(first["returncode"] or 1)

    return results


def _run_task(
    task: dict[str, Any],
    *,
    cwd: Path,
    timeout: int | None,
    stream: bool,
) -> dict[str, Any]:
    label = str(task["label"])
    cmd = list(task["cmd"])
    meta = dict(task.get("meta") or {})

    if stream:
        print(f"\n{'=' * 72}")
        print(label)
        print(" ".join(str(part) for part in cmd))
        print(f"{'=' * 72}")
        result = subprocess.run(cmd, cwd=cwd, text=True, timeout=timeout)
        payload = {
            "label": label,
            "cmd": cmd,
            "returncode": result.returncode,
            "stdout": "",
            "stderr": "",
            **meta,
        }
    else:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        payload = {
            "label": label,
            "cmd": cmd,
            "returncode": result.returncode,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            **meta,
        }

    return payload


def _print_result(result: dict[str, Any]) -> None:
    print(f"\n{'=' * 72}")
    print(result["label"])
    print(" ".join(str(part) for part in result["cmd"]))
    print(f"{'=' * 72}")
    if result.get("stdout"):
        print(result["stdout"], end="" if result["stdout"].endswith("\n") else "\n")
    if result.get("stderr"):
        print(result["stderr"], file=sys.stderr, end="" if result["stderr"].endswith("\n") else "\n")
