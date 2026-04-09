import asyncio
from playwright.async_api import async_playwright

async def main():
    game_url = "https://www.sportsbet.com.au/betting/basketball-us/nba/indiana-pacers-at-brooklyn-nets-10339077"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0")
        page = await context.new_page()
        await page.goto(game_url, wait_until="domcontentloaded")
        await asyncio.sleep(4)
        
        text = await page.evaluate("() => document.body.innerText")
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        
        for i, line in enumerate(lines):
            if "To Record 8+ Rebounds" in line or "To Record 6+ Assists" in line:
                start = max(0, i-5)
                end = min(len(lines), i+15)
                print(f"\n--- Surrounding {line} ---")
                print("\n".join(lines[start:end]))

        await browser.close()

asyncio.run(main())
