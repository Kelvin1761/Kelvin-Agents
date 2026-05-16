import sys
import os
import json
import re
import time
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def extract_race_data(racedate, race_no, venue):
    # Construct URL for individual race
    # Format: https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx?RaceDate=2024/09/01&RaceNo=1
    formatted_date = racedate.replace('-', '/')
    url = f"https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx?RaceDate={formatted_date}&RaceNo={race_no}"
    
    try:
        resp = cffi_requests.get(url, impersonate="chrome120", timeout=30)
        if resp.status_code != 200: return None
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 1. Extract Venue if not provided
        if venue == "Unknown":
            venue_match = soup.find(string=re.compile('沙田|跑馬地'))
            if venue_match:
                venue = "沙田" if "沙田" in venue_match else "跑馬地"

        # 1. Basic Race Info (Check if race exists)
        perf_table = soup.find('table', class_='f_tac')
        if not perf_table: return None
        
        # 2. Extract Results Table
        results = []
        rows = perf_table.find_all('tr')[1:] # Skip header
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 10: continue
            
            # Running Positions (走位) - Use separator to preserve logic
            run_pos = cells[9].get_text(separator=" ", strip=True)
            
            res = {
                'pos': cells[0].get_text(strip=True),
                'horse_no': cells[1].get_text(strip=True),
                'horse_name': cells[2].get_text(strip=True),
                'jockey': cells[3].get_text(strip=True),
                'trainer': cells[4].get_text(strip=True),
                'actual_wt': cells[5].get_text(strip=True),
                'horse_wt': cells[6].get_text(strip=True),
                'draw': cells[7].get_text(strip=True),
                'lbw': cells[8].get_text(strip=True),
                'running_positions': run_pos,
                'finish_time': cells[10].get_text(strip=True),
                'win_odds': cells[11].get_text(strip=True)
            }
            results.append(res)

        # 3. Extract Sectional Times (分段時間)
        sectional_times = []
        cumulative_times = []
        
        # Try to find the section by searching for header text first
        sec_header = soup.find(string=re.compile('分段時間|總時間'))
        sectional_table = None
        if sec_header:
            sectional_table = sec_header.find_parent('table')
            
        if not sectional_table:
            # Fallback to summary attribute for older pages
            sectional_table = soup.find('table', summary=re.compile('分段時間|總時間'))
        
        if sectional_table:
            rows = sectional_table.find_all('tr')
            for row in rows:
                cells = [td.get_text(separator=' ', strip=True) for td in row.find_all(['td', 'th'])]
                if cells:
                    sectional_times.append(cells)
                    # Check if this is a cumulative time row (usually contains brackets or text like '總時間')
                    if any('總時間' in c or '(' in c for c in cells):
                        cumulative_times.append(cells)

        # 4. Extract Incident Report (賽後報告)
        incident_report = ""
        # Search for the header row of the incident table
        report_header_row = soup.find(string=re.compile('名次 馬號 馬名 競賽事件'))
        if report_header_row:
            report_table = report_header_row.find_parent('table')
            if report_table:
                incident_report = report_table.get_text(separator=' ', strip=True)
        
        # Fallback 1: Search for '競賽事件報告' but ensure it's the one in the main content
        if not incident_report:
            headers = soup.find_all(string=re.compile('競賽事件報告|賽後報告'))
            for h in headers:
                if h.parent.name != 'a': # Skip menu links
                    # The report is usually in the next table
                    next_table = h.find_next('table')
                    if next_table:
                        text = next_table.get_text(separator=' ', strip=True)
                        if len(text) > 50: # Ensure it's not an empty table
                            incident_report = text
                            break
        
        # Fallback 2: Content div slicing
        if not incident_report:
            content_div = soup.find('div', class_='content')
            if content_div:
                text = content_div.get_text(separator=' ', strip=True)
                start_match = re.search(r'競賽事件報告|賽事報告', text)
                end_match = re.search(r'勝出馬匹血統|備註', text)
                if start_match:
                    start_idx = start_match.end()
                    end_idx = end_match.start() if end_match and end_match.start() > start_idx else len(text)
                    incident_report = text[start_idx:end_idx].strip()
        
        # Cleanup
        if incident_report:
            # Remove redundant labels
            incident_report = re.sub(r'名次 馬號 馬名 競賽事件', '', incident_report).strip()
            incident_report = re.sub(r'\s+', ' ', incident_report)

        return {
            'racedate': racedate,
            'race_no': race_no,
            'venue': venue,
            'results': results,
            'sectional_times': sectional_times,
            'cumulative_times': cumulative_times,
            'incident_report': incident_report
        }
    except Exception as e:
        print(f"Error extracting Race {race_no}: {e}", flush=True)
        return None

if __name__ == '__main__':
    # Handle both 2 and 3 argument calls for backward compatibility during batch
    if len(sys.argv) < 3:
        print("Usage: python fast_extract_results.py <racedate> <output_path> [optional: venue]")
        sys.exit(1)
    
    date = sys.argv[1]
    out = sys.argv[2]
    ven = sys.argv[3] if len(sys.argv) > 3 else "Unknown"
    
    all_races = {}
    for i in range(1, 13):
        print(f"Extracting Race {i}...", flush=True)
        data = extract_race_data(date, i, ven)
        if data and data['results']:
            all_races[str(i)] = data
            time.sleep(0.5)
        else:
            break
            
    if all_races:
        if os.path.dirname(out): os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(all_races, f, ensure_ascii=False, indent=2)
        print(f"✅ Extracted {len(all_races)} races to {out}")
