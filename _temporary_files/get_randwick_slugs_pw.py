import asyncio
from playwright.async_api import async_playwright
import re
import sys

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        print("Navigating to Randwick overview page...")
        await page.goto("https://www.racenet.com.au/form-guide/horse-racing/randwick-20260404", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)
        html = await page.content()
        await browser.close()
        
        links = re.findall(r'randwick-20260404/([^/"\']+-\d+)/', html)
        unique_slugs = sorted(set(links))
        print(f"Found {len(unique_slugs)} slugs:")
        for slug in unique_slugs:
            print(f"  {slug}")

        if not unique_slugs:
            links = re.findall(r'randwick-20260404/([^/"\']+)', html)
            unique_slugs = sorted(set(links))
            print(f"Found {len(unique_slugs)} slugs with alternative regex:")
            for slug in unique_slugs:
                if 'overview' not in slug and 'form' not in slug:
                    print(f"  {slug}")

if __name__ == '__main__':
    asyncio.run(main())
