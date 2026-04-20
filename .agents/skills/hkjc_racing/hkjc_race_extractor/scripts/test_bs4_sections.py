import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from bs4 import BeautifulSoup
import re

html = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "page.html")).read()
soup = BeautifulSoup(html, 'html.parser')

trs = soup.find_all('tr', class_='data-row')
for tr in trs[:5]:
    tds = tr.find_all('td')
    if len(tds) >= 10:
        sect_div = tds[9].find('div', class_='Sectional_Times')
        if sect_div:
            print("--- HTML ---")
            print(sect_div.prettify())
            print("--- Parsed Sections ---")
            
            # Original Logic:
            sections = [d.text.split('\n')[0].strip() for d in sect_div.find_all('div', recursive=False) if 'item' in d.get('class', [''])[0]]
            sect_text = ", ".join([s for s in sections if re.match(r'^[\d\s.]+$', s)])
            print("OLD PARSER RESULT:", repr(sect_text))
            
            # Try finding ALL divs that have a class containing 'Sectional_Times_item'
            items = sect_div.find_all('div', class_=re.compile('Sectional_Times_item'))
            new_sections = []
            for item in items:
                # We only want top level times, which might have sub-items.
                # get just the direct text of this element excluding children
                text = ''.join(item.find_all(text=True, recursive=False)).strip()
                if re.match(r'^[\d.]+$', text):
                    new_sections.append(text)
            
            print("NEW PARSER RESULT:", repr(", ".join(new_sections)))
            
            last_divs = sect_div.find_all('div', recursive=False)
            comment_text = ""
            if last_divs and not last_divs[-1].get('class'):
                comment_text = last_divs[-1].text.strip()
            print("COMMENT:", repr(comment_text))
            
