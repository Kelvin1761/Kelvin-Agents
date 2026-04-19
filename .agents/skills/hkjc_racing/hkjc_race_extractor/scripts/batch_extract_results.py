#!/usr/bin/env python3
os.environ.setdefault('PYTHONUTF8', '1')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
Batch extraction script for HKJC race results.
Extracts results for multiple races using Lightpanda headless browser.

Usage:
    python batch_extract_results.py --base_url "URL" --races "1-9" --output_dir "/path/to/output"
"""
import os
import sys
import re
import argparse
import subprocess
from urllib.parse import urlparse, parse_qs

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(SKILL_DIR, '..', 'venv', 'bin', 'python')
RESULT_SCRIPT = os.path.join(SKILL_DIR, 'extract_results.py')
PROJECT_ROOT = os.path.abspath(os.path.join(SKILL_DIR, '..', '..', '..', '..', '..'))

# Import lightpanda_utils
sys.path.insert(0, PROJECT_ROOT)
from lightpanda_utils import start_lightpanda, stop_lightpanda

def derive_url(base_url, race_no):
    parsed = urlparse(base_url)
    qs = parse_qs(parsed.query)
    date = qs.get('racedate', [''])[0]
    course = qs.get('Racecourse', [''])[0]
    return f"https://racing.hkjc.com/zh-hk/local/information/localresults?racedate={date}&Racecourse={course}&RaceNo={race_no}"

def extract_single(race_no, base_url, env):
    url = derive_url(base_url, race_no)
    try:
        res = subprocess.run([VENV_PYTHON, RESULT_SCRIPT, url], capture_output=True, text=True, timeout=120, env=env)
        return race_no, res.stdout, res.stderr
    except Exception as e:
        return race_no, "", str(e)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base_url", required=True)
    parser.add_argument("--races", required=True)
    parser.add_argument("--output_dir", required=True)
    args = parser.parse_args()

    # Parse races
    r_matches = re.match(r'(\d+)-(\d+)', args.races)
    if r_matches:
        race_list = list(range(int(r_matches.group(1)), int(r_matches.group(2)) + 1))
    else:
        race_list = [int(r.strip()) for r in args.races.split(',')]

    os.makedirs(args.output_dir, exist_ok=True)
    
    # Extract date/course for filename
    parsed = urlparse(args.base_url)
    qs = parse_qs(parsed.query)
    date_raw = qs.get('racedate', [''])[0]
    course = qs.get('Racecourse', ['ST'])[0]
    course_cn = '沙田' if course == 'ST' else '跑馬地'
    date_parts = date_raw.split('/')
    date_prefix = f"{date_parts[1]}-{date_parts[2]}" if len(date_parts) == 3 else "00-00"

    print(f"🏇 Batching results for {date_raw} {course_cn}...")
    
    # Start Lightpanda once for all races
    use_lp, lp_proc = start_lightpanda(PROJECT_ROOT)
    
    # Prepare env with CDP URL for child processes
    env = os.environ.copy()
    if use_lp:
        env['LIGHTPANDA_CDP_URL'] = 'http://127.0.0.1:9222'
        print("  ✓ Lightpanda server started. Child processes will connect via CDP.")
    
    results = {}
    try:
        # Sequential extraction to avoid CDP concurrency issues
        for race_no in race_list:
            rno, out, err = extract_single(race_no, args.base_url, env)
            if out.strip():
                results[rno] = out
                print(f"   ✅ Race {rno} extracted")
            else:
                print(f"   ❌ Race {rno} failed: {err}")
    finally:
        stop_lightpanda(lp_proc)

    output_file = os.path.join(args.output_dir, f"{date_prefix} {course_cn} 全日賽果.md")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"HKJC 賽果報告\n日期: {date_raw} | 馬場: {course_cn}\n\n")
        for rno in sorted(results.keys()):
            f.write(results[rno])
            f.write("\n\n")
    
    print(f"📊 Results saved to: {output_file}")

if __name__ == "__main__":
    main()
