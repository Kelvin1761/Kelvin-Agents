import os
import json
import subprocess
import time
from datetime import datetime

# 2024/2025 dates (Forward order)
DATES_2425 = [
    '01/09/2024', '08/09/2024', '11/09/2024', '14/09/2024', '15/09/2024', '18/09/2024', '22/09/2024', '25/09/2024', '28/09/2024', '29/09/2024',
    '01/10/2024', '06/10/2024', '09/10/2024', '13/10/2024', '16/10/2024', '19/10/2024', '20/10/2024', '23/10/2024', '27/10/2024', '30/10/2024',
    '02/11/2024', '03/11/2024', '05/11/2024', '06/11/2024', '09/11/2024', '10/11/2024', '13/11/2024', '17/11/2024', '20/11/2024', '24/11/2024', '27/11/2024'
]

EXTRACTOR_PATH = os.path.abspath('.agents/skills/hkjc_racing/hkjc_race_extractor/scripts/fast_extract_results.py')

def process_date(date_str):
    day, month, year = date_str.split('/')
    formatted_date = f'{year}/{month}/{day}'
    season_dir = 'archive race analysis/hkjc results 2024 25'
    output_dir = os.path.join(season_dir, f'{year}-{month}-{day}')
    os.makedirs(output_dir, exist_ok=True)
    
    for venue in ['ST', 'HV']:
        print(f'>> [24/25 Sync] {formatted_date} {venue}...')
        subprocess.run(['python', EXTRACTOR_PATH, '--date', formatted_date, '--venue', venue, '--races', '1-12', '--output_dir', output_dir])

if __name__ == '__main__':
    for d in DATES_2425:
        process_date(d)
        time.sleep(0.2)
