import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from bs4 import BeautifulSoup

with open('./.agents/skills/au_race_extractor/scripts/racenet_print_curl.html', 'r') as f:
    text = f.read()

soup = BeautifulSoup(text, 'html.parser')

details = soup.find('div', class_='racing-full-form-details')
if details:
    # Print all stripped strings in this block to see if past runs exist here
    strings = list(details.stripped_strings)
    print("Found", len(strings), "strings in racing-full-form-details.")
    print("Beginning strings:", strings[:20])
    print("\nEnd strings:", strings[-20:])
    
    # Are there other racing-full-form-details?
    all_details = soup.find_all('div', class_='racing-full-form-details')
    print(f"\nTotal racing-full-form-details blocks: {len(all_details)}")
    
    # Let's find "1st/6" or something like that, which represents a past run
    # E.g., we know "4th/9 1200m 27 Weeks PAKS" is a recent run for Absolute Power
    runs = soup.find_all(string=lambda s: s and '4th/9' in s)
    for r in runs:
        print(f"\nFound past run string: {r.strip()}")
        p = r.parent
        for _ in range(5):
            if p:
                print(f"Parent: {p.name} class={p.get('class')}")
                p = p.parent
