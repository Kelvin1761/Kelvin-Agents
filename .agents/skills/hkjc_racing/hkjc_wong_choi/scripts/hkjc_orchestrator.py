#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[4]
EXTRACTOR_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_race_extractor" / "scripts"
AUTO_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi_auto" / "scripts"
SHARED_SCRIPTS = ROOT / ".agents" / "scripts"

sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SHARED_SCRIPTS))

from hkjc_orchestrator_legacy import (  # type: ignore
    get_target_dir,
    parse_url_for_details,
    trigger_extractor,
)


PYTHON = sys.executable


def _run(cmd: list[str], label: str) -> None:
    print(f"\n{'=' * 72}")
    print(f"🏇 {label}")
    print(" ".join(cmd))
    print(f"{'=' * 72}")
    result = subprocess.run(cmd, cwd=ROOT, text=True)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _resolve_target(input_value: str) -> tuple[Path, str | None]:
    if input_value.startswith("http"):
        venue, formatted_date, resolved_url = parse_url_for_details(input_value)
        target_dir = get_target_dir(venue, formatted_date, auto_create=True)
        if not target_dir:
            raise SystemExit("❌ 無法建立 HKJC meeting folder")
        return Path(target_dir), resolved_url

    target_dir = Path(input_value).resolve()
    if not target_dir.is_dir():
        raise SystemExit(f"❌ Not a valid directory: {target_dir}")
    return target_dir, None


def _maybe_extract(url: str | None, target_dir: Path, skip_extract: bool) -> None:
    if skip_extract or not url:
        return
    trigger_extractor(url, str(target_dir))


def _generate_facts(target_dir: Path, skip_facts: bool) -> None:
    if skip_facts:
        return
    cmd = [
        PYTHON,
        str(SHARED_SCRIPTS / "run_prerace_pipeline.py"),
        str(target_dir),
        "--skip-std-times",
        "--skip-draw",
    ]
    _run(cmd, "Generate Facts.md")


def _iter_facts_files(target_dir: Path) -> list[tuple[int, Path]]:
    facts_files = []
    for facts_path in sorted(target_dir.glob("* Race * Facts.md")):
        match = re.search(r"Race\s+(\d+)", facts_path.name)
        if not match:
            continue
        facts_files.append((int(match.group(1)), facts_path))
    return facts_files


def _generate_logic(target_dir: Path, skip_logic: bool) -> None:
    if skip_logic:
        return
    facts_files = _iter_facts_files(target_dir)
    if not facts_files:
        raise SystemExit(f"❌ No Facts.md files found in {target_dir}")

    for race_num, facts_path in facts_files:
        text = facts_path.read_text(encoding="utf-8")
        horse_nums = [int(x) for x in re.findall(r"^### 馬號\s+(\d+)\s+—", text, re.M)]
        if not horse_nums:
            continue
        logic_path = target_dir / f"Race_{race_num}_Logic.json"
        if logic_path.exists():
            logic_path.unlink()
        for horse_num in horse_nums:
            cmd = [
                PYTHON,
                str(SCRIPT_DIR / "create_hkjc_logic_skeleton.py"),
                str(facts_path),
                str(race_num),
                str(horse_num),
            ]
            _run(cmd, f"Build Logic JSON — Race {race_num} Horse {horse_num}")


def _run_auto(target_dir: Path, validate_engine: bool) -> None:
    cmd = [
        PYTHON,
        str(AUTO_DIR / "hkjc_auto_orchestrator.py"),
        str(target_dir),
    ]
    if validate_engine:
        cmd.append("--validate-engine")
    _run(cmd, "HKJC Wong Choi Full Python Auto")


def main() -> None:
    parser = argparse.ArgumentParser(description="HKJC Wong Choi Full Python Orchestrator")
    parser.add_argument("target", help="HKJC racecard URL or meeting folder")
    parser.add_argument("--auto", action="store_true", help="Accepted for compatibility")
    parser.add_argument("--skip-extract", action="store_true", help="Skip HKJC web extraction")
    parser.add_argument("--skip-facts", action="store_true", help="Skip Facts.md generation")
    parser.add_argument("--skip-logic", action="store_true", help="Skip Race_X_Logic.json regeneration")
    parser.add_argument("--validate-engine", action="store_true", help="Run auto engine validation before scoring")
    args = parser.parse_args()

    target_dir, url = _resolve_target(args.target)
    _maybe_extract(url, target_dir, args.skip_extract)
    _generate_facts(target_dir, args.skip_facts)
    _generate_logic(target_dir, args.skip_logic)
    _run_auto(target_dir, args.validate_engine)


if __name__ == "__main__":
    main()
