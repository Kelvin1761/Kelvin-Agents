#!/usr/bin/env python3
"""Request local copies of AU archive files from the macOS file provider.

The script is read-only from the repository's perspective: opening a cloud
placeholder asks Google Drive to materialize its existing contents locally.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "Wong Choi Horse Race Analysis/AU_Racing"


def touch_contents(path: Path) -> tuple[str, str]:
    try:
        with path.open("rb") as handle:
            handle.read(1)
        return str(path), "ok"
    except Exception as exc:  # pragma: no cover - provider errors are external
        return str(path), f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pattern", default="Race_*_Auto_Scoring.csv")
    parser.add_argument("--workers", type=int, default=24)
    args = parser.parse_args()

    paths = sorted(ARCHIVE.glob(f"*/{args.pattern}"))
    print(f"files={len(paths)} workers={args.workers}", flush=True)
    failures: list[tuple[str, str]] = []
    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [executor.submit(touch_contents, path) for path in paths]
        for future in as_completed(futures):
            path, status = future.result()
            completed += 1
            if status != "ok":
                failures.append((path, status))
            if completed % 25 == 0 or completed == len(paths):
                print(
                    f"completed={completed}/{len(paths)} failures={len(failures)}",
                    flush=True,
                )

    for path, error in failures[:25]:
        print(f"FAILED {path}: {error}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
