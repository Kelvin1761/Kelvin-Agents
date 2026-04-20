import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import extract_formguide_playwright as ex
from bs4 import BeautifulSoup
import re
import urllib.parse

html = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "page.html")).read()
soup = BeautifulSoup(html, 'html.parser')

output = []
output.append("#### 全場馬匹分析 (Full Field Analysis)")
trs = soup.find_all('tr')
current_horse = None

for tr in trs:
    classes = tr.get('class', [])
    if 'comment' in classes:
        if current_horse:
            ex.push_horse(output, current_horse)
        current_horse = {'horseNumber': '', 'horseName': '', 'draw': '', 'bodyWeight': '', 'carriedWeight': '', 'jockey': '', 'trainer': '', 'age': '', 'pastRaces': []}
        tds = tr.find_all('td')
        if len(tds) >= 8:
            num_name = tds[0].text.strip()
            match = re.match(r'^(\d+)\s+(.+)', num_name)
            if match:
                current_horse['horseNumber'] = match.group(1)
                current_horse['horseName'] = match.group(2).strip()
            else:
                current_horse['horseName'] = num_name
            current_horse['draw'] = tds[1].text.replace('(','').replace(')','').strip()
            current_horse['bodyWeight'] = tds[2].text.strip()
            current_horse['carriedWeight'] = tds[3].text.strip()
            current_horse['jockey'] = tds[4].text.strip()
            current_horse['trainer'] = tds[5].text.strip()
    elif 'data-row' in classes and current_horse is not None:
        tds = tr.find_all('td')
        if len(tds) >= 10:
            sect_div = tds[9].find('div', class_='Sectional_Times')
            sect_text = ""
            comment_text = ""
            if sect_div:
                sections = [d.text.split('\n')[0].strip() for d in sect_div.find_all('div', recursive=False) if 'item' in d.get('class', [''])[0]]
                sect_text = " ".join([s for s in sections if re.match(r'^[\d\s.]+$', s)])
                last_divs = sect_div.find_all('div', recursive=False)
                if last_divs and not last_divs[-1].get('class'):
                    comment_text = last_divs[-1].text.strip()
                elif not comment_text:
                    full = sect_div.text.strip()
                    comment_text = full.replace(sect_text, '').strip().replace('\n', ' ')
            race = {'date': tds[0].text.strip(), 'daysSince': tds[1].text.strip(), 'trackInfo': tds[2].text.strip(), 'draw': tds[3].text.strip(), 'bodyWeight': tds[4].text.strip(), 'carriedWeight': tds[5].text.strip(), 'jockey': tds[6].text.strip(), 'rankTotal': tds[7].text.strip(), 'speedEnergy': tds[8].text.strip(), 'sectionalTimes': sect_text, 'comment': comment_text}
            current_horse['pastRaces'].append(race)

if current_horse:
    ex.push_horse(output, current_horse)

print("\n".join(output[:30]))
