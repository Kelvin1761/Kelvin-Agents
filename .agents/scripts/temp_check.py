import os
import tempfile
from curl_cffi import requests
from playwright.sync_api import sync_playwright

def get_meetings_for_date(date_str):
    url = f"https://www.racenet.com.au/results/horse-racing/{date_str}"
    r = requests.get(url, impersonate="chrome120")
    
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(r.text)
        temp_path = f.name
        
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"file://{temp_path}")
            
            # The __NUXT__ object has all the data
            nuxt = page.evaluate("() => window.__NUXT__")
            browser.close()
            
            # Navigate Nuxt structure to find meetings
            # Usually it's in nuxt.data or nuxt.state
            # Let's just print the keys to see
            return nuxt
    finally:
        os.remove(temp_path)

if __name__ == "__main__":
    nuxt = get_meetings_for_date("2026-04-25")
    # print keys
    print("Keys in NUXT:", nuxt.keys() if nuxt else "None")
