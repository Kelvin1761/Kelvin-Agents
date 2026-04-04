import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import os
import time
from playwright.sync_api import sync_playwright
import lightpanda_utils

BASE_DIR = r"/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity"
# USE REAL DATE FOR 2024
MEETING_SLUG = "randwick-20240406"
EVENT_SLUG = "widden-kindergarten-stakes-race-1"
RACE_NUM = 1
DATE_STR = "2026-04-04"  # output folder stays 2026 to match our system
VENUE_NAME = "Randwick"

def process_selections(nuxt_data, f_rc, f_fg):
    form_data = nuxt_data.get('fetch', {})
    form_key = next((k for k in form_data.keys() if k.startswith('FormGuidePrint')), None)
    if not form_key: return None
    event_data = form_data.get(form_key, {})
    selections = event_data.get('selections', [])
    if not selections: return None
    
    meta = {'distance': event_data.get('distance', '?')}
    for sel in selections:
        num = sel.get('competitorNumber', '?')
        comp = sel.get('competitor', {}) or {}
        name = comp.get('name', 'Unknown')
        f_rc.write(f"{num}. {name}\n")
        f_fg.write(f"[{num}] {name}\n\n")
    return meta

def main():
    print(f"AU Race Extractor — Testing REAL URL: {MEETING_SLUG}")
    use_lightpanda, lp_proc = lightpanda_utils.start_lightpanda(BASE_DIR)
    try:
        with sync_playwright() as p:
            if use_lightpanda: browser = p.chromium.connect_over_cdp("ws://127.0.0.1:9222")
            else: browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
            
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            
            output_dir = os.path.join(BASE_DIR, "Architeve Race Analysis", f"{DATE_STR} {VENUE_NAME} Race 1-1")
            os.makedirs(output_dir, exist_ok=True)
            mm_dd = DATE_STR[5:]
            rc_file = os.path.join(output_dir, f"{mm_dd} Race 1-1 Racecard.md")
            fg_file = os.path.join(output_dir, f"{mm_dd} Race 1-1 Formguide.md")
            
            with open(rc_file, 'w', encoding='utf-8') as f_rc, open(fg_file, 'w', encoding='utf-8') as f_fg:
                print_url = f"https://www.racenet.com.au/form-guide/horse-racing/print?meetingSlug={MEETING_SLUG}&eventSlug={EVENT_SLUG}&printSlug=print-form"
                try:
                    page.goto(print_url, wait_until='domcontentloaded', timeout=40000)
                    event_nuxt = None
                    for i in range(15):
                        time.sleep(1)
                        try:
                            event_nuxt = page.evaluate("() => window.__NUXT__")
                            if event_nuxt: break
                        except: pass
                    
                    if not event_nuxt:
                        print(f"  [ERROR] NUXT not found! Still failing on {MEETING_SLUG}")
                    else:
                        meta = process_selections(event_nuxt, f_rc, f_fg)
                        if meta: print(f"  ✓ Race {RACE_NUM} Extracted.")
                except Exception as e: print(f"  [ERROR] {e}")
            browser.close()
    finally:
        lightpanda_utils.stop_lightpanda(lp_proc)

if __name__ == '__main__': main()
