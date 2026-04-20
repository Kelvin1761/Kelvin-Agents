#!/usr/bin/env python3
"""
scrape_race_results.py — Claw Code 賽後結果抓取器

Usage:
    python3 scrape_race_results.py --venue ST --date 2026-04-19
    python3 scrape_race_results.py --venue HV --date 2026-04-22 --races 1-9

Extracts race results from:
    https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx

Output: race_results_{venue}_{date}.json
"""
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import re
import json
import argparse
import time
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup


VENUE_MAP = {"ST": "ST", "HV": "HV", "沙田": "ST", "跑馬地": "HV"}
BASE_URL = "https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx"


def fetch_result_page(date_str: str, venue: str, race_no: int) -> str:
    """Fetch a single race result page."""
    from curl_cffi import requests as cffi_requests
    url = f"{BASE_URL}?RaceDate={date_str}&Racecourse={venue}&RaceNo={race_no}"
    resp = cffi_requests.get(url, impersonate="chrome120", timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_result_table(html: str, race_no: int) -> dict:
    """Parse race result from HTML."""
    soup = BeautifulSoup(html, 'html.parser')

    result = {"race": race_no, "horses": []}

    # Find result table (has 名次/馬號/馬名 headers)
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if len(rows) < 3:
            continue
        header_cells = rows[0].find_all(['th', 'td'])
        header = [c.get_text(strip=True) for c in header_cells]
        if '名次' not in header:
            continue

        # Map column indices
        col_map = {}
        for i, h in enumerate(header):
            if '名次' in h:
                col_map['place'] = i
            elif '馬號' in h:
                col_map['number'] = i
            elif '馬名' in h:
                col_map['name'] = i
            elif '騎師' in h:
                col_map['jockey'] = i
            elif '頭馬距離' in h:
                col_map['margin'] = i
            elif '完成時間' in h:
                col_map['time'] = i
            elif '獨贏賠率' in h or '獨贏' in h:
                col_map['odds'] = i
            elif '檔位' in h:
                col_map['draw'] = i
            elif '實際負磅' in h:
                col_map['weight'] = i

        # Parse data rows
        for row in rows[1:]:
            cells = row.find_all('td')
            if len(cells) < 5:
                continue
            vals = [c.get_text(strip=True) for c in cells]

            try:
                horse = {
                    "place": vals[col_map.get('place', 0)],
                    "number": int(vals[col_map.get('number', 1)]) if vals[col_map.get('number', 1)].isdigit() else 0,
                    "name": re.sub(r'\([A-Z]\d+\)', '', vals[col_map.get('name', 2)]).strip(),
                }
                if 'jockey' in col_map:
                    horse["jockey"] = vals[col_map['jockey']]
                if 'margin' in col_map:
                    horse["margin"] = vals[col_map['margin']]
                if 'time' in col_map:
                    horse["time"] = vals[col_map['time']]
                if 'odds' in col_map:
                    horse["odds"] = vals[col_map['odds']]
                if 'draw' in col_map:
                    horse["draw"] = int(vals[col_map['draw']]) if vals[col_map['draw']].isdigit() else 0
                if 'weight' in col_map:
                    horse["weight"] = vals[col_map['weight']]

                result["horses"].append(horse)
            except (ValueError, IndexError, KeyError):
                continue

        break  # Only process first matching table

    # Extract race info from page
    race_info_text = soup.get_text()
    dist_match = re.search(r'(\d{3,4})\s*米', race_info_text)
    if dist_match:
        result["distance"] = int(dist_match.group(1))

    return result


def main():
    parser = argparse.ArgumentParser(description="Scrape HKJC Race Results")
    parser.add_argument("--venue", "-v", required=True, help="Venue: ST or HV")
    parser.add_argument("--date", "-d", required=True, help="Date: YYYY-MM-DD")
    parser.add_argument("--races", "-r", default="1-11", help="Race range: 1-11 (default)")
    parser.add_argument("--output", "-o", default=None, help="Output JSON path")
    args = parser.parse_args()

    venue = VENUE_MAP.get(args.venue, args.venue)
    date_str = args.date.replace("-", "/")
    
    # Parse race range
    if '-' in args.races:
        start, end = args.races.split('-')
        race_range = range(int(start), int(end) + 1)
    else:
        race_range = [int(r) for r in args.races.split(',')]

    print(f"[Claw Code] Scraping results: {venue} {args.date} (Races {args.races})")

    results = {
        "meta": {
            "venue": venue,
            "date": args.date,
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": BASE_URL,
        },
        "races": []
    }

    for race_no in race_range:
        try:
            html = fetch_result_page(date_str, venue, race_no)
            race = parse_result_table(html, race_no)
            if race["horses"]:
                results["races"].append(race)
                winner = race["horses"][0]
                print(f"  R{race_no}: 🏆 #{winner['number']} {winner['name']} ({winner.get('time','')}) — {len(race['horses'])} runners")
            else:
                print(f"  R{race_no}: ⚠️ No results found (race may not exist)")
                break  # Stop if no more races
        except Exception as e:
            print(f"  R{race_no}: ❌ {e}")
        
        if race_no < max(race_range):
            time.sleep(0.5)

    # Output
    script_dir = Path(__file__).parent
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = script_dir / f"race_results_{venue}_{args.date}.json"

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    n = len(results["races"])
    print(f"\n[DONE] {n} races extracted → {out_path.name}")


if __name__ == "__main__":
    main()
