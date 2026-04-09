import asyncio
from playwright.async_api import async_playwright

async def main():
    url = "https://www.sportsbet.com.au/betting/basketball-us/nba/indiana-pacers-at-brooklyn-nets-10339077"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(4)
        
        print("Dumping all spans with 'Assist':")
        spans = await page.locator("span:has-text('Assist')").all_inner_texts()
        for i, text in enumerate(spans):
            print(f"{i}: {text.strip()}")
            
        print("\nDumping all divs with 'Assist':")
        divs = await page.locator("div:has-text('Assist')").all_inner_texts()
        for i, text in enumerate(set([d.strip().split('\n')[0] for d in divs if d])):
            if "Assist" in text:
                print(f"{i}: {text}")

        await browser.close()

asyncio.run(main())
