import asyncio
import json
import os
from playwright.async_api import async_playwright

BASE_DIR = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"}
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = await context.new_page()

        slugs = []
        async def handle_response(response):
            try:
                ct = response.headers.get("content-type", "")
                if "json" in ct and "graphql" in response.url:
                    body = await response.json()
                    if type(body) == list:
                        for item in body:
                            if "data" in item and "meeting" in item["data"]:
                                for raw_event in item["data"]["meeting"].get("events", []):
                                    es = raw_event.get("seo", {}).get("eventSlug")
                                    if es and es not in slugs:
                                        slugs.append(es)
                    elif type(body) == dict:
                        if "data" in body and "meeting" in body["data"]:
                            for raw_event in body["data"]["meeting"].get("events", []):
                                es = raw_event.get("seo", {}).get("eventSlug")
                                if es and es not in slugs:
                                    slugs.append(es)
            except Exception as e:
                pass

        page.on("response", handle_response)
        
        url = "https://www.racenet.com.au/form-guide/horse-racing/sale-20260408/no1-car-wash-maiden-plate-race-1/overview"
        try:
            await page.goto(url, wait_until="networkidle", timeout=15000)
        except Exception:
            pass
            
        await asyncio.sleep(2)
        print("SLUGS_FOUND: " + ",".join(slugs))
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
