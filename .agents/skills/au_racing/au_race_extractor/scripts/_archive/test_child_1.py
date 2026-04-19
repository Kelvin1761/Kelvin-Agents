import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from bs4 import BeautifulSoup

with open('./.agents/skills/au_race_extractor/scripts/racenet_print_curl.html', 'r') as f:
    text = f.read()

soup = BeautifulSoup(text, 'html.parser')

stats = soup.find('div', class_='print-form__stats')
if stats:
    divs = stats.find_all('div', recursive=False)
    if len(divs) > 1:
        child = divs[1]
        print("Child 1 found.")
        
        # Let's find trs or divs that look like table rows
        rows = child.find_all('tr')
        if rows:
            print(f"Found {len(rows)} table rows!")
            for i, r in enumerate(rows[:3]):
                print(f"  Row {i}: {r.get_text(' | ', strip=True)[:100]}")
        else:
            print("No tr found. Looking for divs with text containing '1200m' or something similar...")
            # Let's find divs with many children, or grids
            past_runs = child.find_all('div', class_=lambda x: x and ('table' in x or 'row' in x or 'run' in x))
            print(f"Found {len(past_runs)} possible past run dicts.")
            for i, pr in enumerate(past_runs[:5]):
                print(f"  Class: {pr.get('class')} | Text: {pr.get_text(' | ', strip=True)[:150]}")
