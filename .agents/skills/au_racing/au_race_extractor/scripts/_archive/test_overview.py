import sys
import os
import json
import re
from curl_cffi import requests
from playwright.sync_api import sync_playwright

url = "https://www.racenet.com.au/form-guide/horse-racing/caulfield-heath-20260304/briga-fliedner-2026-lady-of-racing-finalist-race-1/overview"

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

with open('nuxt_overview.json', 'w') as f:
     json.dump(nuxt_data, f)
     
print("Saved nuxt_overview.json")
