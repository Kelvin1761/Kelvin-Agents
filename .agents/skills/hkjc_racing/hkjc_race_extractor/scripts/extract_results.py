#!/usr/bin/env python3
"""
HKJC Single Race Results Extractor.
Extracts results for one specific race from the HKJC localresults page.
Designed to be called by a batch script for concurrent extraction.

Usage:
    python extract_results.py <results_url>
"""
import sys
import os
import re
from bs4 import BeautifulSoup  # type: ignore
from playwright.sync_api import sync_playwright  # type: ignore

# Add parent directories to path for lightpanda_utils
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, '..', '..', '..', '..', '..'))
sys.path.insert(0, _PROJECT_ROOT)
from lightpanda_utils import start_lightpanda, stop_lightpanda

def extract_race_data(soup, race_no):
    """Extract all data for a single race from the soup."""
    text = soup.get_text(separator='\n', strip=True)
    
    result = {
        'race_no': race_no,
        'class_info': '',
        'distance': '',
        'race_name': '',
        'prize': '',
        'going': '',
        'track': '',
        'win_time': '',
        'sectional_times': '',
        'cumulative_times': '',
        'results': [],
        'incident_report': '',
    }

    # Class and Distance
    class_match = re.search(r'(第[一二三四五]班|公開賽|新馬賽)\s*-\s*(\d+米)\s*-\s*\(([^)]+)\)', text)
    if class_match:
        result['class_info'] = f"{class_match.group(1)} ({class_match.group(3)})"
        result['distance'] = class_match.group(2)
    elif "第" in text and "班" in text:
        # Fallback for different formats
        m = re.search(r'(第[一二三四五]班)', text)
        if m: result['class_info'] = m.group(1)
        m = re.search(r'(\d+米)', text)
        if m: result['distance'] = m.group(1)

    # Going
    going_match = re.search(r'場地狀況\s*[:：]\s*(.+?)(?:\n|$)', text)
    if going_match:
        result['going'] = going_match.group(1).strip()

    # Track
    track_match = re.search(r'賽道\s*[:：]\s*(.+?)(?:\n|$)', text)
    if track_match:
        result['track'] = track_match.group(1).strip()

    # Prize
    prize_match = re.search(r'(HK\$[\d,]+)', text)
    if prize_match:
        result['prize'] = prize_match.group(1)

    # Times
    cum_match = re.findall(r'\((\d+[:.]\d+)\)', text)
    if cum_match:
        # Avoid slicing if cum_match is small, and ensure it's a list
        limit = min(len(cum_match), 10)
        result['cumulative_times'] = ' | '.join(f'({t})' for t in cum_match[:limit])

    sect_match = re.search(r'分段時間\s*[:：]\s*([\s\S]*?)(?:全方位|名次|$)', text)
    if sect_match:
        times = re.findall(r'(\d+\.\d+)', sect_match.group(1))
        if times:
            result['sectional_times'] = ' '.join(times)

    time_match = re.search(r'時間\s*[:：]\s*([\s\S]*?)(?:分段|$)', text)
    if time_match:
        time_text = time_match.group(1)
        t = re.findall(r'\((\d+[:.]\d+)\)', time_text)
        if t:
            result['win_time'] = t[-1]

    # Results Table
    tables = soup.find_all('table')
    for table in tables:
        header_text = table.get_text()
        if '名次' in header_text and '馬號' in header_text and '騎師' in header_text:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                cell_texts = [c.get_text(strip=True) for c in cells]
                if not cell_texts or not cell_texts[0].isdigit():
                    continue
                if len(cell_texts) >= 12:
                    entry = {
                        'pos': cell_texts[0],
                        'horse_no': cell_texts[1],
                        'horse_name': cell_texts[2],
                        'jockey': cell_texts[3],
                        'trainer': cell_texts[4],
                        'actual_weight': cell_texts[5],
                        'declared_weight': cell_texts[6],
                        'draw': cell_texts[7],
                        'margin': cell_texts[8],
                        'running_positions': cell_texts[9],
                        'finish_time': cell_texts[10],
                        'win_odds': cell_texts[11],
                    }
                    result['results'].append(entry)
            break

    # Incident Report
    report_tag = soup.find(lambda t: t.name in ['div', 'table'] and '競賽事件報告' in t.get_text())
    if report_tag:
        # Walk up to find the container
        container = report_tag.find_parent('table') or report_tag.find_parent('div', class_=re.compile(r'race_detail|report', re.I))
        if container:
            raw_text = container.get_text(separator='\n', strip=True)
            raw_text = re.sub(r'^.*?競賽事件\n?', '', raw_text, flags=re.DOTALL)
            lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
            
            report_lines = []
            i = 0
            while i < len(lines):
                if lines[i].isdigit() and i+3 < len(lines) and lines[i+1].isdigit():
                    pos, no = lines[i], lines[i+1]
                    name_str = lines[i+2]
                    n_idx = i+3
                    if n_idx < len(lines) and lines[n_idx].startswith('(') and lines[n_idx].endswith(')'):
                        name_str += lines[n_idx]
                        n_idx += 1
                    comment_parts = []
                    while n_idx < len(lines):
                        if lines[n_idx].isdigit() and n_idx+1 < len(lines) and lines[n_idx+1].isdigit() and int(lines[n_idx]) <= 14:
                            break
                        comment_parts.append(lines[n_idx])
                        n_idx += 1
                    report_lines.append(f"{pos:<3} {no:<4} {name_str:<15} - {' '.join(comment_parts)}")
                    i = n_idx
                else:
                    i += 1
            result['incident_report'] = '\n'.join(report_lines) if report_lines else raw_text.strip()

    return result

