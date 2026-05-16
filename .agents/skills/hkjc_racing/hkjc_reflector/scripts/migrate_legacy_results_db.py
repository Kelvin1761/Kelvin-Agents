#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from hkjc_results_db import get_results_database_root


def sync_tree(src: Path, dst: Path, dry_run: bool = False) -> list[tuple[Path, Path]]:
    copied: list[tuple[Path, Path]] = []
    if not src.exists():
        return copied
    for path in sorted(src.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(src)
        target = dst / rel
        if target.exists():
            continue
        copied.append((path, target))
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill legacy HKJC results database into canonical Archive_Race_Analysis/HKJC_Race_Results_Database")
    parser.add_argument("legacy_root", help="Legacy results root to import from")
    parser.add_argument("--dry-run", action="store_true", help="Show files that would be copied without changing anything")
    args = parser.parse_args()

    legacy = Path(args.legacy_root).resolve()
    canonical = get_results_database_root()

    copied = sync_tree(legacy, canonical, dry_run=args.dry_run)
    print(f"Legacy source: {legacy}")
    print(f"Canonical target: {canonical}")
    print(f"Files {'to copy' if args.dry_run else 'copied'}: {len(copied)}")
    for src, dst in copied[:50]:
        print(f"- {src} -> {dst}")
    if len(copied) > 50:
        print(f"... and {len(copied) - 50} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
