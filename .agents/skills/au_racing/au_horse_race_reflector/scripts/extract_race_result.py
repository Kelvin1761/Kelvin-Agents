import sys
import os
import json
import re
import argparse
from curl_cffi import requests
from playwright.sync_api import sync_playwright

def fetch_nuxt_data(url):
    print(f"Fetching {url} with curl_cffi...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    resp = requests.get(url, impersonate="chrome120", headers=headers, timeout=30)
    resp.raise_for_status()
    
    import time
    temp_html = os.path.abspath(f"racenet_temp_{int(time.time())}.html")
    with open(temp_html, 'w', encoding='utf-8') as f:
        f.write(resp.text)
    
    print("Evaluating Nuxt payload with Playwright locally...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file://{temp_html}")
        nuxt_data = page.evaluate("() => window.__NUXT__")
        browser.close()
        
    if os.path.exists(temp_html):
        os.remove(temp_html)
    return nuxt_data

def process_results(nuxt_data, target_event_slug=None, output_dir=None):
    # Search for the meeting data in the Nuxt payload
    data_list = nuxt_data.get('data', [])
    meeting_data = None
    
    # Fast lookup for meeting data in data_list
    for d in data_list:
        if isinstance(d, dict) and 'meeting' in d:
            meeting_data = d.get('meeting')
            break
            
    if not meeting_data:
        # Try finding in fetch keys if not in data_list
        fetch_data = nuxt_data.get('fetch', {})
        for k, v in fetch_data.items():
            if isinstance(v, dict) and 'meeting' in v:
                meeting_data = v.get('meeting')
                break

    if not meeting_data:
        print("No meeting data found in NUXT payload.")
        return
        
    meeting_date = meeting_data.get('meetingDateLocal', 'UnknownDate')
    # Format YYYY-MM-DD
    if 'T' in meeting_date:
        meeting_date = meeting_date.split('T')[0]
        
    venue = meeting_data.get('venue', {}).get('name', 'UnknownVenue')
    
    events = meeting_data.get('events', [])
    print(f"Found {len(events)} events in meeting.")
    
    for event in events:
        slug = event.get('slug')
        if target_event_slug and target_event_slug != 'all-races' and slug != target_event_slug:
            continue
            
        race_num = event.get('eventNumber', '?')
        track_cond = event.get('trackCondition', {}).get('overall', '?')
        
        filename = f"{meeting_date} {venue} Race {race_num} Result.txt"
        
        # If output_dir is provided, use it
        if output_dir:
            file_path = os.path.abspath(os.path.join(output_dir, filename))
        else:
            file_path = os.path.abspath(os.path.join(os.getcwd(), filename))
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"Meeting Date: {meeting_date}\n")
            f.write(f"Venue: {venue}\n")
            f.write(f"Race: {race_num}\n")
            f.write(f"Event Name: {event.get('name', '?')}\n")
            f.write(f"Distance: {event.get('distance', '?')}m\n")
            f.write(f"Track Condition: {track_cond}\n")
            f.write(f"Win Time: {event.get('winningTime', '?')}\n")
            f.write("="*60 + "\n")
            
            selections = event.get('selections', [])
            
            # Sort by finish position
            def get_pos(s):
                res = s.get('result', {})
                pos = res.get('finishPosition')
                return pos if (pos is not None and pos > 0) else 999
            
            selections.sort(key=get_pos)
            
            for sel in selections:
                if not isinstance(sel, dict):
                    continue
                    
                status = sel.get('statusAbv', 'UNK')
                num = sel.get('competitorNumber', '?')
                bar = sel.get('barrierNumber', '?')
                
                comp = sel.get('competitor') or {}
                name = comp.get('name', 'Unknown')
                
                jock_obj = sel.get('jockey') or {}
                jockey = jock_obj.get('name', 'Unknown')
                
                train_obj = sel.get('trainer') or {}
                trainer = train_obj.get('name', 'Unknown')
                
                weight = sel.get('weight', '?')
                sp = sel.get('startingPrice', '?')
                
                if status == 'SCR':
                    f.write(f"[SCR] {num}. {name} (J: {jockey}, T: {trainer}) - Scratched\n")
                    continue
                    
                res = sel.get('result') or {}
                pos = res.get('finishPosition', '?')
                margin = res.get('margin', 0)
                margin_str = f" {margin}L" if margin else ""
                
                pos_summary = res.get('competitorPositionSummary', []) or []
                in_run = []
                if pos_summary:
                    for p in pos_summary:
                        if isinstance(p, dict):
                            in_run.append(f"{p.get('positionText')}@{p.get('distanceText')}")
                    
                in_run_str = " ".join(in_run)
                
                f.write(f"[{pos}] {num}. {name} ({bar})\n")
                f.write(f"    J: {jockey} | T: {trainer} | Wt: {weight}kg | SP: ${sp}\n")
                if margin_str:
                    f.write(f"    Margin: {margin_str} | In-Run: {in_run_str}\n")
                f.write("-" * 40 + "\n")
                
        print(f"Results for Race {race_num} saved to {file_path}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Extract race results from Racenet.")
    parser.add_argument("url", help="Racenet result URL")
    parser.add_argument("--output_dir", help="Directory to save the result files")
    
    args = parser.parse_args()
    
    url = args.url
    output_dir = args.output_dir
    
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    # Identify the target slug from the URL
    # https://www.racenet.com.au/results/horse-racing/rosehill-gardens-20260314/all-races
    match = re.search(r'results/horse-racing/[^/]+/([^/]+)', url)
    target_slug = None
    if match:
        target_slug = match.group(1)
        
    nuxt_data = fetch_nuxt_data(url)
    process_results(nuxt_data, target_event_slug=target_slug, output_dir=output_dir)
