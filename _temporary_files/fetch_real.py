import asyncio
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
            
            # Use real date for widden kindergarten stakes 
            url = "https://www.racenet.com.au/form-guide/horse-racing/randwick-20240406"
            print(f"Navigating to {url}")
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=40000)
            except Exception as e:
                print(f"Nav error: {e}")
            
            time.sleep(5)
            html = page.content()
            out_path = os.path.join(BASE_DIR, "_temporary_files", "randwick_html_real.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"Saved HTML to {out_path} length {len(html)}")
            
            browser.close()
    finally:
        lightpanda_utils.stop_lightpanda(lp_proc)

if __name__ == '__main__':
    main()
