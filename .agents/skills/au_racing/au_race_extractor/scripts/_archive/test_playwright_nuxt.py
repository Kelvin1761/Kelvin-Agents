import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright
import json

def get_nuxt_data():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Load the local HTML file we fetched via curl_cffi
        page.goto('file://./.agents/skills/au_race_extractor/scripts/racenet_print_curl.html')
        
        # Extract the global window.__NUXT__ object
        nuxt_data = page.evaluate('() => window.__NUXT__')
        
        print("Success! Keys in Nuxt data:", nuxt_data.keys() if nuxt_data else "None")
        
        with open('./.agents/skills/au_race_extractor/scripts/nuxt.json', 'w') as f:
            json.dump(nuxt_data, f, indent=2)
            
        print("Saved to nuxt.json")
        browser.close()

if __name__ == '__main__':
    get_nuxt_data()
