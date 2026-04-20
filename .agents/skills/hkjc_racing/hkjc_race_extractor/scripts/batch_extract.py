#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
Batch extraction script for HKJC race data.
Extracts racecard + formguide for multiple races concurrently,
plus the starter PDF (once per meeting).

Usage:
    python batch_extract.py --base_url "https://racing.hkjc.com/zh-hk/local/information/racecard?racedate=2026/03/04&Racecourse=HV&RaceNo=1" --races 1-9 --output_dir "/path/to/output"

Arguments:
    --base_url: Any racecard URL from the meeting (used to derive date and racecourse)
    --races: Race range (e.g., "1-9" or "1,3,5" or "1")
    --output_dir: Target folder for output files
"""
import re
import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs

# Paths to existing extraction scripts
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
# Cross-platform venv detection
import platform as _platform
_venv_base = os.path.join(SKILL_DIR, '..', 'venv')
if _platform.system() == 'Windows':
    _venv_win = os.path.join(_venv_base, 'Scripts', 'python.exe')
    VENV_PYTHON = _venv_win if os.path.isfile(_venv_win) else sys.executable
else:
    _venv_unix = os.path.join(_venv_base, 'bin', 'python')
    VENV_PYTHON = _venv_unix if os.path.isfile(_venv_unix) else sys.executable
RACECARD_SCRIPT = os.path.join(SKILL_DIR, 'extract_racecard.py')
FORMGUIDE_SCRIPT = os.path.join(SKILL_DIR, 'extract_formguide_playwright.py')
STARTER_PDF_SCRIPT = os.path.join(SKILL_DIR, 'extract_starter_pdf.py')

# Force UTF-8 for child subprocess output (prevents garbled Chinese on non-macOS systems)
SUBPROCESS_ENV = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}



def parse_races(race_str):
    """Parse race specification like '1-9' or '1,3,5' or '1'"""
    races = []
    for part in race_str.split(','):
        part = part.strip()
        if '-' in part:
            start, end = part.split('-')
            races.extend(range(int(start), int(end) + 1))
        else:
            races.append(int(part))
    return sorted(set(races))


def derive_urls(base_url, race_no):
    """Derive racecard and formguide URLs for a given race number."""
    parsed = urlparse(base_url)
    qs = parse_qs(parsed.query)
    date = qs.get('racedate', [''])[0]
    course = qs.get('Racecourse', [''])[0]

    racecard_url = f"https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={date}&Racecourse={course}&RaceNo={race_no}"
    formguide_url = f"https://racing.hkjc.com/zh-hk/local/info/speedpro/formguide?racedate={date}&Racecourse={course}&RaceNo={race_no}"
    return racecard_url, formguide_url


def extract_single_race(race_no, base_url, output_dir, date_prefix):
    """Extract racecard + formguide for a single race."""
    racecard_url, formguide_url = derive_urls(base_url, race_no)
    results = {'race': race_no, 'racecard_ok': False, 'formguide_ok': False, 'errors': []}

    # Racecard
    rc_file = os.path.join(output_dir, f"{date_prefix} Race {race_no} 排位表.md")
    try:
        rc_result = subprocess.run(
            [VENV_PYTHON, RACECARD_SCRIPT, racecard_url],
            capture_output=True, text=True, timeout=60,
            encoding='utf-8', env=SUBPROCESS_ENV
        )
        with open(rc_file, 'w', encoding='utf-8') as f:
            f.write(rc_result.stdout)
        if rc_result.returncode == 0:
            results['racecard_ok'] = True
        else:
            results['errors'].append(f"Racecard R{race_no}: {rc_result.stderr[:200]}")
    except Exception as e:
        results['errors'].append(f"Racecard R{race_no}: {str(e)}")

    # Formguide
    fg_file = os.path.join(output_dir, f"{date_prefix} Race {race_no} 賽績.md")
    try:
        fg_result = subprocess.run(
            [VENV_PYTHON, FORMGUIDE_SCRIPT, formguide_url],
            capture_output=True, text=True, timeout=120,
            encoding='utf-8', env=SUBPROCESS_ENV
        )
        # Filter out the "Extracting form guide" log line
        lines = fg_result.stdout.splitlines(keepends=True)
        filtered = [l for l in lines if "Extracting form guide using Playwright" not in l]
        with open(fg_file, 'w', encoding='utf-8') as f:
            f.writelines(filtered)
        if fg_result.returncode == 0:
            results['formguide_ok'] = True
        else:
            results['errors'].append(f"Formguide R{race_no}: {fg_result.stderr[:200]}")
    except Exception as e:
        results['errors'].append(f"Formguide R{race_no}: {str(e)}")

    # Post-extraction content validation
    for filepath, label, key in [(rc_file, 'Racecard', 'racecard_ok'), (fg_file, 'Formguide', 'formguide_ok')]:
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            if size < 100:
                results['errors'].append(f"{label} R{race_no}: Output file suspiciously small ({size} bytes) — likely extraction failure")
                results[key] = False
            else:
                # Check for error content explicitly
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    first_line = content.strip().split('\n')[0] if content.strip() else ''
                    
                    if first_line.startswith('Error:'):
                        results['errors'].append(f"{label} R{race_no}: Output contains error message: {first_line[:100]}")
                        results[key] = False
                    elif "Could not find racecard table" in content or "沒有賽績紀錄" in content:
                        results['errors'].append(f"{label} R{race_no}: Empty or invalid HKJC table detected.")
                        results[key] = False
                except Exception:
                    pass

    return results


def extract_starter_pdf(date_yyyymmdd, output_dir, date_prefix):
    """Extract the starter PDF (once per meeting)."""
    pdf_file = os.path.join(output_dir, f"{date_prefix} 全日出賽馬匹資料 (PDF).md")
    try:
        result = subprocess.run(
            [VENV_PYTHON, STARTER_PDF_SCRIPT, date_yyyymmdd],
            capture_output=True, text=True, timeout=90,
            encoding='utf-8', env=SUBPROCESS_ENV
        )
        with open(pdf_file, 'w', encoding='utf-8') as f:
            f.write(result.stdout)
        # Validate PDF output content
        if result.returncode != 0:
            return False, result.stderr[:200]
        file_size = os.path.getsize(pdf_file)
        if file_size < 100:
            return False, f"PDF output file too small ({file_size} bytes) — extraction likely failed"
        # Check if output is just an error message
        first_line = result.stdout.strip().split('\n')[0] if result.stdout.strip() else ''
        if first_line.startswith('Error:'):
            return False, f"PDF script wrote error to stdout: {first_line[:100]}"
        return True, ""
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="Batch extract HKJC race data")
    parser.add_argument("--base_url", required=True, help="Any racecard URL from the meeting")
    parser.add_argument("--races", required=True, help="Race range: '1-9' or '1,3,5' or '1'")
    parser.add_argument("--output_dir", required=True, help="Target output folder")
    parser.add_argument("--max_workers", type=int, default=3, help="Max concurrent extractions (default: 3)")
    args = parser.parse_args()

    # Parse inputs
    races = parse_races(args.races)
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    # Derive date info from URL — fail-fast on missing/malformed racedate
    parsed = urlparse(args.base_url)
    qs = parse_qs(parsed.query)
    date_raw = qs.get('racedate', [''])[0]  # e.g., "2026/03/04"
    date_parts = date_raw.split('/')
    if len(date_parts) != 3 or not all(date_parts):
        print(f"❌ FATAL: Invalid or missing 'racedate' in URL: '{date_raw}'")
        print(f"   Expected format: YYYY/MM/DD (e.g., 2026/03/25)")
        print(f"   Full URL: {args.base_url}")
        sys.exit(1)
    date_yyyymmdd = ''.join(date_parts)  # "20260304"
    if len(date_yyyymmdd) != 8 or not date_yyyymmdd.isdigit():
        print(f"❌ FATAL: Date failed numeric validation: '{date_yyyymmdd}' (from '{date_raw}')")
        sys.exit(1)
    date_prefix = f"{date_parts[1]}-{date_parts[2]}"

    print(f"🏇 HKJC Batch Extraction")
    print(f"   Races: {races}")
    print(f"   Output: {output_dir}")
    print(f"   Date: {date_raw}")
    print()

    # Step 1: Extract starter PDF (once)
    print(f"📄 Extracting starter PDF...")
    pdf_ok, pdf_err = extract_starter_pdf(date_yyyymmdd, output_dir, date_prefix)
    if pdf_ok:
        print(f"   ✅ Starter PDF saved")
    else:
        print(f"   ❌ Starter PDF failed: {pdf_err}")
        print(f"   🚨 [Fast-Fail] PDF is required for accurate analysis. Aborting batch extraction to conserve resources.")
        sys.exit(1)
    print()

    # Step 2: Extract all races concurrently
    print(f"🔄 Extracting {len(races)} races (max {args.max_workers} concurrent)...")
    all_results = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {
            executor.submit(extract_single_race, r, args.base_url, output_dir, date_prefix): r
            for r in races
        }
        for future in as_completed(futures):
            result = future.result()
            all_results.append(result)
            race = result['race']
            rc = "✅" if result['racecard_ok'] else "❌"
            fg = "✅" if result['formguide_ok'] else "❌"
            print(f"   Race {race}: Racecard {rc} | Formguide {fg}")
            for err in result['errors']:
                print(f"      ⚠️ {err}")

    # Summary
    all_results.sort(key=lambda x: x['race'])
    total_rc = sum(1 for r in all_results if r['racecard_ok'])
    total_fg = sum(1 for r in all_results if r['formguide_ok'])
    print()
    print(f"📊 Summary: {total_rc}/{len(races)} racecards | {total_fg}/{len(races)} formguides")
    if pdf_ok:
        print(f"   ✅ Starter PDF: OK")
    print(f"   📁 All files saved to: {output_dir}")


if __name__ == "__main__":
    main()
