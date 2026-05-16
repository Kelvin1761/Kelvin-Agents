import os
import subprocess
import time
import json
from datetime import datetime

EXTRACTOR_PATH = '.agents/skills/hkjc_racing/hkjc_race_extractor/scripts/fast_extract_results.py'
OUTPUT_BASE = 'archive race analysis/hkjc results 2025 26'
DELAY = 1.0

RAW_DATES = [
    '07/09/2025', '10/09/2025', '13/09/2025', '14/09/2025', '17/09/2025', '21/09/2025', '25/09/2025', '28/09/2025', '01/10/2025', '04/10/2025', '05/10/2025', '08/10/2025', '11/10/2025', '12/10/2025', '15/10/2025', '18/10/2025', '19/10/2025', '22/10/2025', '25/10/2025', '26/10/2025', '30/10/2025', '01/11/2025', '02/11/2025', '04/11/2025', '05/11/2025', '08/11/2025', '09/11/2025', '12/11/2025', '15/11/2025', '16/11/2025', '19/11/2025', '23/11/2025', '26/11/2025', '30/11/2025', '03/12/2025', '07/12/2025', '10/12/2025', '14/12/2025', '17/12/2025', '20/12/2025', '23/12/2025', '27/12/2025', '28/12/2025', '01/01/2026', '04/01/2026', '07/01/2026', '10/01/2026', '11/01/2026', '14/01/2026', '18/01/2026', '21/01/2026', '25/01/2026', '28/01/2026', '01/02/2026', '04/02/2026', '07/02/2026', '08/02/2026', '11/02/2026', '14/02/2026', '15/02/2026', '18/02/2026', '22/02/2026', '25/02/2026', '01/03/2026', '04/03/2026', '07/03/2026', '08/03/2026', '11/03/2026', '15/03/2026', '18/03/2026', '22/03/2026', '25/03/2026', '29/03/2026', '01/04/2026', '05/04/2026', '06/04/2026', '08/04/2026', '12/04/2026', '13/04/2026', '15/04/2026', '19/04/2026', '22/04/2026', '26/04/2026', '29/04/2026', '03/05/2026', '06/05/2026', '10/05/2026'
]

def extract_meeting(date_str, venue):
    try:
        d = datetime.strptime(date_str, '%d/%m/%Y')
        dir_name = f"{d.year}-{d.month:02d}-{d.day:02d}"
        meeting_dir = os.path.join(OUTPUT_BASE, dir_name)
        os.makedirs(meeting_dir, exist_ok=True)
        
        venue_name = "\u8dd1\u99ac\u5730" if venue == "HV" else "\u6c99\u7530"
        target_name = f"{d.month:02d}-{d.year}_{venue_name}_\u5168\u65e5\u8cfd\u679c.json"
        target_path = os.path.join(meeting_dir, target_name)
        
        if os.path.exists(target_path):
            with open(target_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if len(data) > 0:
                    return True
        
        print(f"Extracting {date_str} at {venue}...")
        cmd = [
            'python', EXTRACTOR_PATH,
            '--date', date_str,
            '--venue', venue,
            '--races', '1-12',
            '--output_dir', meeting_dir
        ]
        # Use env with UTF-8
        env = os.environ.copy()
        env['PYTHONUTF8'] = '1'
        subprocess.run(cmd, env=env)
        
        if os.path.exists(target_path):
            with open(target_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if len(data) > 0:
                    print(f"  Success: {venue}")
                    return True
        return False
    except Exception as e:
        print(f"  Error for {date_str} {venue}: {e}")
        return False

if __name__ == "__main__":
    print("Starting HKJC Venue Recovery (ST + HV)...")
    success_count = 0
    for date in RAW_DATES:
        # Try both venues. One will likely fail (empty or error) and one will succeed.
        # This ensures we get ST for ST days and HV for HV days.
        s_st = extract_meeting(date, 'ST')
        s_hv = extract_meeting(date, 'HV')
        if s_st or s_hv:
            success_count += 1
        time.sleep(DELAY)
    print(f"Done. Meetings covered: {success_count}/{len(RAW_DATES)}")
