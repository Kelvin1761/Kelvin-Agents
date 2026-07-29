#!/usr/bin/env python3
"""Compatibility wrapper for building every race Logic in one process per race."""

import argparse
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
SKELETON = (
    ROOT
    / ".agents"
    / "skills"
    / "hkjc_racing"
    / "hkjc_wong_choi"
    / "scripts"
    / "create_hkjc_logic_skeleton.py"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("meeting_dir", type=Path)
    args = parser.parse_args()
    facts_files = []
    for path in args.meeting_dir.glob("* Race * Facts.md"):
        match = re.search(r"Race\s+(\d+)", path.name)
        if match:
            facts_files.append((int(match.group(1)), path))
    for race_num, facts_path in sorted(facts_files):
        output = args.meeting_dir / f"Race_{race_num}_Logic.json"
        subprocess.run(
            [
                sys.executable,
                str(SKELETON),
                str(facts_path),
                str(race_num),
                "--all-horses",
                "--output",
                str(output),
            ],
            check=True,
            cwd=ROOT,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
