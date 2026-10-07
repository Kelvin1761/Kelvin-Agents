import os
os.environ.setdefault('PYTHONUTF8', '1')
import urllib.request
from urllib.parse import parse_qs, urljoin, urlparse
import ssl
from bs4 import BeautifulSoup
import sys
import re

# Force UTF-8 stdout regardless of OS locale (prevents garbled Chinese on Windows)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def clean_text(s):
    return re.sub(r'\s+', ' ', s).strip()


def parse_english_name_map(html):
    """Return an official HKJC ``brand number -> English horse name`` map."""
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table', class_='draggable')
    names = {}
    if not table or not table.find('tbody'):
        return names
    for tr in table.find('tbody').find_all('tr'):
        tds = [clean_text(td.text) for td in tr.find_all('td')]
        if len(tds) < 5:
            continue
        brand = tds[4].upper()
        name = tds[3].strip()
        if re.fullmatch(r'[A-Z]\d{3}', brand) and name:
            names[brand] = name
    return names


HKJC_HORSE_ID_RE = re.compile(r"^HK_\d{4}_[A-HJ-Z]\d{3}$", re.IGNORECASE)
HKJC_HORSE_PROFILE_BASE = "https://racing.hkjc.com"


def parse_horse_profile_link(row):
    """Return the exact official horse id and canonical profile URL from a row."""
    for link in row.find_all("a", href=True):
        href = link.get("href", "").strip()
        full_url = urljoin(HKJC_HORSE_PROFILE_BASE, href)
        horse_id = ""
        for key, values in parse_qs(urlparse(full_url).query).items():
            if key.lower() == "horseid" and values:
                horse_id = values[0].strip().upper()
                break
        if not horse_id:
            match = re.search(r"HK_\d{4}_[A-HJ-Z]\d{3}", href, re.IGNORECASE)
            horse_id = match.group(0).upper() if match else ""
        if HKJC_HORSE_ID_RE.fullmatch(horse_id):
            return {
                "hkjc_horse_id": horse_id,
                "horse_profile_url": (
                    "https://racing.hkjc.com/zh-hk/local/information/horse"
                    f"?horseid={horse_id}"
                ),
            }
    return {}

