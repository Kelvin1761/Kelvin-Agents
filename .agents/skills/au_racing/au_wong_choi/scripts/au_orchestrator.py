#!/usr/bin/env python3
"""AU Wong Choi main orchestrator — full Python mainline."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
SHARED_SCRIPTS = PROJECT_ROOT / ".agents" / "scripts"
SHARED_HOOK_DIR = PROJECT_ROOT / ".agents" / "skills" / "shared_racing" / "post_success_hooks" / "scripts"

sys.path.insert(0, str(SHARED_SCRIPTS))
sys.path.insert(0, str(SHARED_HOOK_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from cloudflare_deploy_hook import run_post_success_cloudflare_deploy
from subprocess_pool import bounded_workers, run_labeled_commands
from wongchoi_paths import AU_RACING

PYTHON = sys.executable
EXTRACTOR = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_race_extractor" / "scripts" / "extractor.py"
FACTS_INJECTOR = PROJECT_ROOT / ".agents" / "scripts" / "inject_fact_anchors.py"
AUTO_LOGIC = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "build_au_logic.py"
AUTO_ORCH = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "au_auto_orchestrator.py"
TEMP_ROOT = PROJECT_ROOT / "_temporary_files"
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


def main():
    parser = argparse.ArgumentParser(description="AU Wong Choi Full Python Orchestrator")
    parser.add_argument("target", help="Racenet URL, meeting directory, or Race_X_Logic.json")
    parser.add_argument("--auto", action="store_true", help="Compatibility flag")
    parser.add_argument("--autopilot", action="store_true", help="Compatibility flag")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary files after completion")
    parser.add_argument("--skip-cloudflare-deploy", action="store_true", help="Skip post-success Cloudflare deploy")
    parser.add_argument("--batch-cloudflare-deploy", action="store_true", help="Queue dashboard deploy for a later batch flush")
    parser.add_argument("--flush-cloudflare-deploy", action="store_true", help="Flush any queued dashboard deploy after this run")
    parser.add_argument("--race-workers", type=int, default=_default_race_workers(), help="Race-level Facts/Logic workers")
    args = parser.parse_args()

    target = args.target.strip()

    cleanup_target: Path | None = None
    try:
        if _looks_like_url(target):
            meeting_dir = _extract_meeting(target)
        else:
            meeting_dir = Path(target).resolve()
            if meeting_dir.is_file():
                cleanup_target = meeting_dir.parent
                _run([PYTHON, str(AUTO_ORCH), str(meeting_dir)])
                run_post_success_cloudflare_deploy(
                    source="AU Wong Choi",
                    target_dir=meeting_dir.parent,
                    skip=args.skip_cloudflare_deploy,
                    batch=args.batch_cloudflare_deploy,
                    flush_batch=args.flush_cloudflare_deploy,
                    allow_failure=True,
                )
                return
            if not meeting_dir.exists():
                raise FileNotFoundError(meeting_dir)

        cleanup_target = meeting_dir
        print("=" * 68)
        print("🏇 AU Wong Choi — Full Python Mainline")
        print("=" * 68)
        print(f"📁 Meeting Dir: {meeting_dir}")

        race_workers = bounded_workers(args.race_workers)
        print(f"⚙️ Race-level workers: {race_workers}")
        _ensure_facts(meeting_dir, race_workers)
        _ensure_logic(meeting_dir, race_workers)
        _run([PYTHON, str(AUTO_ORCH), str(meeting_dir)])
        run_post_success_cloudflare_deploy(
            source="AU Wong Choi",
            target_dir=meeting_dir,
            skip=args.skip_cloudflare_deploy,
            batch=args.batch_cloudflare_deploy,
            flush_batch=args.flush_cloudflare_deploy,
            allow_failure=True,
        )

        print("=" * 68)
        print("✅ AU full-Python pipeline complete")
        print("=" * 68)
    finally:
        if not args.keep_temp:
            _cleanup_temp_artifacts(cleanup_target)


def _looks_like_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _default_race_workers() -> int:
    try:
        return int(os.environ.get("WC_RACE_WORKERS", "3"))
    except ValueError:
        return 3


def _extract_meeting(url: str) -> Path:
    print("🚀 Extracting AU meeting data via Race Extractor...")
    _run([PYTHON, str(EXTRACTOR), url, "all"])
    meeting_dir = _get_target_dir_from_url(url)
    if not meeting_dir or not meeting_dir.exists():
        raise FileNotFoundError(f"Cannot locate extracted meeting directory for URL: {url}")
    return meeting_dir


def _get_target_dir_from_url(url: str) -> Path | None:
    match = re.search(r"form-guide/horse-racing/([^/]+)-(\d{8})", url)
    if not match:
        return None
    venue = match.group(1).replace("-", " ").title()
    date_str = match.group(2)
    formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    candidates = []
    for path in AU_RACING.iterdir():
        if not path.is_dir():
            continue
        if path.name.startswith(f"{formatted_date} {venue}") or path.name.startswith(f"{formatted_date}_{venue}_Race_"):
            candidates.append(path)
    if not candidates:
        return None
    return max(candidates, key=_meeting_candidate_score)


def _meeting_candidate_score(path: Path) -> tuple[int, int, int]:
    relevant = 0
    total = 0
    for child in path.iterdir():
        total += 1
        if child.is_file() and (
            child.name.endswith("Racecard.md")
            or child.name.endswith("Formguide.md")
            or child.name.endswith("Facts.md")
            or child.name.startswith("Race_")
        ):
            relevant += 1
    return relevant, total, path.stat().st_mtime_ns


def _ensure_facts(meeting_dir: Path, workers: int = 1) -> None:
    racecards = sorted(meeting_dir.glob("*Racecard.md"))
    formguides = sorted(meeting_dir.glob("*Formguide.md"))
    if not racecards or not formguides:
        raise FileNotFoundError(f"Missing Racecard/Formguide files in {meeting_dir}")
    tasks = []
    for racecard in racecards:
        race_num = _race_num_from_name(racecard.name)
        if race_num is None:
            continue
        formguide = _matching_formguide(formguides, race_num)
        if not formguide:
            raise FileNotFoundError(f"Missing Formguide for Race {race_num} in {meeting_dir}")
        facts_candidates = sorted(meeting_dir.glob(f"*Race_{race_num}_Facts.md"))
        facts_path = facts_candidates[0] if facts_candidates else None
        if facts_path and not _is_output_stale(facts_path, racecard, formguide):
            continue
        venue = _venue_from_meeting(meeting_dir.name)
        distance = _distance_for_race(racecard, formguide)
        print(f"🧩 Generating Facts for Race {race_num}...")
        cmd = [PYTHON, str(FACTS_INJECTOR), str(racecard), str(formguide), "--max-display", "5", "--venue", venue]
        if distance:
            cmd.extend(["--distance", str(distance)])
        tasks.append({"label": f"Generate Facts — Race {race_num}", "cmd": cmd})
    run_labeled_commands(tasks, cwd=PROJECT_ROOT, max_workers=workers)


def _ensure_logic(meeting_dir: Path, workers: int = 1) -> None:
    facts_files = sorted(meeting_dir.glob("*Facts.md"), key=lambda p: (_race_num_from_name(p.name) or 999))
    if not facts_files:
        raise FileNotFoundError(f"No Facts.md files found in {meeting_dir}")
    tasks = []
    for facts in facts_files:
        race_num = _race_num_from_name(facts.name)
        if race_num is None:
            continue
        logic_path = meeting_dir / f"Race_{race_num}_Logic.json"
        if logic_path.exists() and not _is_output_stale(logic_path, facts) and _logic_has_horses(logic_path):
            continue
        print(f"🧠 Building deterministic Logic for Race {race_num}...")
        tasks.append({
            "label": f"Build deterministic Logic — Race {race_num}",
            "cmd": [PYTHON, str(AUTO_LOGIC), str(facts), "--output", str(logic_path)],
        })
    run_labeled_commands(tasks, cwd=PROJECT_ROOT, max_workers=workers)


def _matching_formguide(formguides: list[Path], race_num: int) -> Path | None:
    for path in formguides:
        if _race_num_from_name(path.name) == race_num:
            return path
    return None


def _race_num_from_name(name: str) -> int | None:
    match = re.search(r"Race[ _](\d+)", name)
    return int(match.group(1)) if match else None


def _venue_from_meeting(meeting_name: str) -> str:
    # Remove date prefix: "2025-01-15_Randwick_Race_1_1200m" → "Randwick_Race_1_1200m"
    name = re.sub(r"^\d{4}-\d{2}-\d{2}[_\s-]*", "", meeting_name).strip()
    if "_" in name:
        # Take first word before any underscore followed by "Race" or number
        parts = name.split("_")
        venue_parts = []
        for p in parts:
            if re.match(r"^race\s*\d+", p, re.I) or re.match(r"^\d+", p):
                break
            venue_parts.append(p)
        if venue_parts:
            return " ".join(venue_parts)
        return parts[0]
    parts = name.split()
    return " ".join(parts[1:-3]) if len(parts) > 3 and "Race" in name else name


def _distance_for_race(racecard: Path, formguide: Path | None) -> int | None:
    for path in (racecard, formguide):
        if not path or not path.exists():
            continue
        distance = _extract_distance_from_text(path.read_text(encoding="utf-8"))
        if distance:
            return distance
    return None


def _extract_distance_from_text(text: str) -> int | None:
    patterns = (
        r"^RACE\s+\d+\s*[—–-]\s*(\d{3,5})m",
        r"^\s*RACE\s+\d+\s*\|\s*(\d{3,5})m",
        r"^\s*RACE\s+\d+\s*\n.*?(\d{3,5})m",
        r"\b(\d{3,5})m\s*\|",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.M | re.S)
        if match:
            return int(match.group(1))
    return None


def _is_output_stale(output_path: Path, *source_paths: Path) -> bool:
    if not output_path.exists():
        return True
    output_mtime = output_path.stat().st_mtime_ns
    for source_path in source_paths:
        if source_path.exists() and source_path.stat().st_mtime_ns > output_mtime:
            return True
    return False


def _logic_has_horses(logic_path: Path) -> bool:
    try:
        logic = json.loads(logic_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, AttributeError):
        return False
    if not isinstance(logic, dict):
        return False
    horses = logic.get("horses")
    return isinstance(horses, dict) and bool(horses)


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, text=True)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _cleanup_temp_artifacts(target_dir: Path | None) -> None:
    removed = 0
    for path in PROJECT_ROOT.glob("_mip_temp_*.html"):
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


if __name__ == "__main__":
    main()
