import os
import sys
import json
import subprocess
import time
import re
from pathlib import Path

# Config
PYTHON = sys.executable
PROJECT_ROOT = Path(__file__).resolve().parents[5]
import sys as _sys; _sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import AU_RACING
ORCHESTRATOR = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi" / "scripts" / "au_orchestrator.py"
RESULTS_CLAWER = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "claw_racenet_results.py"
ARCHIVE_DIR = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "archive race analysis"
OLD_ARCHIVE_DIR = AU_RACING

def run_command(cmd, cwd=PROJECT_ROOT):
    print(f"🚀 Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, text=True)
    return result.returncode == 0

def get_form_guide_entry(results_url):
    """Run claw_racenet_results.py to get JSON data and extract slugs."""
    print(f"🕵️ Using claw_racenet_results.py to discover slugs for {results_url}...")
    try:
        # Run claw_racenet_results.py with --json
        cmd = [PYTHON, ".agents/skills/au_racing/claw_racenet_results.py", "--url", results_url, "--json"]
        subprocess.run(cmd, check=True, capture_output=True)
        
        # Find the JSON file created (it follows a pattern)
        # Race_Results_Venue_YYYY-MM-DD.json
        # But we can also just look for any .json in current dir or temporary files if we modify it
        # For now, let's look for the JSON file based on the meeting slug
        meeting_slug_part = results_url.split('/')[-2] # e.g. randwick-20260425
        # Find json file containing this slug
        import glob
        json_files = glob.glob(f"Race_Results_*{meeting_slug_part[:8]}*.json") # Match date part
        if not json_files:
            # Fallback to broad search
            json_files = glob.glob("Race_Results_*.json")
            
        if json_files:
            latest_json = max(json_files, key=os.path.getmtime)
            with open(latest_json, 'r') as f:
                data = json.load(f)
                meeting_slug = data['meeting']['slug']
                # Get the first race slug
                first_race_key = sorted(data['events'].keys(), key=int)[0]
                race_slug = data['events'][first_race_key]['slug']
                return f"https://www.racenet.com.au/form-guide/horse-racing/{meeting_slug}/{race_slug}/overview"
    except Exception as e:
        print(f"  ⚠️ Discovery error via clawer: {e}")
    return None

def process_meeting(meeting):
    results_url = meeting['url']
    
    print(f"\n--- 🏇 Processing {meeting['track']} ({meeting['date']}) ---")
    
    # Discovery valid form-guide entry point
    form_guide_url = get_form_guide_entry(results_url)
    if not form_guide_url:
        print(f"❌ Could not find form-guide entry for {results_url}")
        return False
        
    print(f"✅ Found entry: {form_guide_url}")
    
    # 1. Run Orchestrator
    if not run_command([PYTHON, str(ORCHESTRATOR), form_guide_url, "--auto"]):
        print(f"❌ Orchestrator failed for {meeting['date']}")
        return False
    
    # 2. Locate the generated directory
    # Pattern: YYYY-MM-DD Venue...
    venue_name = meeting['track'].replace("-", " ").title()
    date_str = meeting['date']
    meeting_dir = None
    for p in PROJECT_ROOT.iterdir():
        if p.is_dir() and p.name.startswith(date_str) and venue_name in p.name:
            meeting_dir = p
            break
    
    if not meeting_dir:
        print(f"❌ Could not find directory for {date_str} {venue_name}")
        return False
        
    print(f"📂 Found meeting dir: {meeting_dir}")
    
    # 3. Run Results Clawer to get the outcomes
    if not run_command([PYTHON, str(RESULTS_CLAWER), results_url]):
        print(f"❌ Results clawer failed for {meeting['date']}")
    else:
        # Move result file if it exists
        res_file = PROJECT_ROOT / "Race_Results_Reflector.md"
        if res_file.exists():
            target_path = meeting_dir / "Race_Results_Reflector.md"
            res_file.replace(target_path)
            print(f"✅ Saved results to {target_path}")

    # 4. Move entire directory to ARCHIVE_DIR
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    archive_path = ARCHIVE_DIR / meeting_dir.name
    if archive_path.exists():
        import shutil
        shutil.rmtree(archive_path)
    
    meeting_dir.rename(archive_path)
    print(f"📦 Archived to: {archive_path}")

    return True

def main():
    json_path = PROJECT_ROOT / ".scratch" / "discovered_meetings.json"
    if not json_path.exists():
        print(f"❌ Missing {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        meetings = json.load(f)

    print(f"📋 Loaded {len(meetings)} meetings. Starting batch process...")
    
    consecutive_failures = 0
    max_failures = 3
    
    for i, meeting in enumerate(meetings):
        # Check if already archived
        venue_name = meeting['track'].replace("-", " ").title()
        date_str = meeting['date']
        is_done = False
        
        # Check both new and old archive dirs
        for adir in [ARCHIVE_DIR, OLD_ARCHIVE_DIR]:
            if not adir.exists(): continue
            for p in adir.iterdir():
                if p.is_dir() and p.name.startswith(date_str) and venue_name in p.name:
                    print(f"⏩ Skipping {date_str} {venue_name} (Already in {adir.name})")
                    is_done = True
                    break
            if is_done: break
            
        if is_done: continue

        print(f"\n[{i+1}/{len(meetings)}] 🏁 Processing: {date_str} {venue_name}")
        if process_meeting(meeting):
            print(f"✅ Finished: {date_str} {venue_name}")
            consecutive_failures = 0
            print("😴 Cooling down (10s)...")
            time.sleep(10)
        else:
            print(f"❌ Failed: {date_str} {venue_name}")
            consecutive_failures += 1
            with open("failed_meetings.log", "a") as f:
                f.write(f"{date_str} {venue_name} {meeting['url']}\n")
            
            if consecutive_failures >= max_failures:
                print(f"🛑 CIRCUIT BREAKER: {max_failures} consecutive failures. Stopping to protect IP.")
                break

if __name__ == "__main__":
    main()
