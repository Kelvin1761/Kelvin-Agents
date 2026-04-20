import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import json
import re
from curl_cffi import requests
from playwright.sync_api import sync_playwright

def fetch_nuxt_data(url, temp_html_path=".agents.agents/tmp/racenet_sectionals.html"):
    print(f"Fetching {url}... ")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    resp = requests.get(url, impersonate="chrome120", headers=headers, timeout=30)
    resp.raise_for_status()
    
    with open(temp_html_path, 'w') as f:
        f.write(resp.text)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file://{temp_html_path}")
        nuxt_data = page.evaluate("() => window.__NUXT__")
        browser.close()
        
    return nuxt_data

url = "https://www.racenet.com.au/form-guide/horse-racing/caulfield-heath-20260304/briga-fliedner-2026-lady-of-racing-finalist-race-1/sectionals"
nuxt = fetch_nuxt_data(url)

with open("./.agents/skills/au_race_extractor/scripts/sectionals_nuxt.json", "w") as f:
    json.dump(nuxt, f, indent=2)

print("Saved sectionals payload to sectionals_nuxt.json")
