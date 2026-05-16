import sys
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
import re

def fetch_horse_profile(horse_id):
    url = f"https://racing.hkjc.com/racing/information/Chinese/Horse/Horse.aspx?HorseId={horse_id}"
    print(f"Fetching Profile: {url}")
    
    resp = cffi_requests.get(url, impersonate="chrome120", timeout=30)
    if resp.status_code != 200:
        return None
        
    soup = BeautifulSoup(resp.text, 'html.parser')
    data = {}
    
    # The horse info is usually in a specific table or div
    # Look for text like "出生地", "進口類別"
    tables = soup.find_all('table')
    for t in tables:
        text = t.get_text()
        if '出生地' in text:
            # Found info table
            rows = t.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                for i, cell in enumerate(cells):
                    ctext = cell.get_text(strip=True)
                    if '出生地' in ctext and i+1 < len(cells):
                        data['origin'] = cells[i+1].get_text(strip=True)
                    if '進口類別' in ctext and i+1 < len(cells):
                        data['import_type'] = cells[i+1].get_text(strip=True)
                    if '父系' in ctext and i+1 < len(cells):
                        data['sire'] = cells[i+1].get_text(strip=True)
                    if '母系' in ctext and i+1 < len(cells):
                        data['dam'] = cells[i+1].get_text(strip=True)
                    if '外祖父' in ctext and i+1 < len(cells):
                        data['dam_sire'] = cells[i+1].get_text(strip=True)
    return data

if __name__ == "__main__":
    test_id = "H196" # 上市魅力
    profile = fetch_horse_profile(test_id)
    print(profile)