def format_output(data):
    out = [f"{'='*70}", f"第 {data['race_no']} 場", f"{'='*70}"]
    out.extend([
        f"班次: {data['class_info']}",
        f"路程: {data['distance']}",
        f"場地狀況: {data['going']}",
        f"賽道: {data['track']}",
        f"完成時間: {data['win_time']}",
        f"分段時間: {data['sectional_times']}",
        ""
    ])
    out.append(f"{'名次':<4} {'馬號':<4} {'馬名':<16} {'騎師':<10} {'練馬師':<10} {'負磅':<5} {'體重':<5} {'檔位':<4} {'頭馬距離':<8} {'完成時間':<10} {'獨贏賠率':<6}")
    out.append(f"{'─'*70}")
    for r in data['results']:
        out.append(f"{r['pos']:<4} {r['horse_no']:<4} {r['horse_name']:<16} {r['jockey']:<10} {r['trainer']:<10} {r['actual_weight']:<5} {r['declared_weight']:<5} {r['draw']:<4} {r['margin']:<8} {r['finish_time']:<10} {r['win_odds']:<6}")
    
    if data['incident_report']:
        out.extend(["", "📋 競賽事件報告:", data['incident_report']])
    return '\n'.join(out)

def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_results.py <URL>")
        sys.exit(1)
    
    url = sys.argv[1]
    race_no = 1
    m = re.search(r'RaceNo=(\d+)', url)
    if m: race_no = int(m.group(1))

    # Check if batch script already started Lightpanda (env var set)
    cdp_url = os.environ.get('LIGHTPANDA_CDP_URL')
    lp_proc = None
    
    if cdp_url:
        # Batch mode: Lightpanda is already running, just connect
        use_lp = True
    else:
        # Standalone mode: start our own Lightpanda
        use_lp, lp_proc = start_lightpanda(_PROJECT_ROOT)
        cdp_url = "http://127.0.0.1:9222"
    
    try:
        with sync_playwright() as p:
            if use_lp:
                try:
                    browser = p.chromium.connect_over_cdp(cdp_url)
                    print(f"  [Lightpanda] Connected via CDP for Race {race_no}", file=sys.stderr)
                except Exception as e:
                    print(f"  [WARN] Lightpanda CDP connection failed: {e}. Falling back to Chromium.", file=sys.stderr)
                    use_lp = False
                    browser = p.chromium.launch(headless=True)
            else:
                browser = p.chromium.launch(headless=True)
            
            page = browser.new_page()
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=45000)
                page.wait_for_timeout(2000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1000)
                soup = BeautifulSoup(page.content(), 'html.parser')
                data = extract_race_data(soup, race_no)
                print(format_output(data))
            finally:
                browser.close()
    finally:
        stop_lightpanda(lp_proc)

if __name__ == "__main__":
    main()
