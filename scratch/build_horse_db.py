import os
import json
import re
import time
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
import sys

CACHE_PATH = 'scratch/horse_metadata_cache.json'
LIST_PATH = 'scratch/json_files.txt'

def load_cache():
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}
    return {}

def save_cache(cache):
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def fetch_horse_details(horse_id):
    url = f"https://racing.hkjc.com/racing/information/Chinese/Horse/Horse.aspx?HorseId={horse_id}"
    try:
        resp = cffi_requests.get(url, impersonate="chrome120", timeout=30)
        if resp.status_code != 200: return None
        soup = BeautifulSoup(resp.text, 'html.parser')
        details = {'horse_id': horse_id}
        for t in soup.find_all('table'):
            if '出生地' in t.get_text():
                for row in t.find_all('tr'):
                    cells = [c.get_text(strip=True) for c in row.find_all('td')]
                    for i, c in enumerate(cells):
                        if '出生地' in c and i+1 < len(cells): details['origin'] = cells[i+1]
                        if '進口類別' in c and i+1 < len(cells): details['import_type'] = cells[i+1]
                        if '父系' in c and i+1 < len(cells): details['sire'] = cells[i+1]
                        if '母系' in c and i+1 < len(cells): details['dam'] = cells[i+1]
                        if '外祖父' in c and i+1 < len(cells): details['dam_sire'] = cells[i+1]
                break
        return details
    except: return None

def build_horse_db():
    cache = load_cache()
    found_ids = set()
    if not os.path.exists(LIST_PATH): return

    with open(LIST_PATH, 'r', encoding='utf-16') as f:
        paths = [line.strip() for line in f if line.strip()]
    
    for path in paths:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for r in data.values():
                    for h in r.get('results', []):
                        m = re.search(r'\(([A-Z]\d+)\)', h.get('horse_name', ''))
                        if m: found_ids.add(m.group(1))
        except: pass
    
    to_fetch = [hid for hid in found_ids if hid not in cache]
    print(f"Need to fetch: {len(to_fetch)}", flush=True)
    
    for i, hid in enumerate(to_fetch[:50]): # Fetch 50
        details = fetch_horse_details(hid)
        if details:
            cache[hid] = details
            print(f"[{i+1}] Fetched {hid}", flush=True)
            if (i+1) % 5 == 0:
                save_cache(cache)
            time.sleep(0.5)
    save_cache(cache)
    print("✅ Sync Complete.", flush=True)

if __name__ == '__main__':
    build_horse_db()
