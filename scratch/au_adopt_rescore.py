#!/usr/bin/env python3
"""Adopt the sandbox facts-refresh rescore into the Drive AU archive.

For every sandbox meeting: move the Drive originals (Logic, meeting scoring
CSV, per-race auto outputs) into a sibling backup tree via os.rename (Drive-
internal metadata move — fast, fully reversible), then copy the rescored
sandbox files in. Facts/Formguide/Racecard files are never touched.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, "/Users/imac/Antigravity-repo")
from wongchoi_paths import AU_RACING

SP = Path("/private/tmp/claude-501/-Users-imac-Antigravity-repo/b09ea7dc-ca6d-496d-af27-41b7787ee6ae/scratchpad")
SANDBOX = SP / "data" / "Wong Choi Horse Race Analysis" / "AU_Racing"
BACKUP = AU_RACING.parent / "AU_Racing_prescore_backup_2026-07-17"

ADOPT_PATTERNS = ("Race_*_Logic.json", "Meeting_Auto_Scoring.csv",
                  "Race_*_Auto_Scoring.csv", "Race_*_Auto_Analysis.md")


def main() -> int:
    meetings = sorted(p for p in SANDBOX.iterdir()
                      if p.is_dir() and (p / "Meeting_Auto_Scoring.csv").exists())
    print(f"adopting {len(meetings)} rescored meetings; backup at {BACKUP}", flush=True)
    moved = copied = 0
    start = time.time()
    for idx, sandbox_dir in enumerate(meetings, 1):
        drive_dir = AU_RACING / sandbox_dir.name
        if not drive_dir.is_dir():
            print(f"[{idx}] SKIP no drive dir: {sandbox_dir.name}", flush=True)
            continue
        backup_dir = BACKUP / sandbox_dir.name
        backup_dir.mkdir(parents=True, exist_ok=True)
        # move originals to backup (only files we are about to replace)
        for pattern in ADOPT_PATTERNS:
            for src_file in sandbox_dir.glob(pattern):
                orig = drive_dir / src_file.name
                if orig.is_file():
                    target = backup_dir / src_file.name
                    if not target.exists():
                        orig.rename(target)
                        moved += 1
        # copy rescored files in
        for pattern in ADOPT_PATTERNS:
            for src_file in sandbox_dir.glob(pattern):
                shutil.copy(src_file, drive_dir / src_file.name)
                copied += 1
        if idx % 10 == 0 or idx == len(meetings):
            print(f"[{idx}/{len(meetings)}] {sandbox_dir.name} (moved {moved}, copied {copied})", flush=True)
    print(f"ADOPTION DONE moved={moved} copied={copied} in {(time.time()-start)/60:.1f} min", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
