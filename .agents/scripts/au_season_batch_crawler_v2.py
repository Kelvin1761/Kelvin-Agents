"""
AU Wong Choi - Season Batch Crawler v2
Covers ALL Tier 1 and Tier 2 AU venues, race by race, with anti-block pacing.

Tier 1 (premium metro): randwick, flemington, rosehill, caulfield, eagle-farm, moonee-valley
Tier 2 (major metro): warwick-farm, canterbury, pakenham, sandown-lakeside, doomben, hawkesbury
Tier 2/3 (provincial): gosford, geelong, cranbourne, newcastle, caulfield-heath, sale, gold-coast, ballarat

Slow pacing: 20-45s between meetings, 1-3s between track checks.
Uses chrome136 curl_cffi impersonation + local Chrome profile fallback.
"""

import os
import sys
import time
import random
import datetime
import subprocess
import glob
import shutil
from curl_cffi import requests

START_DATE = datetime.date(2025, 8, 1)
END_DATE = datetime.date.today()

# All tier 1 + tier 2 venues, in slugs Racenet uses
TRACKS_TIER_1 = [
    "randwick",
    "flemington",
    "rosehill-gardens",
    "caulfield",
    "eagle-farm",
    "moonee-valley",
]

TRACKS_TIER_2 = [
    "warwick-farm",
    "canterbury",
    "pakenham",
    "sandown-lakeside",
    "doomben",
    "hawkesbury",
    "newcastle",
    "caulfield-heath",
]

TRACKS = TRACKS_TIER_1 + TRACKS_TIER_2

# Folder name mapping (Racenet slug -> folder display name)
SLUG_TO_DISPLAY = {
    "randwick": "Randwick",
    "flemington": "Flemington",
    "rosehill-gardens": "Rosehill Gardens",
    "caulfield": "Caulfield",
    "eagle-farm": "Eagle Farm",
    "moonee-valley": "Moonee Valley",
    "warwick-farm": "Warwick Farm",
    "canterbury": "Canterbury",
    "pakenham": "Pakenham",
    "sandown-lakeside": "Sandown Lakeside",
    "doomben": "Doomben",
    "hawkesbury": "Hawkesbury",
    "newcastle": "Newcastle",
    "caulfield-heath": "Caulfield Heath",
}

# Paths
ORCHESTRATOR_PATH = os.path.join(
    ".agents", "skills", "au_racing", "au_wong_choi", "scripts", "au_orchestrator.py"
)
RESULTS_SCRIPT_PATH = os.path.join(
    ".agents", "skills", "au_racing", "claw_racenet_results.py"
)
REFLECTOR_PATH = os.path.join(
    ".agents", "skills", "au_racing", "au_reflector", "scripts", "au_reflector_orchestrator.py"
)
ARCHIVE_DIR = os.path.join("Archive_Race_Analysis", "AU_Racing")

# Anti-block pacing
SLEEP_BETWEEN_TRACK_CHECKS = (1.5, 3.0)
SLEEP_BETWEEN_MEETINGS = (20, 45)
SLEEP_BEFORE_RETRY = (60, 120)
MAX_CONSECUTIVE_FAILURES = 5


def make_env():
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    return env


def check_track_on_date(slug, date_obj):
    """Check if Racenet has race data for a given track/date."""
    date_compact = date_obj.strftime("%Y%m%d")
    url = f"https://www.racenet.com.au/results/horse-racing/{slug}-{date_compact}/all-races"
    try:
        r = requests.get(url, impersonate="chrome136", timeout=15)
        # If meeting doesn't exist, Racenet redirects to /results/horse-racing/ (no slug)
        if r.status_code == 200 and slug in r.url:
            return True
    except Exception as e:
        print(f"  [Check Error] {slug} {date_compact}: {e}")
    return False


def is_meeting_complete(folder_path):
    """Check if meeting has full pipeline output (analysis + results)."""
    has_logic = len(glob.glob(os.path.join(folder_path, "Race_*_Logic.json"))) >= 1
    has_analysis = len(glob.glob(os.path.join(folder_path, "Race_*_Auto_Analysis.md"))) >= 1
    has_scoring = len(glob.glob(os.path.join(folder_path, "Race_*_Auto_Scoring.csv"))) >= 1
    has_results = (
        len(glob.glob(os.path.join(folder_path, "*Result*.md"))) > 0
        or len(glob.glob(os.path.join(folder_path, "*Result*.txt"))) > 0
    )
    return has_logic and has_analysis and has_scoring and has_results


def find_existing_folder(date_obj, track_slug):
    """Find existing folder for this meeting if any."""
    date_dashed = date_obj.strftime("%Y-%m-%d")
    display = SLUG_TO_DISPLAY.get(track_slug, track_slug.title())
    for f in os.listdir(ARCHIVE_DIR):
        if f.startswith(date_dashed) and track_slug.replace("-", " ") in f.lower():
            return os.path.join(ARCHIVE_DIR, f)
    return None


def move_orchestrator_output(date_obj, track_slug):
    """Move orchestrator output from project root to archive."""
    date_dashed = date_obj.strftime("%Y-%m-%d")
    display = SLUG_TO_DISPLAY.get(track_slug, track_slug.title())
    project_root = os.getcwd()
    pattern = os.path.join(project_root, f"{date_dashed}*{display.split()[0]}*")
    candidates = [p for p in glob.glob(pattern) if os.path.isdir(p)]
    if not candidates:
        return None
    src = candidates[0]
    dst = os.path.join(ARCHIVE_DIR, os.path.basename(src))
    if os.path.abspath(src) != os.path.abspath(dst):
        try:
            if os.path.exists(dst):
                shutil.copytree(src, dst, dirs_exist_ok=True)
                shutil.rmtree(src)
            else:
                shutil.move(src, dst)
        except Exception as e:
            print(f"  [Move Error] {src} -> {dst}: {e}")
    return dst


