os.environ.setdefault('PYTHONUTF8', '1')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import sys
import os
import json
import re
from curl_cffi import requests
from playwright.sync_api import sync_playwright

def get_race_slugs(url):
    print("Fetching overview...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    resp = requests.get(url, impersonate="chrome120", headers=headers, timeout=30)
    
    temp_html = ".agents.agents/tmp/overview.html"
    with open(temp_html, 'w') as f:
        f.write(resp.text)
        
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file://{temp_html}")
        nuxt_data = page.evaluate("() => window.__NUXT__")
        browser.close()
        
    apollo = nuxt_data.get('apollo', {}).get('horseClient', {})
    
    # Let's dump all meeting events
    print("Finding events...")
    events = []
    for k, v in apollo.items():
        if k.startswith("Event:") and v.get('eventSlug'):
             events.append((v.get('eventNumber'), v.get('eventSlug')))
             
    events.sort(key=lambda x: x[0] if x[0] else 99)
    for e in events:
         print(e)
         
get_race_slugs("https://www.racenet.com.au/form-guide/horse-racing/caulfield-heath-20260304/briga-fliedner-2026-lady-of-racing-finalist-race-1/overview")
