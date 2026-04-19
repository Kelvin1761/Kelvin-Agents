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

print("Looking for Absolute Power's form:")
for name_tag in soup.find_all(string=re.compile("1. Absolute Power")):
    # Try finding the next big container that looks like past runs
    p = name_tag.parent
    for _ in range(5):
        if not p: break
        # Try to find date strings like "2023", or elements with class 'past-run'
        past_runs = p.find_all('div', class_=re.compile('past-run|horse-form|row'))
        if past_runs:
            print(f"Parent <{p.name} class='{p.get('class')}'> has {len(past_runs)} possible past runs.")
            for pr in past_runs[:2]:
                print(f"  Run: {pr.get_text(' | ', strip=True)[:200]}")
            break
        p = p.parent

    # Try finding sibling containers
    p2 = name_tag.find_parent('div', class_='event-selection-row-container')
    print("Event row container found:", bool(p2))
    if p2:
        ns = p2.find_next_sibling('div')
        if ns:
            print(f"Next Sibling to horse row: classes={ns.get('class')}")
            # print first 500 chars of text
            print("Text:", ns.get_text(" | ", strip=True)[:500])
