#!/usr/bin/env python3
"""Opt-in external scratch/cache routing; never moves live data or deletes files.

This is a startup storage guard, not the research supervisor. Children must
still enforce their production locks and detect a volume disappearing mid-run.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

GIB = 1024 ** 3
MIN_FREE_BYTES = 10 * GIB
DEFAULT_ROOT = Path("/Volumes/Kelvin Hardisk 1/WongChoi-Archive")


def _volume_for(root: Path) -> Path:
    if len(root.parts) < 4 or root.parts[1] != "Volumes":
        raise ValueError("external root must be beneath a mounted /Volumes disk")
    return Path(*root.parts[:3])


def _reject_symlinks(path: Path) -> None:
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("symlinked storage paths are not accepted")


def inspect_root(root: Path) -> dict:
    root = root.expanduser().absolute()
    _reject_symlinks(root)
    volume = _volume_for(root)
    if not volume.is_mount():
        raise ValueError("external volume is not mounted; local fallback disabled")
    root = root.resolve()
    if not root.is_relative_to(volume.resolve()):
        raise ValueError("archive root escapes external volume")
    if not root.is_dir():
        raise ValueError("external archive root is missing")
    next(root.iterdir(), None)  # Actual read probe, not just stat/TCC metadata.
    free = shutil.disk_usage(root).free
    if free < MIN_FREE_BYTES:
        raise ValueError("external capacity below 10 GiB reserve")
    return {"root": str(root), "volume": str(volume), "free_bytes": free,
            "minimum_free_bytes": MIN_FREE_BYTES, "local_fallback": False}


def prepare_environment(root: Path, original: dict) -> tuple[dict, Path]:
    report = inspect_root(root)
    root = Path(report["root"])
    directories = {
        "TMPDIR": root / "scratch" / "command-runs",
        "PIP_CACHE_DIR": root / "download-caches" / "pip",
        "UV_CACHE_DIR": root / "download-caches" / "uv",
        "npm_config_cache": root / "download-caches" / "npm",
    }
    # Validate every destination before making any directory.
    for path in directories.values():
        _reject_symlinks(path)
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("cache path escapes external root")
    for path in directories.values():
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="wc-run-", dir=directories["TMPDIR"]))
    env = dict(original)
    env.update({key: str(value) for key, value in directories.items()})
    env["TMPDIR"] = str(scratch)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    inspect_root(root)  # Recheck after real writes, immediately before the child.
    return env, scratch


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("Usage: python3 .agents/scripts/wongchoi_external_run.py --check | -- COMMAND [ARGS...]", file=sys.stderr)
        return 64
    root = Path(os.environ.get("WC_WARM_ARCHIVE_ROOT") or DEFAULT_ROOT)
    try:
        if args == ["--check"]:
            print(json.dumps(inspect_root(root), sort_keys=True))
            return 0
        if args[0] == "--":
            args.pop(0)
        if not args:
            return 64
        env, scratch = prepare_environment(root, os.environ)
    except (OSError, ValueError) as exc:
        print(f"External storage unavailable: {exc}", file=sys.stderr)
        return 75
    print(f"External scratch (retained): {scratch}", file=sys.stderr)
    try:
        result = subprocess.run(args, env=env, shell=False)
    except FileNotFoundError:
        print("Requested command was not found", file=sys.stderr)
        return 127
    except OSError as exc:
        print(f"Command could not start: {type(exc).__name__}", file=sys.stderr)
        return 126
    except KeyboardInterrupt:
        return 130
    return result.returncode if result.returncode >= 0 else 128 - result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