def process_meeting(track_slug, date_obj):
    """Full pipeline: extract + facts + logic + analysis + results + reflector."""
    date_dashed = date_obj.strftime("%Y-%m-%d")
    date_compact = date_obj.strftime("%Y%m%d")
    display = SLUG_TO_DISPLAY.get(track_slug, track_slug.title())

    # Check if already complete
    existing = find_existing_folder(date_obj, track_slug)
    if existing and is_meeting_complete(existing):
        print(f"  [{date_dashed}] {display} ✅ 已經有完整分析+賽果，自動跳過")
        return True

    env = make_env()
    target_folder = existing

    # 1. Run orchestrator (extract + facts + logic + analysis)
    form_guide_url = (
        f"https://www.racenet.com.au/form-guide/horse-racing/{track_slug}-{date_compact}/all-races"
    )
    print(f"\n[{date_dashed}] 🚀 {display} 啟動完整 Pipeline...")
    print(f"  Form Guide URL: {form_guide_url}")

    cmd_orch = ["python3", ORCHESTRATOR_PATH, form_guide_url, "--skip-cloudflare-deploy"]
    try:
        result = subprocess.run(cmd_orch, env=env, timeout=3000)
        if result.returncode != 0:
            print(f"  ⚠️ Orchestrator returncode={result.returncode}")
    except subprocess.TimeoutExpired:
        print(f"  ⏱️ Orchestrator timeout")
    except Exception as e:
        print(f"  ❌ Orchestrator failed: {e}")

    # Move orchestrator output
    if not target_folder:
        target_folder = move_orchestrator_output(date_obj, track_slug)
    if not target_folder:
        print(f"  ⚠️ 找不到 Orchestrator 產出資料夾，跳過 {display} on {date_dashed}")
        return False

    # 2. Run race results crawler
    results_url = (
        f"https://www.racenet.com.au/results/horse-racing/{track_slug}-{date_compact}/all-races"
    )
    print(f"  [{date_dashed}] 📋 下載賽果 ({display})...")
    cmd_res = ["python3", RESULTS_SCRIPT_PATH, "--url", results_url, "--output_dir", target_folder]
    try:
        result = subprocess.run(cmd_res, env=env, timeout=300)
        if result.returncode != 0:
            print(f"  ⚠️ Results crawler returncode={result.returncode}")
    except subprocess.TimeoutExpired:
        print(f"  ⏱️ Results crawler timeout")
    except Exception as e:
        print(f"  ❌ Results crawler failed: {e}")

    # 3. Run reflector (analysis vs results comparison)
    print(f"  [{date_dashed}] 🔬 跑 Reflector 覆盤 ({display})...")
    cmd_ref = ["python3", REFLECTOR_PATH, target_folder, "--skip-backtest"]
    try:
        result = subprocess.run(cmd_ref, env=env, timeout=300)
        if result.returncode != 0:
            print(f"  ⚠️ Reflector returncode={result.returncode}")
    except subprocess.TimeoutExpired:
        print(f"  ⏱️ Reflector timeout")
    except Exception as e:
        print(f"  ❌ Reflector failed: {e}")

    print(f"  [{date_dashed}] ✅ {display} 處理完畢！")
    return True


def main():
    print("=" * 70)
    print("AU Wong Choi - 全季批量爬蟲 v2 (Tier 1 + Tier 2)")
    print(f"掃描範圍: {START_DATE} 至 {END_DATE}")
    print(f"Tracks ({len(TRACKS)}): {', '.join(TRACKS)}")
    print("=" * 70)

    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    # Iterate from most recent to oldest (catch up first)
    current_date = END_DATE
    total_processed = 0
    total_skipped = 0
    consecutive_failures = 0

    while current_date >= START_DATE:
        date_dashed = current_date.strftime("%Y-%m-%d")
        date_compact = current_date.strftime("%Y%m%d")

        # Check each tier 1/2 track for this date
        found_tracks = []
        for slug in TRACKS:
            if check_track_on_date(slug, current_date):
                found_tracks.append(slug)
            time.sleep(random.uniform(*SLEEP_BETWEEN_TRACK_CHECKS))

        if found_tracks:
            display_list = [SLUG_TO_DISPLAY.get(t, t) for t in found_tracks]
            print(f"\n>> [{date_dashed}] 發現賽事: {', '.join(display_list)}")
            for slug in found_tracks:
                try:
                    if process_meeting(slug, current_date):
                        total_processed += 1
                        consecutive_failures = 0
                    else:
                        total_skipped += 1
                except Exception as e:
                    print(f"  ❌ Process error: {e}")
                    consecutive_failures += 1

                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    print(f"\n⚠️ 連續 {MAX_CONSECUTIVE_FAILURES} 次失敗，長休眠避免被封鎖...")
                    time.sleep(300)
                    consecutive_failures = 0
                else:
                    sleep_time = random.uniform(*SLEEP_BETWEEN_MEETINGS)
                    print(f"  💤 等待 {sleep_time:.1f} 秒避免被封鎖...")
                    time.sleep(sleep_time)
        else:
            # No racing at this venue on this date - quick sleep
            time.sleep(random.uniform(0.3, 0.8))

        current_date -= datetime.timedelta(days=1)

    print("=" * 70)
    print(f"全部完成！新處理: {total_processed} 個賽馬日，跳過: {total_skipped}")
    print("=" * 70)


if __name__ == "__main__":
    main()
