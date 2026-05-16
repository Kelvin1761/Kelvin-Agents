import os
import json
import datetime
import subprocess
import time
import sys

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def get_all_potential_dates(start_year, end_year):
    dates = []
    start_date = datetime.date(start_year, 9, 1)
    end_date = datetime.date(end_year, 7, 31)
    
    curr = start_date
    while curr <= end_date:
        if curr.weekday() in [2, 5, 6]:
            dates.append(curr.strftime('%Y-%m-%d'))
        curr += datetime.timedelta(days=1)
    return dates

def run_extraction():
    dates_24_25 = get_all_potential_dates(2024, 2025)
    dates_25_26 = get_all_potential_dates(2025, 2026)
    
    tasks = []
    for d in dates_24_25: tasks.append((d, 'archive race analysis/hkjc results 2024 25'))
    for d in dates_25_26: tasks.append((d, 'archive race analysis/hkjc results 2025 26'))
    
    print(f"Total potential race dates: {len(tasks)}", flush=True)
    
    for date, base_path in tasks:
        day_dir = os.path.join(base_path, date)
        # Check if deep data exists
        json_path = None
        if os.path.exists(day_dir):
            for f in os.listdir(day_dir):
                if f.endswith('_賽果.json') or f.endswith('_全日賽果.json'):
                    json_path = os.path.join(day_dir, f)
                    break
        
        if json_path:
            with open(json_path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    if data and '1' in data and 'sectional_times' in data['1'] and data['1']['sectional_times']:
                        continue
                except: pass

        print(f"\n🚀 Extracting: {date}", flush=True)
        # QUOTE THE PATH for spaces!
        output_file = os.path.join(day_dir, f"{date[-5:]}_賽果.json")
        
        # Use shlex.quote or just wrap in double quotes
        cmd = f'python .agents/skills/hkjc_racing/hkjc_race_extractor/scripts/fast_extract_results.py "{date}" "UNKNOWN" "{output_file}"'
        try:
            subprocess.run(cmd, shell=True, env=dict(os.environ, PYTHONUTF8="1"))
        except Exception as e:
            print(f"Error {date}: {e}", flush=True)

    print("\n🏁 Race extraction complete. Starting Horse DB Sync...", flush=True)
    subprocess.run("python scratch/build_horse_db.py", shell=True, env=dict(os.environ, PYTHONUTF8="1"))

if __name__ == '__main__':
    run_extraction()
