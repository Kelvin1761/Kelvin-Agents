import asyncio
from playwright.async_api import async_playwright

async def main():
    game_url = "https://www.sportsbet.com.au/betting/basketball-us/nba/indiana-pacers-at-brooklyn-nets-10339077"
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        print("Navigating to Sportsbet...")
        await page.goto(game_url)
        await asyncio.sleep(4)
        print("Finding window state variables...")
        keys = await page.evaluate('''() => {
            return Object.keys(window).filter(k => k.includes("STATE") || k.includes("INIT") || k.includes("DATA"));
        }''')
        print(f"Potential state variables: {keys}")
        await browser.close()

asyncio.run(main())
