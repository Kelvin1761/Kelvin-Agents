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
AUTO_ENGINE_DIR = (
    PROJECT_ROOT
    / ".agents"
    / "skills"
    / "au_racing"
    / "au_wong_choi_auto"
    / "scripts"
)

sys.path.insert(0, str(SHARED_SCRIPTS))
sys.path.insert(0, str(SHARED_HOOK_DIR))
sys.path.insert(0, str(AUTO_ENGINE_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from cloudflare_deploy_hook import run_post_success_cloudflare_deploy
from au_racing_engine.source_alignment import validate_facts_horse_alignment, venue_from_meeting_name
from subprocess_pool import bounded_workers, run_labeled_commands
from wongchoi_paths import AU_RACING

PYTHON = sys.executable
FACTS_INJECTOR = PROJECT_ROOT / ".agents" / "scripts" / "inject_fact_anchors.py"
AUTO_LOGIC = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "build_au_logic.py"
AUTO_ORCH = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "au_auto_orchestrator.py"
COMPLIANCE_SCAN = (
    PROJECT_ROOT
    / ".agents"
    / "skills"
    / "race_compliance_qa"
    / "scripts"
    / "race_compliance_scan.py"
)
TEMP_ROOT = PROJECT_ROOT / "_temporary_files"
TEMP_FILE_PATTERNS = (
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
    parser.add_argument("target", help="SportsbetForm URL, meeting directory, or Race_X_Logic.json")
    parser.add_argument("--auto", action="store_true", help="Compatibility flag")
    parser.add_argument("--autopilot", action="store_true", help="Compatibility flag")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary files after completion")
    parser.add_argument("--skip-cloudflare-deploy", action="store_true", help="Skip post-success Cloudflare deploy")
    parser.add_argument("--batch-cloudflare-deploy", action="store_true", help="Queue dashboard deploy for a later batch flush")
    parser.add_argument("--flush-cloudflare-deploy", action="store_true", help="Flush any queued dashboard deploy after this run")
    parser.add_argument("--race-workers", type=int, default=_default_race_workers(), help="Race-level Facts/Logic workers")
    parser.add_argument(
        "--going",
        help="Official current track condition (e.g. 'Good 4'); overrides stored meeting data",
    )
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
                official_going = _resolve_official_going(meeting_dir.parent, args.going)
                _run(_auto_command(meeting_dir, official_going))
                _run_compliance_gate(meeting_dir.parent)
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
        official_going = _resolve_official_going(meeting_dir, args.going)
        _run(_auto_command(meeting_dir, official_going))
        _run_compliance_gate(meeting_dir)
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


SPORTSBET_EXTRACTOR = (PROJECT_ROOT / ".agents" / "skills" / "au_racing"
                       / "claw_sportsbet_form.py")
SPORTSBET_MEETING_IDS = (
    PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "data"
    / "sb_archive_meeting_ids.json"
)


def _extract_meeting(url: str) -> Path:
    # AU 抽取只有一條路：Sportsbet。Racenet 三條 transport 2026-08-02 全封
    # （profile 403、results 202 攔截頁、Playwright 202），而 2026-08-04 連
    # extractor、transport、profile scraper 一併剷走，所以呢度冇 fallback ——
    # 唔係 sportsbetform 嘅 URL 直接停低。
    #
    # ⚠️ 以前有個 `WC_ALLOW_RACENET=1` 逃生門。剷咗係因為佢已經冇嘢可以行到：
    # 目標腳本唔存在，set 咗只會換一個更難讀嘅 ImportError。
    if "sportsbetform" in url:
        dir_name, meeting = _sportsbet_meeting_spec(url)
        meeting_dir = AU_RACING / dir_name
        print("🚀 Extracting AU meeting data via Sportsbet...")
        _run([
            PYTHON,
            str(SPORTSBET_EXTRACTOR),
            "--meeting-url",
            url,
            "--races",
            ",".join(str(race_id) for race_id in meeting["races"]),
            "--out-dir",
            str(meeting_dir),
            "--date",
            str(meeting["date"]),
            "--venue",
            _venue_from_meeting(dir_name),
        ])
        if not meeting_dir.exists():
            raise FileNotFoundError(f"Sportsbet extractor did not create {meeting_dir}")
        return meeting_dir
    raise SystemExit(
        f"❌ 唔識抽呢個 URL：{url}\n"
        "   AU Wong Choi 只用 Sportsbet（Racenet 2026-08-02 全封，"
        "相關腳本 2026-08-04 已剷走）。\n"
        "   抽取請用：\n"
        "     python3 .agents/skills/au_racing/claw_sportsbet_form.py \\\n"
        "       --meeting-url https://www.sportsbetform.com.au/<meetingId>/<raceId>/ \\\n"
        "       --races <raceId,raceId,...> --out-dir '<meeting dir>' \\\n"
        "       --date YYYY-MM-DD --venue '<track>'\n"
        "   然後把 meeting 目錄餵返呢個 orchestrator。")


def _sportsbet_meeting_spec(
    url: str,
    mapping_path: Path | None = None,
) -> tuple[str, dict]:
    """Resolve one Sportsbet race URL to the complete tracked meeting.

    A race URL contains only meetingId/raceId.  The tracked date index is the
    authoritative source for the date, venue, full race list and output folder;
    guessing those values would re-introduce race-order/data-alignment errors.
    """
    mapping_path = mapping_path or SPORTSBET_MEETING_IDS
    match = re.search(r"sportsbetform\.com\.au/(\d+)/(\d+)(?:/|$)", url, re.I)
    if not match:
        raise ValueError(f"Invalid SportsbetForm race URL: {url}")
    meeting_id, race_id = match.groups()
    try:
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read Sportsbet meeting index {mapping_path}: {exc}") from exc
    matches = [
        (name, meta)
        for name, meta in mapping.items()
        if str(meta.get("meetingId")) == meeting_id
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Sportsbet meetingId {meeting_id} is not uniquely tracked in {mapping_path}; "
            "run the daily discovery first."
        )
    dir_name, meeting = matches[0]
    race_ids = {str(value) for value in meeting.get("races", [])}
    if race_id not in race_ids:
        raise ValueError(
            f"Sportsbet raceId {race_id} is not listed under meetingId {meeting_id}; "
            "refresh the daily meeting index before extraction."
        )
    required = {"date", "races"}
    missing = sorted(key for key in required if not meeting.get(key))
    if missing:
        raise ValueError(f"Incomplete Sportsbet meeting index for {dir_name}: {missing}")
    return dir_name, meeting


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
        facts_path = _find_facts_file(meeting_dir, race_num)
        if (
            facts_path
            and _facts_has_horses(facts_path)
            and not _is_output_stale(facts_path, racecard, formguide)
        ):
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


def _find_facts_file(meeting_dir: Path, race_num: int) -> Path | None:
    for pattern in (
        f"*Race_{race_num}_Facts.md",
        f"*Race {race_num} Facts.md",
    ):
        matches = sorted(path for path in meeting_dir.glob(pattern) if path.is_file())
        if matches:
            return matches[0]
    return None


def _facts_has_horses(facts_path: Path) -> bool:
    try:
        text = facts_path.read_text(encoding="utf-8")
        return bool(validate_facts_horse_alignment(text, source=facts_path.name))
    except (OSError, UnicodeError, ValueError):
        return False


def _race_num_from_name(name: str) -> int | None:
    match = re.search(r"Race[ _](\d+)", name)
    return int(match.group(1)) if match else None


def _venue_from_meeting(meeting_name: str) -> str:
    return venue_from_meeting_name(meeting_name)


def _resolve_official_going(meeting_dir: Path, override: str | None) -> str | None:
    if override and override.strip():
        return override.strip()
    summary_path = meeting_dir / "Meeting_Summary.md"
    if not summary_path.exists():
        return None
    match = re.search(
        r"^Track Condition:\s*([^\n]+)",
        summary_path.read_text(encoding="utf-8"),
        re.M,
    )
    return match.group(1).strip() if match else None


def _auto_command(target: Path, official_going: str | None) -> list[str]:
    command = [PYTHON, str(AUTO_ORCH), str(target)]
    if official_going:
        command.extend(["--going", official_going])
    return command


def _run_compliance_gate(meeting_dir: Path) -> None:
    """Block publish when raw/Logic/rendered/result layers drift."""
    _run(
        [
            PYTHON,
            str(COMPLIANCE_SCAN),
            "--root",
            str(meeting_dir),
            "--platform",
            "au",
        ]
    )


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