def extract_racecard(url):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        english_names = {}
        english_url = re.sub(r'/zh-hk/', '/en-us/', url, flags=re.IGNORECASE)
        if english_url != url:
            try:
                english_req = urllib.request.Request(english_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(english_req, context=ctx) as english_response:
                    english_html = english_response.read().decode('utf-8')
                english_names = parse_english_name_map(english_html)
            except Exception as english_error:
                print(f"Warning: English horse names unavailable: {english_error}", file=sys.stderr)

        with urllib.request.urlopen(req, context=ctx) as response:
            html = response.read().decode('utf-8')
            soup = BeautifulSoup(html, 'html.parser')

            # --- Header Extraction ---
            print("#### 第一部分：賽事資料 (Race Info)")
            header_div = None
            for div in soup.find_all('div', class_='f_fs13'):
                text = div.get_text(separator='|', strip=True)
                if '星期' in text and '場' in text and '獎金' in text:
                    header_div = div
                    break

            if header_div:
                parts = header_div.get_text(separator='|', strip=True).split('|')
                
                # Part 0: 第 3 場 - 環島中港通讓賽
                # Part 1: 2026年3月4日, 星期三, 跑馬地, 19:40
                # Part 2: 草地, "C" 賽道, 2200米, 好地至黏地
                # Part 3: 獎金: $1,170,000, 評分: 60-40, 第四班
                
                # Parse part 0
                race_no_match = re.search(r'第\s*(\d+)\s*場', parts[0])
                race_no = f"第{race_no_match.group(1)}場" if race_no_match else ""
                race_name = parts[0].split('-')[-1].strip() if '-' in parts[0] else parts[0]
                
                # Parse part 1
                p1_parts = [p.strip() for p in parts[1].split(',')]
                date_str = p1_parts[0] if len(p1_parts) > 0 else ""
                date_match = re.search(r'(\d+)年(\d+)月(\d+)日?', date_str)
                if date_match:
                    y, m, d = date_match.groups()
                    date_str = f"{y}-{int(m):02d}-{int(d):02d}"
                day_str = p1_parts[1] if len(p1_parts) > 1 else ""
                venue_str = p1_parts[2] if len(p1_parts) > 2 else ""
                time_str = p1_parts[3] if len(p1_parts) > 3 else ""

                # Parse part 2
                p2_parts = [p.strip() for p in parts[2].split(',')]
                surface = p2_parts[0] if len(p2_parts) > 0 else ""
                track = p2_parts[1].replace('"','') if len(p2_parts) > 1 else ""
                distance = p2_parts[2] if len(p2_parts) > 2 else ""

                # Parse part 3 correctly avoiding splitting prize comma
                p3_str = parts[3]
                prize = ""
                prize_match = re.search(r'獎金:\s*(\$[\d,]+)', p3_str)
                if prize_match:
                    prize = prize_match.group(1)
                
                rating = ""
                rating_match = re.search(r'評分:\s*([\d\-a-zA-Z]+)', p3_str)
                if rating_match:
                    rating = rating_match.group(1)
                
                race_class = ""
                # Class usually at the end after last comma
                class_parts = [p.strip() for p in p3_str.split(',')]
                if class_parts:
                    race_class = class_parts[-1]
                    if '班' not in race_class and '級' not in race_class:
                        race_class = "" # heuristic

                print(f"場次: {race_no}")
                print(f"賽事名稱: {race_name}")
                print(f"日期: {date_str}")
                print(f"星期: {day_str}")
                print(f"地點: {venue_str}")
                print(f"時間: {time_str}")
                print(f"場地: {surface}")
                print(f"賽道: {track}")
                print(f"路程: {distance}")
                print(f"獎金: {prize}")
                print(f"評分: {rating}")
                print(f"班次: {race_class}")
            else:
                parsed = urlparse(url)
                qs = parse_qs(parsed.query)
                date_str = qs.get('racedate', [''])[0]
                race_no = qs.get('RaceNo', [''])[0]
                course = qs.get('Racecourse', [''])[0]
                course_name = '跑馬地' if course == 'HV' else '沙田' if course == 'ST' else course
                print(f"場次: 第{race_no}場")
                print(f"日期: {date_str}")
                print(f"地點: {course_name}")

            print("")
            print("#### 第二部分：馬匹資料 (Horse Info)")

            table = soup.find('table', class_='draggable')
            if table:
                tbody = table.find('tbody')
                if tbody:
                    for tr in tbody.find_all('tr'):
                        tds = [clean_text(td.text) for td in tr.find_all('td')]
                        if len(tds) < 27: continue

                        brand = tds[4].upper()
                        print(f"馬號: {tds[0]}")
                        print(f"馬名: {tds[3]}")
                        if english_names.get(brand):
                            print(f"英文馬名: {english_names[brand]}")
                        print(f"賽績: {tds[1]}")
                        print(f"烙號: {brand}")
                        profile = parse_horse_profile_link(tr)
                        if profile:
                            print(f"HKJC馬匹ID: {profile['hkjc_horse_id']}")
                            print(f"官方馬匹資料: {profile['horse_profile_url']}")
                        print(f"負磅: {tds[5]}")
                        print(f"騎師: {tds[6]}")
                        print(f"檔位: {tds[8]}")
                        print(f"練馬師: {tds[9]}")
                        print(f"評分: {tds[11]}")
                        print(f"評分+/-: {tds[12]}")
                        print(f"排位體重: {tds[13]}")
                        print(f"馬齡: {tds[16]}")
                        print(f"分齡讓磅: {tds[17]}")
                        print(f"性別: {tds[18]}")
                        print(f"優先參賽次序: {tds[20]}")
                        print(f"上賽距今日數: {tds[21]}")
                        print(f"配備: {tds[22]}")
                        print(f"父系: {tds[24]}")
                        print(f"母系: {tds[25]}")
                        print("")
            else:
                print("Could not find racecard table.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        extract_racecard(sys.argv[1])
    else:
        print("Please provide a URL")
