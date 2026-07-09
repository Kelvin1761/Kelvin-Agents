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
import re
import subprocess
import argparse
from pathlib import Path
from datetime import datetime, timedelta

from subprocess_pool import bounded_workers, run_labeled_commands


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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
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
        print(f"  ❌ TIMEOUT after 900s")
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


def step2c_rebuild_stats() -> dict:
    """Rebuild jockey/trainer comprehensive_stats CSVs so the engine's continuous
    ratings + combo/distance priors reflect every completed meeting up to now.

    賽前重建：只會計到上一個已完成賽日（今場結果未有），對今場評分冇 lookahead，
    正正就係我哋要嘅「rating 貼市」。--write 會自動 backup .bak。跑贏就靠佢，
    出錯只警告唔中斷（沿用現有快照）。"""
    return run_script("build_comprehensive_stats.py", args=["--write"],
                      label="Step 2c: Rebuild Jockey/Trainer Stats")


def check_draw_stats_freshness(meeting_dir: Path) -> dict:
    """Loudly warn if hkjc_draw_stats.json doesn't match THIS meeting.

    Draw stats are per-meeting (racing.hkjc.com 檔位頁). If the scrape returned 0
    races (off-season/未出檔) the previous file is kept — and if that file is from
    another meeting, every 檔位 stat resolves to 「數據不可用」and scoring falls back
    to the position prior. That's exactly the stale-report failure we want surfaced,
    not hidden. Advisory only: never blocks the run, just makes staleness visible.
    """
    try:
        with open(DRAW_STATS_JSON, 'r', encoding='utf-8') as f:
            meta = json.load(f).get("meta", {})
    except Exception:
        print("   ⚠️ 檔位統計檔案缺失/讀取失敗 — 下游將顯示「數據不可用」並 fallback 位置先驗。")
        return {"status": "MISSING"}

    meeting_str = str(meta.get("meeting", ""))
    scraped_at = str(meta.get("scraped_at", ""))
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})_?(\w+)?", meeting_dir.name)
    exp_date = f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else ""
    folder_venue = (m.group(4) or "") if m else ""
    exp_venue = "沙田" if "Sha" in folder_venue else ("跑馬地" if "Happy" in folder_venue else "")

    date_ok = (not exp_date) or (exp_date in meeting_str)
    venue_ok = (not exp_venue) or (exp_venue in meeting_str)
    if date_ok and venue_ok:
        print(f"   ✅ 檔位統計匹配本賽日: {meeting_str} (scraped {scraped_at})")
        return {"status": "FRESH", "meeting": meeting_str}

    print("\n" + "!" * 60)
    print("   ⚠️⚠️  檔位統計不匹配本賽日 — 報告會用到錯/舊賽日數據！")
    print(f"       本賽日 : {(exp_venue + ' ' + exp_date).strip()}  (資料夾 {meeting_dir.name})")
    print(f"       檔位檔 : {meeting_str or '（空）'}  (scraped {scraped_at})")
    print("       → 檔位統計會 resolve 失敗顯示「數據不可用」、評分 fallback 位置先驗。")
    print("       → 請確認本賽日已出檔（今日 scrape 是否 0 場）再重跑，切勿用錯賽日數據出報告。")
    print("!" * 60)
    return {"status": "STALE", "meeting": meeting_str, "expected": f"{exp_venue} {exp_date}".strip()}


def step3_inject_facts(meeting_dir: Path, workers: int = 1) -> list:
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
        formguides = sorted(meeting_dir.glob("*賽績.md"))

    if not formguides:
        print(f"\n⚠️ No formguide files found in {meeting_dir}")
        return results

    print(f"\n📂 Found {len(formguides)} formguide(s) in {meeting_dir.name}")

    tasks = []
    for fg in formguides:
        # Extract race number from filename
        import re
        race_match = re.search(r'Race\s*(\d+)', fg.name, re.IGNORECASE)
        race_num = int(race_match.group(1)) if race_match else 0

        # Determine output path
        out_name = fg.name.replace("Formguide", "Facts").replace("formguide", "Facts").replace("賽績", "Facts")
        if not out_name.endswith(".md"):
            out_name = out_name.rsplit(".", 1)[0] + ".md" if "." in out_name else out_name + ".md"
        out_path = meeting_dir / out_name

        # Build inject command args
        inject_args = [str(fg), "--output", str(out_path)]
        if race_num > 0:
            inject_args.extend(["--race-num", str(race_num)])

        tasks.append({
            "label": f"Step 3: Race {race_num} Facts.md",
            "cmd": [sys.executable, str(SCRIPT_DIR / "inject_hkjc_fact_anchors.py"), *inject_args],
            "meta": {
                "script": "inject_hkjc_fact_anchors.py",
                "race_num": race_num,
                "output": str(out_path),
            },
        })

    task_results = run_labeled_commands(
        tasks,
        cwd=SCRIPT_DIR.parent.parent,
        max_workers=workers,
        timeout=900,
    )
    for result in task_results:
        results.append({
            "script": result.get("script", "inject_hkjc_fact_anchors.py"),
            "status": "OK" if result["returncode"] == 0 else "FAILED",
            "returncode": result["returncode"],
            "error": result.get("stderr") if result["returncode"] != 0 else None,
            "race_num": result.get("race_num"),
            "output": result.get("output"),
        })

    return results


def generate_summary(meeting_dir: Path, step1: dict, step2: dict, step3: list, step2c: dict = None) -> dict:
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
            "jockey_trainer_stats": step2c or {"status": "SKIPPED"},
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
    parser.add_argument("--skip-stats", action="store_true", help="Skip jockey/trainer stats rebuild")
    parser.add_argument("--skip-inject", action="store_true", help="Skip Facts.md injection")
    parser.add_argument("--inject-workers", type=int, default=1, help="Race-level Facts injection workers")
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

    # Step 2b: verify the (possibly kept) draw stats actually match THIS meeting
    draw_freshness = check_draw_stats_freshness(meeting_dir)

    # Step 2c: rebuild jockey/trainer stats so ratings/priors are current
    step2c = {"status": "SKIPPED"} if args.skip_stats else step2c_rebuild_stats()

    # Step 3: Facts Injection
    inject_workers = bounded_workers(args.inject_workers)
    step3 = [] if args.skip_inject else step3_inject_facts(meeting_dir, workers=inject_workers)

    # Generate summary
    summary = generate_summary(meeting_dir, step1, step2, step3, step2c)

    # Final report
    print(f"\n{'='*60}")
    print(f"✅ PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"   Standard Times: {step1.get('status', 'N/A')}")
    print(f"   Draw Stats: {step2.get('status', 'N/A')} | 匹配本賽日: {draw_freshness.get('status', 'N/A')}")
    print(f"   Jockey/Trainer Stats: {step2c.get('status', 'N/A')}")
    print(f"   Facts Injection: {summary['stats']['successful']}/{summary['stats']['total_races']} OK")
    if summary['stats']['failed'] > 0:
        print(f"   ⚠️ {summary['stats']['failed']} race(s) failed!")
    print(f"   Summary: {meeting_dir / 'pipeline_summary.json'}")


if __name__ == "__main__":
    main()
