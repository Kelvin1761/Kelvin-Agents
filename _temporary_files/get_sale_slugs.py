import io
import sys
from curl_cffi import requests
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

url = "https://www.racenet.com.au/form-guide/horse-racing/sale-20260408/no1-car-wash-maiden-plate-race-1/overview"

resp = requests.get(url, impersonate="chrome120")
if resp.status_code == 200:
    with open("/tmp/temp2.html", "w", encoding="utf-8") as f:
        f.write(resp.text)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file:///tmp/temp2.html")
        
        nuxt_data = page.evaluate("() => window.__NUXT__")
        
        slugs = []
        if nuxt_data:
            apollo = nuxt_data.get('apollo', {}).get('horseClient', {})
            meeting_key = next((k for k in apollo.keys() if k.startswith("Meeting:")), None)
            if meeting_key:
                events = apollo[meeting_key].get('events', [])
                for e in events:
                    if isinstance(e, dict) and '__ref' in e:
                        event_id = e['__ref']
                        event_obj = apollo.get(event_id, {})
                        seo = event_obj.get('seo', {})
                        if seo.get('eventSlug'):
                            slugs.append(seo.get('eventSlug'))
        
        print(",".join(slugs))
        browser.close()
