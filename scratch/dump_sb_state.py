import asyncio
import json
from playwright.async_api import async_playwright

async def main():
    game_url = "https://www.sportsbet.com.au/betting/basketball-us/nba/indiana-pacers-at-brooklyn-nets-10339077"
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(game_url)
        await asyncio.sleep(4)
        print("Dumping __PRELOADED_STATE__ ...")
        state = await page.evaluate("() => JSON.stringify(window.__PRELOADED_STATE__)")
        with open("scratch/sb_preloaded.json", "w") as f:
            f.write(state)
        await browser.close()
        print("Done.")

asyncio.run(main())
