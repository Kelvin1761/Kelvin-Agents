#!/usr/bin/env python3
"""
HKJC Fast Race Results Extractor — curl_cffi + local Playwright hydration.

Uses the Claw Code architecture:
1. curl_cffi to bypass anti-bot and download raw HTML rapidly
2. Playwright loads the local HTML file to extract JS-rendered data
3. No need for remote browser connections

Usage:
    python fast_extract_results.py --base_url "URL" --races "1-11" --output_dir "/path/to/output"
    python fast_extract_results.py --date 2026/04/06 --venue ST --races "1-11" --output_dir "/path/to/output"
"""
import os
import sys
import re
import json
import argparse
import tempfile
from urllib.parse import urlparse, parse_qs

def fetch_page_html(url, temp_dir):
    """Download raw HTML using curl_cffi to bypass anti-bot."""
    try:
        from curl_cffi import requests as cffi_requests
        resp = cffi_requests.get(url, impersonate="chrome120", timeout=30)
        if resp.status_code == 200:
            html_path = os.path.join(temp_dir, "page.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(resp.text)
            return html_path, resp.text
    except ImportError:
        pass
    
    # Fallback: standard requests with browser-like headers
    import urllib.request
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'zh-HK,zh;q=0.9,en;q=0.8',
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode('utf-8')
        html_path = os.path.join(temp_dir, "page.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        return html_path, html

def extract_via_playwright_local(html_path, race_no):
    """Load local HTML in Playwright and extract JS-rendered race data."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file://{html_path}", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)  # Allow JS to hydrate
        
        # Try extracting from JS state first (HKJC may embed data)
        try:
            js_data = page.evaluate("""() => {
                // Try common SPA state patterns
                if (window.__NEXT_DATA__) return JSON.stringify(window.__NEXT_DATA__);
                if (window.__NUXT__) return JSON.stringify(window.__NUXT__);
                if (window.raceResult) return JSON.stringify(window.raceResult);
                if (window.raceData) return JSON.stringify(window.raceData);
                return null;
            }""")
            if js_data:
                browser.close()
                return {"type": "js_state", "data": json.loads(js_data)}
        except Exception:
            pass
        
        # Fallback: extract from rendered HTML tables
        try:
            table_data = page.evaluate("""() => {
                const results = [];
                const tables = document.querySelectorAll('table');
                for (const table of tables) {
                    const text = table.textContent;
                    if (text.includes('名次') && text.includes('馬號') && text.includes('騎師')) {
                        const rows = table.querySelectorAll('tr');
                        for (const row of rows) {
                            const cells = Array.from(row.querySelectorAll('td, th'));
                            const cellTexts = cells.map(c => c.textContent.trim());
                            if (cellTexts.length >= 10 && /^\d+$/.test(cellTexts[0])) {
                                results.push(cellTexts);
                            }
                        }
                    }
                }
                
                // Also get sectional times, going, class info
                const bodyText = document.body.textContent;
                const meta = {};
                const goingMatch = bodyText.match(/場地狀況\\s*[:：]\\s*(.+?)(?:\\n|$)/);
                if (goingMatch) meta.going = goingMatch[1].trim();
                const trackMatch = bodyText.match(/賽道\\s*[:：]\\s*(.+?)(?:\\n|$)/);
                if (trackMatch) meta.track = trackMatch[1].trim();
                
                return {results, meta};
            }""")
            browser.close()
            if table_data and table_data.get('results'):
                return {"type": "table", "data": table_data}
        except Exception as e:
            browser.close()
            return {"type": "error", "error": str(e)}
    
    return None


def extract_from_raw_html(html_text, race_no):
    """Extract structured data from raw HTML using BeautifulSoup — no JS needed."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None
    
    soup = BeautifulSoup(html_text, 'html.parser')
    text = soup.get_text(separator='\n', strip=True)
    
    result = {
        'race_no': race_no,
        'class_info': '',
        'distance': '',
        'going': '',
        'track': '',
        'win_time': '',
        'sectional_times': '',
        'results': [],
        'incident_report': '',
    }
    
    # Class and Distance
    class_match = re.search(r'(第[一二三四五]班|公開賽|新馬賽)\s*-\s*(\d+米)', text)
    if class_match:
        result['class_info'] = class_match.group(1)
        result['distance'] = class_match.group(2)
    
    # Going
    going_match = re.search(r'場地狀況\s*[:：]\s*(.+?)(?:\n|$)', text)
    if going_match:
        result['going'] = going_match.group(1).strip()
    
    # Track
    track_match = re.search(r'賽道\s*[:：]\s*(.+?)(?:\n|$)', text)
    if track_match:
        result['track'] = track_match.group(1).strip()
    
    # Results table (try parsing the HTML table structure)
    tables = soup.find_all('table')
    for table in tables:
        header_text = table.get_text()
        if '名次' in header_text and '馬號' in header_text:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                cell_texts = [c.get_text(strip=True) for c in cells]
                if not cell_texts or not cell_texts[0].isdigit():
                    continue
                if len(cell_texts) >= 10:
                    entry = {
                        'pos': cell_texts[0],
                        'horse_no': cell_texts[1] if len(cell_texts) > 1 else '',
                        'horse_name': cell_texts[2] if len(cell_texts) > 2 else '',
                        'jockey': cell_texts[3] if len(cell_texts) > 3 else '',
                        'trainer': cell_texts[4] if len(cell_texts) > 4 else '',
                        'actual_weight': cell_texts[5] if len(cell_texts) > 5 else '',
                        'declared_weight': cell_texts[6] if len(cell_texts) > 6 else '',
                        'draw': cell_texts[7] if len(cell_texts) > 7 else '',
                        'margin': cell_texts[8] if len(cell_texts) > 8 else '',
                        'running_positions': cell_texts[9] if len(cell_texts) > 9 else '',
                        'finish_time': cell_texts[10] if len(cell_texts) > 10 else '',
                        'win_odds': cell_texts[11] if len(cell_texts) > 11 else '',
                    }
                    result['results'].append(entry)
            break
    
    # Incident report
    report_tag = soup.find(lambda t: t.name in ['div', 'table'] and '競賽事件報告' in t.get_text())
    if report_tag:
        container = report_tag.find_parent('table') or report_tag.find_parent('div')
        if container:
            result['incident_report'] = container.get_text(separator='\n', strip=True)
    
    return result


def format_race_output(data):
    """Format a single race result into markdown."""
    lines = [
        f"## 第 {data['race_no']} 場",
        f"- 班次: {data.get('class_info', '')}",
        f"- 路程: {data.get('distance', '')}",
        f"- 場地: {data.get('going', '')}",
        f"- 賽道: {data.get('track', '')}",
        f"- 分段時間: {data.get('sectional_times', '')}",
        "",
        "| 名次 | 馬號 | 馬名 | 騎師 | 練馬師 | 負磅 | 體重 | 檔位 | 距離 | 走位 | 時間 | 賠率 |",
        "|:---:|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|:---|:---:|:---:|",
    ]
    
    for r in data.get('results', []):
        if isinstance(r, dict):
            lines.append(f"| {r.get('pos','')} | {r.get('horse_no','')} | {r.get('horse_name','')} | {r.get('jockey','')} | {r.get('trainer','')} | {r.get('actual_weight','')} | {r.get('declared_weight','')} | {r.get('draw','')} | {r.get('margin','')} | {r.get('running_positions','')} | {r.get('finish_time','')} | {r.get('win_odds','')} |")
        elif isinstance(r, list) and len(r) >= 10:
            lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6] if len(r)>6 else ''} | {r[7] if len(r)>7 else ''} | {r[8] if len(r)>8 else ''} | {r[9] if len(r)>9 else ''} | {r[10] if len(r)>10 else ''} | {r[11] if len(r)>11 else ''} |")
    
    if data.get('incident_report'):
        lines.extend(["", "### 📋 競賽事件報告", data['incident_report']])
    
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description="Fast HKJC race results extractor")
    parser.add_argument("--base_url", help="Full HKJC results URL")
    parser.add_argument("--date", help="Race date in YYYY/MM/DD format")
    parser.add_argument("--venue", default="ST", help="ST or HV")
    parser.add_argument("--races", required=True, help="Race range e.g. '1-11' or '1,3,5'")
    parser.add_argument("--output_dir", required=True, help="Output directory")
    parser.add_argument("--method", default="auto", choices=["auto", "curl", "playwright", "bs4"],
                       help="Extraction method")
    args = parser.parse_args()
    
    # Determine date and venue
    if args.base_url:
        parsed = urlparse(args.base_url)
        qs = parse_qs(parsed.query)
        date = qs.get('racedate', [args.date])[0]
        venue = qs.get('Racecourse', [args.venue])[0]
    else:
        date = args.date
        venue = args.venue
    
    if not date:
        print("❌ Must provide either --base_url or --date")
        sys.exit(1)
    
    # Parse race range
    r_match = re.match(r'(\d+)-(\d+)', args.races)
    if r_match:
        race_list = list(range(int(r_match.group(1)), int(r_match.group(2)) + 1))
    else:
        race_list = [int(r.strip()) for r in args.races.split(',')]
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    venue_cn = '沙田' if venue == 'ST' else '跑馬地'
    date_parts = date.split('/')
    date_prefix = f"{date_parts[1]}-{date_parts[2]}" if len(date_parts) == 3 else "00-00"
    
    print(f"🏇 Fast extracting results for {date} {venue_cn} (Races {args.races})...")
    
    all_results = {}
    
    with tempfile.TemporaryDirectory() as temp_dir:
        for race_no in race_list:
            url = f"https://racing.hkjc.com/zh-hk/local/information/localresults?racedate={date}&Racecourse={venue}&RaceNo={race_no}"
            print(f"  📥 Race {race_no}...", end=" ", flush=True)
            
            try:
                html_path, html_text = fetch_page_html(url, temp_dir)
                
                # Try direct BS4 parsing first (fastest, no JS)
                result = extract_from_raw_html(html_text, race_no)
                
                if result and result.get('results'):
                    all_results[race_no] = result
                    print(f"✅ ({len(result['results'])} runners via BS4)")
                    continue
                
                # If BS4 fails (JS-rendered), try local Playwright hydration
                if args.method in ("auto", "playwright"):
                    result_pw = extract_via_playwright_local(html_path, race_no)
                    if result_pw and result_pw.get('type') == 'table':
                        table_data = result_pw['data']
                        result = {
                            'race_no': race_no,
                            'class_info': '',
                            'distance': '',
                            'going': table_data.get('meta', {}).get('going', ''),
                            'track': table_data.get('meta', {}).get('track', ''),
                            'sectional_times': '',
                            'results': table_data.get('results', []),
                            'incident_report': '',
                        }
                        all_results[race_no] = result
                        print(f"✅ ({len(result['results'])} runners via Playwright hydration)")
                        continue
                
                print("⚠️ No table data extracted")
                
            except Exception as e:
                print(f"❌ Error: {e}")
    
    # Write output
    output_file = os.path.join(args.output_dir, f"{date_prefix} {venue_cn} 全日賽果.md")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"# HKJC 賽果報告\n")
        f.write(f"**日期:** {date} | **馬場:** {venue_cn}\n\n")
        
        for rno in sorted(all_results.keys()):
            f.write(format_race_output(all_results[rno]))
            f.write("\n\n---\n\n")
    
    print(f"\n📊 Results saved to: {output_file}")
    print(f"   Extracted: {len(all_results)}/{len(race_list)} races")
    
    if len(all_results) == 0:
        print("\n⚠️ HKJC results page is client-side rendered (JavaScript SPA).")
        print("   The race result tables require JavaScript execution to load.")
        print("   Falling back to browser-based extraction may be needed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
