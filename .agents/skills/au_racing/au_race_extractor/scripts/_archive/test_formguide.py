import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from bs4 import BeautifulSoup
import re

with open('./.agents/skills/au_race_extractor/scripts/racenet_print_curl.html', 'r') as f:
    text = f.read()

soup = BeautifulSoup(text, 'html.parser')

print("Searching for form guides...")
# Search past runs based on the structure we saw in text:
# e.g., <div class="racing-full-form-details"> 
details = soup.find_all('div', class_='racing-full-form-details')
print(f"Found {len(details)} racing-full-form-details")

if details:
    # A single horse's detail block
    for i, detail in enumerate(details[:2]): # Just look at the first two
        # The form guide itself might be in another div next to it or inside
        # Usually each past run has a class like 'past-run', 'horse-form-run', or maybe simply table rows 
        # Let's dump all text of the parent container to see what it looks like
        parent = detail.parent
        runs_texts = parent.get_text(" | ", strip=True)
        print(f"Horse {i} Parent Text Start: {runs_texts[:200]}")
        
        # Are there table rows?
        trs = parent.find_all('tr')
        print(f"Found {len(trs)} table rows inside this horse's details.")
        for tr in trs[:3]:
            print(f"  Row: {tr.get_text(' ', strip=True)}")
