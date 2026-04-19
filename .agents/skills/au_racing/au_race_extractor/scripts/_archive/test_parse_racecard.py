import os
os.environ.setdefault('PYTHONUTF8', '1')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from bs4 import BeautifulSoup
import re
import sys

def parse_html(filepath):
    with open(filepath, 'r') as f:
        text = f.read()

    soup = BeautifulSoup(text, 'html.parser')

    print("Searching for race containers...")
    races = soup.find_all('div', class_=re.compile('form-guide-page__overview'))
    print(f"Found {len(races)} races in print HTML.")

    for race in races[:1]: # just look at first race
        header = race.find('h2', class_='event-header__event-name')
        if header:
            print(f"--- RACE: {header.get_text(strip=True)} ---")
        else:
            print("--- RACE HEADER NOT FOUND ---")
            
        # Horses are typically inside event-selection-row-container
        boxes = race.find_all('div', class_='event-selection-row-container')
        print(f"Found {len(boxes)} horses.")

        for box in boxes[:1]: 
            desktop_row = box.find('div', class_='selection-row-desktop')
            if not desktop_row: 
                print("No desktop row")
                continue

            name_el = desktop_row.find('a', class_='horseracing-selection-details-name')
            name = name_el.get_text(strip=True) if name_el else "Unknown"
            
            # The barrier is inside a small tag
            barrier_el = desktop_row.find('small', class_='competior-meta-info')
            barrier = ""
            if barrier_el:
                span = barrier_el.find('span')
                barrier = span.get_text(strip=True) if span else ""

            # Trainer and Jockey
            trainer = "T: Unknown"
            jockey = "J: Unknown"
            t_el = desktop_row.find('span', string="T: ")
            if t_el and t_el.parent:
                trainer = t_el.parent.get_text(" ", strip=True)
            j_el = desktop_row.find('span', string="J: ")
            if j_el and j_el.parent:
                jockey = j_el.parent.get_text(" ", strip=True)

            print(f"Horse: {name} {barrier} | {trainer} | {jockey}")
            
            # Check right columns
            right_cols = desktop_row.find_all('div', class_=re.compile('event-selection-row-right__column'))
            col_texts = [c.get_text(" ", strip=True) for c in right_cols]
            print(f"Columns: {col_texts}")
            
            # Find the form guide table for this horse
            ns = box.find_next_sibling('div')
            if ns and 'print' in (ns.get('class') or []):
                print(f"Found print details block! Classes: {ns.get('class')}")
                runs = ns.find_all('div', class_=re.compile('past-run|horse-form'))
                if not runs:
                    runs = ns.find_all('div', class_=re.compile('form-guide-horse__past-run'))
                if not runs:
                    # let's just count all divs inside
                    runs = len(ns.find_all('div'))
                    print(f"Didn't find past-run classes, but found {runs} total divs inside print block.")
                else:
                    print(f"Found {len(runs)} past runs inside sibling!")
            else:
                 print(f"Next sibling class is: {ns.get('class') if ns else 'None'}")
                 
if __name__ == "__main__":
    parse_html('./.agents/skills/au_race_extractor/scripts/racenet_print_curl.html')
