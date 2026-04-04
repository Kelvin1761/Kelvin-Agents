import asyncio
import json
import os
import time
from playwright.sync_api import sync_playwright
import lightpanda_utils

BASE_DIR = r"/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity"

def main():
    use_lightpanda, lp_proc = lightpanda_utils.start_lightpanda(BASE_DIR)
    captured = {}

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

            def handle_response(response):
                try:
                    if "json" in response.headers.get("content-type", "") and "racenet" in response.url:
                        body = response.json()
                        captured[response.url] = body
                        print(f"Captured: {response.url[:120]}")
                except Exception:
                    pass

            page.on("response", handle_response)
            
            url = "https://www.racenet.com.au/form-guide/horse-racing/randwick-20260404/widden-kindergarten-stakes-race-1/overview"
            print(f"Navigating to {url}")
            try:
                page.goto(url, wait_until='networkidle', timeout=60000)
            except Exception as e:
                print(f"Nav err: {e}")
            
            time.sleep(10)
            browser.close()
    finally:
        lightpanda_utils.stop_lightpanda(lp_proc)

    out_path = os.path.join(BASE_DIR, "_temporary_files", "lp_captured.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(captured, f, indent=2, ensure_ascii=False, default=str)
    print(f"Saved {len(captured)} requests to {out_path}")

if __name__ == '__main__':
    main()
