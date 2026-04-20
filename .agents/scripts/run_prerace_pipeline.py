#!/usr/bin/env python3
"""
run_prerace_pipeline.py — 一鍵賽前數據準備管線

Usage:
    python3 run_prerace_pipeline.py <meeting_folder>
    python3 run_prerace_pipeline.py 2026-04-22_HappyValley/

Pipeline Steps:
    1. Sync standard times (skip if <30 days old)
    2. Scrape draw stats (always refresh)
    3. For each race: inject Facts.md with --race-num
    4. Generate pipeline_summary.json
"""
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import json
import subprocess
import argparse
from pathlib import Path
from datetime import datetime, timedelta


SCRIPT_DIR = Path(__file__).parent
STANDARD_TIMES_JSON = SCRIPT_DIR / "hkjc_standard_times.json"
DRAW_STATS_JSON = SCRIPT_DIR / "hkjc_draw_stats.json"
STD_TIMES_MAX_AGE_DAYS = 30


def run_script(script_name: str, args: list = None, label: str = "") -> dict:
    """Run a Python script and return status."""
    cmd = [sys.executable, str(SCRIPT_DIR / script_name)] + (args or [])
    label = label or script_name
    print(f"\n{'='*60}")
    print(f"🔄 [{label}] {' '.join(cmd)}")
    print(f"{'='*60}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return {
            "script": script_name,
            "status": "OK" if result.returncode == 0 else "FAILED",
            "returncode": result.returncode,
            "error": result.stderr if result.returncode != 0 else None
        }
    except subprocess.TimeoutExpired:
        print(f"  ❌ TIMEOUT after 120s")
        return {"script": script_name, "status": "TIMEOUT", "returncode": -1}
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return {"script": script_name, "status": "ERROR", "returncode": -1, "error": str(e)}


def step1_sync_standard_times() -> dict:
    """Sync standard times (skip if recent enough)."""
    if STANDARD_TIMES_JSON.exists():
        try:
            with open(STANDARD_TIMES_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)
            scraped_at = data.get("meta", {}).get("scraped_at", "")
            if scraped_at:
                scraped_date = datetime.strptime(scraped_at, "%Y-%m-%d %H:%M:%S")
                age = datetime.now() - scraped_date
                if age < timedelta(days=STD_TIMES_MAX_AGE_DAYS):
                    n = len(data.get("standard_times", {}))
                    print(f"\n✅ Standard times up-to-date ({n} entries, {age.days}d old) — skipping")
                    return {"script": "scrape_standard_times.py", "status": "SKIPPED",
                            "reason": f"{age.days}d old < {STD_TIMES_MAX_AGE_DAYS}d threshold"}
        except Exception:
            pass

    return run_script("scrape_standard_times.py", label="Step 1: Standard Times Sync")


def step2_scrape_draw_stats() -> dict:
    """Scrape draw stats (always refresh — data changes per meeting)."""
    return run_script("scrape_draw_stats.py", label="Step 2: Draw Stats Scrape")


def step3_inject_facts(meeting_dir: Path) -> list:
    """Inject Facts.md for each race in the meeting folder."""
    results = []

    # Find all formguide files
    formguides = sorted(meeting_dir.glob("*Formguide*.txt"))
    if not formguides:
        # Try alternative patterns
        formguides = sorted(meeting_dir.glob("*formguide*.txt"))
    if not formguides:
        formguides = sorted(meeting_dir.glob("*Race*Formguide*"))

    if not formguides:
        print(f"\n⚠️ No formguide files found in {meeting_dir}")
        return results

    print(f"\n📂 Found {len(formguides)} formguide(s) in {meeting_dir.name}")

    for fg in formguides:
        # Extract race number from filename
        import re
        race_match = re.search(r'Race\s*(\d+)', fg.name, re.IGNORECASE)
        race_num = int(race_match.group(1)) if race_match else 0

        # Determine output path
        out_name = fg.name.replace("Formguide", "Facts").replace("formguide", "Facts")
        if not out_name.endswith(".md"):
            out_name = out_name.rsplit(".", 1)[0] + ".md" if "." in out_name else out_name + ".md"
        out_path = meeting_dir / out_name

        # Build inject command args
        inject_args = [str(fg), "--output", str(out_path)]
        if race_num > 0:
            inject_args.extend(["--race-num", str(race_num)])

        result = run_script("inject_hkjc_fact_anchors.py", inject_args,
                           label=f"Step 3: Race {race_num} Facts.md")
        result["race_num"] = race_num
        result["output"] = str(out_path)
        results.append(result)

    return results


def generate_summary(meeting_dir: Path, step1: dict, step2: dict, step3: list) -> dict:
    """Generate pipeline_summary.json."""
    summary = {
        "meta": {
            "pipeline": "run_prerace_pipeline.py",
            "meeting_dir": str(meeting_dir),
            "executed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "steps": {
            "standard_times": step1,
            "draw_stats": step2,
            "facts_injection": step3,
        },
        "stats": {
            "total_races": len(step3),
            "successful": sum(1 for r in step3 if r.get("status") == "OK"),
            "failed": sum(1 for r in step3 if r.get("status") != "OK"),
        },
        "data_files": {
            "standard_times": str(STANDARD_TIMES_JSON),
            "draw_stats": str(DRAW_STATS_JSON),
        }
    }

    summary_path = meeting_dir / "pipeline_summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return summary


def main():
    parser = argparse.ArgumentParser(description="HKJC Pre-Race Data Pipeline")
    parser.add_argument("meeting_dir", help="Path to meeting directory (e.g. 2026-04-22_HappyValley/)")
    parser.add_argument("--skip-std-times", action="store_true", help="Skip standard times sync")
    parser.add_argument("--skip-draw", action="store_true", help="Skip draw stats scrape")
    parser.add_argument("--skip-inject", action="store_true", help="Skip Facts.md injection")
    args = parser.parse_args()

    meeting_dir = Path(args.meeting_dir).resolve()
    if not meeting_dir.exists():
        print(f"❌ Directory not found: {meeting_dir}")
        sys.exit(1)

    print(f"🏇 HKJC Pre-Race Pipeline — {meeting_dir.name}")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Scripts: {SCRIPT_DIR}")

    # Step 1: Standard Times
    step1 = {"status": "SKIPPED"} if args.skip_std_times else step1_sync_standard_times()

    # Step 2: Draw Stats
    step2 = {"status": "SKIPPED"} if args.skip_draw else step2_scrape_draw_stats()

    # Step 3: Facts Injection
    step3 = [] if args.skip_inject else step3_inject_facts(meeting_dir)

    # Generate summary
    summary = generate_summary(meeting_dir, step1, step2, step3)

    # Final report
    print(f"\n{'='*60}")
    print(f"✅ PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"   Standard Times: {step1.get('status', 'N/A')}")
    print(f"   Draw Stats: {step2.get('status', 'N/A')}")
    print(f"   Facts Injection: {summary['stats']['successful']}/{summary['stats']['total_races']} OK")
    if summary['stats']['failed'] > 0:
        print(f"   ⚠️ {summary['stats']['failed']} race(s) failed!")
    print(f"   Summary: {meeting_dir / 'pipeline_summary.json'}")


if __name__ == "__main__":
    main()
