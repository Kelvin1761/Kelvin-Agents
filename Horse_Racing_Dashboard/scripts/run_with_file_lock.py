#!/usr/bin/env python3
"""Run one command while holding a machine-wide advisory file lock."""

from __future__ import annotations

import argparse
import fcntl
import os
import subprocess
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        print("file-lock: missing command", file=sys.stderr)
        return 2

    args.lock.parent.mkdir(parents=True, exist_ok=True)
    with args.lock.open("a+", encoding="utf-8") as handle:
        print(f"🔒 等候 Dashboard 全域發佈鎖：{args.lock}", flush=True)
        fcntl.flock(handle, fcntl.LOCK_EX)
        print("🔓 已取得 Dashboard 全域發佈鎖", flush=True)
        env = os.environ.copy()
        env["WC_DASHBOARD_DEPLOY_LOCK_HELD"] = "1"
        try:
            completed = subprocess.run(command, env=env, check=False)
        except OSError as exc:
            print(f"file-lock: cannot run {command[0]}: {exc}", file=sys.stderr)
            return 127
        return completed.returncode if completed.returncode >= 0 else 128 - completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
