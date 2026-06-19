#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
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
SHARED_HOOK_DIR = ROOT / ".agents" / "skills" / "shared_racing" / "post_success_hooks" / "scripts"

sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SHARED_SCRIPTS))
sys.path.insert(0, str(SHARED_HOOK_DIR))

from hkjc_orchestrator_helpers import (
    get_target_dir,
    parse_url_for_details,
    trigger_extractor,
)
from cloudflare_deploy_hook import run_post_success_cloudflare_deploy
from subprocess_pool import bounded_workers


PYTHON = sys.executable
TEMP_ROOT = ROOT / "_temporary_files"
TEMP_FILE_PATTERNS = (
    "racenet_temp_*.html",
    "latest_results.html",
    "temp_results.html",
    "test_results*.html",
    "test_yesterday.html",
    "daemon.log",
    "test_pdf.txt",
    "race",
)


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


def _generate_facts(target_dir: Path, skip_facts: bool, workers: int = 1) -> None:
    if skip_facts:
        return
    cmd = [
        PYTHON,
        str(SHARED_SCRIPTS / "run_prerace_pipeline.py"),
        str(target_dir),
        "--skip-std-times",
        "--skip-draw",
        "--inject-workers",
        str(workers),
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


def _extract_horse_nums(facts_path: Path) -> list[int]:
    text = facts_path.read_text(encoding="utf-8")
    return [int(x) for x in re.findall(r"^### 馬號\s+(\d+)\s+—", text, re.M)]


def _logic_needs_refresh(facts_path: Path, logic_path: Path, horse_nums: list[int]) -> bool:
    if not logic_path.exists():
        return True
    if facts_path.stat().st_mtime_ns > logic_path.stat().st_mtime_ns:
        return True
    try:
        logic_data = json.loads(logic_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return True
    horses = logic_data.get("horses")
    if not isinstance(horses, dict):
        return True
    expected = {str(num) for num in horse_nums}
    return not expected.issubset(horses.keys())


def _generate_logic(target_dir: Path, skip_logic: bool, workers: int = 1) -> None:
    if skip_logic:
        return
    facts_files = _iter_facts_files(target_dir)
    if not facts_files:
        raise SystemExit(f"❌ No Facts.md files found in {target_dir}")

    jobs = []
    for race_num, facts_path in facts_files:
        horse_nums = _extract_horse_nums(facts_path)
        if not horse_nums:
            raise SystemExit(f"❌ No horse sections found in {facts_path}")
        logic_path = target_dir / f"Race_{race_num}_Logic.json"
        if not _logic_needs_refresh(facts_path, logic_path, horse_nums):
            print(f"⏭️  Logic up-to-date — Race {race_num}")
            continue
        jobs.append((race_num, facts_path, horse_nums, logic_path))

    race_workers = bounded_workers(workers)
    if not jobs:
        return
    if race_workers == 1 or len(jobs) == 1:
        for job in jobs:
            _generate_logic_for_race(*job, stream=True)
        return

    print(f"⚙️ Building HKJC Logic for {len(jobs)} race(s) with {race_workers} worker(s)")
    with ThreadPoolExecutor(max_workers=race_workers) as executor:
        futures = [executor.submit(_generate_logic_for_race, *job, stream=False) for job in jobs]
        for future in as_completed(futures):
            result = future.result()
            print(result["stdout"], end="" if result["stdout"].endswith("\n") else "\n")
            if result["stderr"]:
                print(result["stderr"], file=sys.stderr, end="" if result["stderr"].endswith("\n") else "\n")
            if result["returncode"] != 0:
                raise SystemExit(result["returncode"])


def _generate_logic_for_race(
    race_num: int,
    facts_path: Path,
    horse_nums: list[int],
    logic_path: Path,
    *,
    stream: bool,
) -> dict[str, object]:
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    for horse_num in horse_nums:
        cmd = [
            PYTHON,
            str(SCRIPT_DIR / "create_hkjc_logic_skeleton.py"),
            str(facts_path),
            str(race_num),
            str(horse_num),
            "--output",
            str(logic_path),
        ]
        label = f"Build Logic JSON — Race {race_num} Horse {horse_num}"
        if stream:
            _run(cmd, label)
            continue
        result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
        stdout_parts.append(f"\n{'=' * 72}\n{label}\n{' '.join(cmd)}\n{'=' * 72}\n")
        stdout_parts.append(result.stdout or "")
        stderr_parts.append(result.stderr or "")
        if result.returncode != 0:
            return {
                "race_num": race_num,
                "returncode": result.returncode,
                "stdout": "".join(stdout_parts),
                "stderr": "".join(stderr_parts),
            }
    return {
        "race_num": race_num,
        "returncode": 0,
        "stdout": "".join(stdout_parts),
        "stderr": "".join(stderr_parts),
    }


def _run_auto(target_dir: Path, validate_engine: bool) -> None:
    cmd = [
        PYTHON,
        str(AUTO_DIR / "hkjc_auto_orchestrator.py"),
        str(target_dir),
    ]
    if validate_engine:
        cmd.append("--validate-engine")
    _run(cmd, "HKJC Wong Choi Full Python Auto")


def _cleanup_temp_artifacts(target_dir: Path | None) -> None:
    removed = 0
    for path in ROOT.glob("_mip_temp_*.html"):
        if path.is_file():
            path.unlink(missing_ok=True)
            removed += 1
    if TEMP_ROOT.exists():
        for pattern in TEMP_FILE_PATTERNS:
            for path in TEMP_ROOT.glob(pattern):
                if path.is_file():
                    path.unlink(missing_ok=True)
                    removed += 1
    if target_dir and target_dir.exists():
        for pattern in ("*.tmp", "*.tmp.*"):
            for path in target_dir.glob(pattern):
                if path.is_file():
                    path.unlink(missing_ok=True)
                    removed += 1
    if removed:
        print(f"🧹 Removed {removed} temporary file(s)")


def _default_race_workers() -> int:
    try:
        return int(os.environ.get("WC_RACE_WORKERS", "3"))
    except ValueError:
        return 3


def main() -> None:
    parser = argparse.ArgumentParser(description="HKJC Wong Choi Full Python Orchestrator")
    parser.add_argument("target", help="HKJC racecard URL or meeting folder")
    parser.add_argument("--auto", action="store_true", help="Accepted for compatibility")
    parser.add_argument("--skip-extract", action="store_true", help="Skip HKJC web extraction")
    parser.add_argument("--skip-facts", action="store_true", help="Skip Facts.md generation")
    parser.add_argument("--skip-logic", action="store_true", help="Skip Race_X_Logic.json regeneration")
    parser.add_argument("--validate-engine", action="store_true", help="Run auto engine validation before scoring")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary files after completion")
    parser.add_argument("--skip-cloudflare-deploy", action="store_true", help="Skip post-success Cloudflare deploy")
    parser.add_argument("--batch-cloudflare-deploy", action="store_true", help="Queue dashboard deploy for a later batch flush")
    parser.add_argument("--flush-cloudflare-deploy", action="store_true", help="Flush any queued dashboard deploy after this run")
    parser.add_argument("--race-workers", type=int, default=_default_race_workers(), help="Race-level Facts/Logic workers")
    args = parser.parse_args()

    target_dir: Path | None = None
    try:
        target_dir, url = _resolve_target(args.target)
        _maybe_extract(url, target_dir, args.skip_extract)
        race_workers = bounded_workers(args.race_workers)
        print(f"⚙️ Race-level workers: {race_workers}")
        _generate_facts(target_dir, args.skip_facts, race_workers)
        _generate_logic(target_dir, args.skip_logic, race_workers)
        _run_auto(target_dir, args.validate_engine)
        run_post_success_cloudflare_deploy(
            source="HKJC Wong Choi",
            target_dir=target_dir,
            skip=args.skip_cloudflare_deploy,
            batch=args.batch_cloudflare_deploy,
            flush_batch=args.flush_cloudflare_deploy,
            allow_failure=True,
        )
    finally:
        if not args.keep_temp:
            _cleanup_temp_artifacts(target_dir)


if __name__ == "__main__":
    main()
