import os
import time
from playwright.sync_api import sync_playwright
import lightpanda_utils

BASE_DIR = r"/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity"

def main():
    use_lightpanda, lp_proc = lightpanda_utils.start_lightpanda(BASE_DIR)
    
    try:
        with sync_playwright() as p:
            if use_lightpanda:
                browser = p.chromium.connect_over_cdp("ws://127.0.0.1:9222")
            else:
                browser = p.chromium.launch(
                    headless=True,
                    args=['--ignore-certificate-errors', '--disable-blink-features=AutomationControlled']
                )
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            
            # test a print URL with "race-2" as slug
            url = "https://www.racenet.com.au/form-guide/horse-racing/print?meetingSlug=randwick-20260404&eventSlug=race-2&printSlug=print-form"
            print(f"Navigating to {url}")
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=30000)
                nuxt_data = None
                for i in range(10):
                    time.sleep(1)
                    try:
                        nuxt_data = page.evaluate("() => window.__NUXT__")
                        if nuxt_data:
                            break
                    except Exception:
                        pass
                
                if nuxt_data:
                    form_data = nuxt_data.get('fetch', {})
                    form_key = next((k for k in form_data.keys() if k.startswith('FormGuidePrint')), None)
                    event_data = form_data.get(form_key, {}) if form_key else {}
                    print("Found data!")
                    print("Class:", event_data.get("class"))
                    print("Distance:", event_data.get("distance"))
                else:
                    print("No NUXT data!")
            except Exception as e:
                print(f"Error: {e}")
            
            browser.close()
    finally:
        lightpanda_utils.stop_lightpanda(lp_proc)

if __name__ == '__main__':
    main()
