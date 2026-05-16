#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from hkjc_results_db import (
    ROOT,
    ensure_results_database_dirs,
    get_analysis_archive_root,
    get_results_database_root,
)


def infer_season_bucket(date_text: str) -> str:
    year = int(date_text[:4])
    month = int(date_text[5:7])
    if month >= 9:
        return f"hkjc results {year} {str(year + 1)[-2:]}"
    return f"hkjc results {year - 1} {str(year)[-2:]}"


def sync_meeting_results(meeting_dir: Path, dry_run: bool = False) -> list[tuple[Path, Path]]:
    copied: list[tuple[Path, Path]] = []
    if not meeting_dir.exists():
        return copied
    date_text = meeting_dir.name[:10]
    if len(date_text) != 10:
        return copied

    db_dirs = ensure_results_database_dirs()
    season_dir = db_dirs["root"] / infer_season_bucket(date_text) / date_text
    season_dir.mkdir(parents=True, exist_ok=True)

    for source in sorted(meeting_dir.glob("*全日賽果.*")):
        normalized_name = source.name.replace("沙田", "ShaTin").replace("跑馬地", "HappyValley")
        dest = season_dir / normalized_name
        copied.append((source, dest))
        if not dry_run:
            shutil.copy2(source, dest)

        if source.suffix.lower() == ".json":
            normalized_dest = season_dir / "full_day_results.json"
        elif source.suffix.lower() == ".md":
            normalized_dest = season_dir / "full_day_results.md"
        else:
            normalized_dest = None
        if normalized_dest is not None:
            copied.append((source, normalized_dest))
            if not dry_run:
                shutil.copy2(source, normalized_dest)
    return copied


def sync_all_hkjc_meetings(dry_run: bool = False) -> list[tuple[Path, Path]]:
    archive_root = get_analysis_archive_root()
    copied: list[tuple[Path, Path]] = []
    if not archive_root.exists():
        return copied
    for meeting_dir in sorted(archive_root.iterdir()):
        if not meeting_dir.is_dir():
            continue
        name = meeting_dir.name
        if "ShaTin" not in name and "HappyValley" not in name and "Sha_Tin" not in name:
            continue
        copied.extend(sync_meeting_results(meeting_dir, dry_run=dry_run))
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync HKJC meeting result files into canonical HKJC race results database")
    parser.add_argument("--meeting-dir", help="Specific HKJC meeting directory to sync")
    parser.add_argument("--dry-run", action="store_true", help="Show planned copies without writing")
    args = parser.parse_args()

    get_results_database_root()
    if args.meeting_dir:
        copies = sync_meeting_results(Path(args.meeting_dir), dry_run=args.dry_run)
    else:
        copies = sync_all_hkjc_meetings(dry_run=args.dry_run)

    print(f"HKJC results database root: {ensure_results_database_dirs()['root']}")
    print(f"Copied files: {len(copies)}")
    for src, dst in copies[:20]:
        print(f"- {src} -> {dst}")
    if len(copies) > 20:
        print(f"... and {len(copies) - 20} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
