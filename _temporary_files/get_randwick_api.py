import asyncio
import json
import os
from playwright.async_api import async_playwright

BASE_DIR = r"/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity"

async def main():
    captured = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            # extra headers to mimic real browser better
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        # Add stealth script
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = await context.new_page()

        async def handle_response(response):
            try:
                ct = response.headers.get("content-type", "")
                if "json" in ct and "racenet.com.au" in response.url:
                    body = await response.json()
                    captured[response.url] = body
                    print(f"Captured API: {response.url[:120]}")
            except Exception:
                pass

        page.on("response", handle_response)
        
        url = "https://www.racenet.com.au/form-guide/horse-racing/randwick-20260404/widden-kindergarten-stakes-race-1/overview"
        print(f"Navigating to {url}")
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"Navigation timeout: {e}")
            
        await asyncio.sleep(5)
        await browser.close()

    out_path = os.path.join(BASE_DIR, "_temporary_files", "randwick_debug.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(captured, f, indent=2, ensure_ascii=False, default=str)
    print(f"Saved {len(captured)} requests to {out_path}")

if __name__ == "__main__":
    asyncio.run(main())
