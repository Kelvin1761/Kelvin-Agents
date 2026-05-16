import asyncio
import sys
from playwright.async_api import async_playwright

# Ensure UTF-8 output for Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://racing.hkjc.com/zh-hk/local/information/horse?horseid=HK_2020_E486")
        # Wait for the horse name to appear in the table
        await page.wait_for_selector("td:has-text('浪漫勇士')")
        title = await page.title()
        print(f"Title: {title}")
        
        # Check if we can find sire info
        sire_element = await page.query_selector("td:has-text('父系') + td + td")
        if sire_element:
            sire = await sire_element.inner_text()
            print(f"Sire: {sire.strip()}")
        
        await browser.close()

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except Exception as e:
        print(f"Error: {e}")
