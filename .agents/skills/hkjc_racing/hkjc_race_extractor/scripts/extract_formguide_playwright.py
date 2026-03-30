import sys
import json
import urllib.parse
from bs4 import BeautifulSoup  # type: ignore
from playwright.sync_api import sync_playwright  # type: ignore

# Force UTF-8 stdout regardless of OS locale (prevents garbled Chinese on Windows)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def format_race(race, idx):
    date = race.get('date', '')
    days = race.get('daysSince', '')
    track = race.get('trackInfo', '')
    draw = race.get('draw', '')
    bw = race.get('bodyWeight', '')
    cw = race.get('carriedWeight', '')
    joc = race.get('jockey', '')
    rank = race.get('rankTotal', '')
    speed = race.get('speedEnergy', '')
    sect = race.get('sectionalTimes', '')
    comment = race.get('comment', '')
    out: list[str] = []
    out.append(f"  [{idx}] {date} | 日數: {days} | {track}")
    out.append(f"      檔位: {draw} | 馬重: {bw} | 負磅: {cw} | 騎師: {joc} | 名次: {rank}")
    out.append(f"      能量: {speed} | 分段時間: {sect}")
    out.append(f"      短評: {comment}")
    return "\n".join(out)

def extract_formguide(url):
    print(f"Extracting form guide using Playwright & BeautifulSoup: {url}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until='networkidle')
        page.wait_for_timeout(3000)
        html_content = page.content()
        browser.close()
        
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Overview
    race_date = ""
    venue_info = ""
    class_info = ""
    
    # Fallback/heuristic for overview using div classes if possible
    race_texts = soup.find_all('div', class_='race-text')
    if race_texts:
        for rt in race_texts:
            divs = rt.find_all('div')
            if len(divs) >= 3:
                venue_info = divs[0].text.strip()
                class_info = divs[1].text.strip() + " " + divs[2].text.strip()
    
    date_div = soup.find('div', class_='date')
    if date_div:
        race_date = date_div.text.strip()

    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    race_no = f"第{qs.get('RaceNo', [''])[0]}場"
    
    output: list[str] = []
    output.append("#### 賽事概覽 (Race Overview)")
    output.append(f"- 賽事日期 / 場次 / 跑道及場地狀況: {race_date} / {race_no} / {venue_info} {class_info}")
    output.append("")
    output.append("#### 全場馬匹分析 (Full Field Analysis)")
    
    # Parse horses and races
    trs = soup.find_all('tr')
    
    current_horse = None
    
    for tr in trs:
        classes = tr.get('class', [])
        
        # Horse header row
        if 'comment' in classes:
            if current_horse:
                # Append previous horse
                push_horse(output, current_horse)
                
            current_horse = {
                'horseNumber': '', 'horseName': '', 'draw': '', 'bodyWeight': '',
                'carriedWeight': '', 'jockey': '', 'trainer': '', 'age': '', 'pastRaces': []
            }
            tds = tr.find_all('td')
            if len(tds) >= 8:
                # 12 發光發亮
                num_name = tds[0].text.strip()
                import re
                match = re.match(r'^(\\d+)\\s*(.+)', num_name)
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
                
        # Race data row
        elif 'data-row' in classes and current_horse is not None:
            tds = tr.find_all('td')
            if len(tds) >= 10:
                # extract sections & comment
                sect_div = tds[9].find('div', class_='Sectional_Times')
                sect_text = ""
                comment_text = ""
                if sect_div:
                    # Iterating through all children of sect_div to grab times and comments
                    new_sections: list[str] = []
                    for child in sect_div.find_all('div', recursive=False):
                        classes = child.get('class', [])
                        # if it has a class and the word 'item' is in the first class name (e.g. Sectional_Times_item)
                        if classes and 'item' in classes[0].lower():
                            pieces = child.get_text(separator='|', strip=True).split('|')
                            if pieces:
                                # Find the first text block inside the item that contains a number
                                time_text = ""
                                for p in pieces:
                                    if re.search(r'\d', p):
                                        time_text = re.sub(r'[^\d.]', '', p)
                                        break
                                if time_text:
                                    new_sections.append(time_text)
                        # if it has no class, it's the comment
                        elif not classes:
                            comment_text = child.text.strip()
                            
                    sect_text = ", ".join(new_sections)
                    if not comment_text:
                        # Fallback just take the whole text and strip sections
                        full = sect_div.text.strip()
                        # This is a bit hacky but works for now
                        comment_text = full.replace(sect_text, '').strip()

                race = {
                    'date': tds[0].text.strip(),
                    'daysSince': tds[1].text.strip(),
                    'trackInfo': tds[2].text.strip(),
                    'draw': tds[3].text.strip(),
                    'bodyWeight': tds[4].text.strip(),
                    'carriedWeight': tds[5].text.strip(),
                    'jockey': tds[6].text.strip(),
                    'rankTotal': tds[7].text.strip(),
                    'speedEnergy': tds[8].text.strip(),
                    'sectionalTimes': sect_text,
                    'comment': comment_text
                }
                current_horse['pastRaces'].append(race)

    # Append the last horse
    if current_horse:
        push_horse(output, current_horse)

    return "\n".join(output)

def push_horse(output, horse):
    output.append(f"馬號: {horse.get('horseNumber', '')}")
    output.append(f"馬名: {horse.get('horseName', '')}")
    output.append(f"檔位: {horse.get('draw', '')}")
    output.append(f"騎師: {horse.get('jockey', '')}")
    output.append(f"負磅: {horse.get('carriedWeight', '')}")
    output.append(f"排位體重: {horse.get('bodyWeight', '')}")
    output.append("")
    output.append("往績紀錄:")
    
    if not horse.get('pastRaces'):
        output.append("  (無往績紀錄)")
    else:
        for idx, race in enumerate(horse.get('pastRaces', []), 1):
            output.append(format_race(race, idx))
            
    output.append("")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
        result = extract_formguide(url)
        print(result)
    else:
        print("Please provide a URL")
