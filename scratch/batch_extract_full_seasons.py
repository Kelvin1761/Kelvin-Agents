import os
import json
import subprocess
import time
from datetime import datetime

DATES_PATH = 'scratch/all_hkjc_dates.json'
CACHE_PATH = 'scratch/horse_metadata_cache.json'
EXTRACTOR_PATH = '.agents/skills/hkjc_racing/hkjc_race_extractor/scripts/fast_extract_results.py'
BASE_DIR = 'archive race analysis'

def load_json(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    return [] if 'dates' in path else {}

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def run_extraction():
    dates = load_json(DATES_PATH)
    if not dates:
        print("Error: No dates found in scratch/all_hkjc_dates.json")
        return
    
    print(f"Total dates to process: {len(dates)}")
    
    for date_str in dates:
        # Determine season folder
        # date_str format: "DD/MM/YYYY"
        try:
            day, month, year = date_str.split('/')
            # Season break is typically July
            season = "2024 25" if (int(year) == 2024 or (int(year) == 2025 and int(month) <= 7)) else "2025 26"
            
            out_dir = os.path.join(BASE_DIR, f"hkjc results {season}", f"{year}-{month}-{day}")
            out_file = os.path.join(out_dir, "full_day_results.json")
            
            # For extraction, we need YYYY-MM-DD for the extractor script's URL logic
            formatted_date_for_url = f"{year}-{month}-{day}"
            
            # CLEANUP: If there are old files with different names in this folder, we should remove them or skip if the new one exists
            # This handles the "duplicated race results" issue
            if os.path.exists(out_dir):
                old_files = [f for f in os.listdir(out_dir) if f.endswith('.json') and f != "full_day_results.json"]
                for old_f in old_files:
                    try:
                        os.remove(os.path.join(out_dir, old_f))
                        print(f"Removed duplicated old file: {old_f}")
                    except: pass

            # if os.path.exists(out_file):
            #     # Check if it's a recent extraction or needs upgrade
            #     # For now, if user said "duplicated", we might want to re-run or just skip
            #     # Let's re-run if it's smaller than a certain size or just skip if it's there
            #     print(f"Skipping {date_str} (full_day_results.json already exists)")
            #     continue
                
            print(f"\n>>> Processing {date_str} (Season {season})")
            # Usage: python fast_extract_results.py <racedate> <output_path> [venue]
            # Venue is hard to know before extraction, so we let the script handle it or use "Auto"
            cmd = f'python {EXTRACTOR_PATH} {formatted_date_for_url} "{out_file}"'
            
            subprocess.run(cmd, shell=True, check=True, env={**os.environ, "PYTHONUTF8": "1"})
            
            # Respectful delay
            time.sleep(2)
            
        except Exception as e:
            print(f"Error processing {date_str}: {e}")
            continue

if __name__ == '__main__':
    run_extraction()

