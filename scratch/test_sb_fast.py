import asyncio
from playwright.async_api import async_playwright

async def main():
    url = "https://www.sportsbet.com.au/betting/basketball-us/nba"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        game_url = "https://www.sportsbet.com.au/betting/basketball-us/nba/indiana-pacers-at-brooklyn-nets-10339077"
        
        context = await browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = await context.new_page()
        
        print("Navigating...")
        await page.goto(game_url, wait_until="domcontentloaded")
        await asyncio.sleep(5)
        
        # Click "Player Props"
        print("Looking for Player Props tab...")
        try:
            tabs = await page.locator("div.navItem_f1n50o3f, div, span").all_inner_texts()
            # print([t for t in tabs if "Prop" in t])
            # Just click it if it exists
            await page.locator("text='Player Props'").first.click(timeout=3000)
            await asyncio.sleep(3)
        except Exception as e:
            print(f"Tab click failed: {e}")
            
        print("Dumping entire body to see market syntax...")
        text = await page.evaluate("() => document.body.innerText")
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        
        assists_lines = [l for l in lines if "Assist" in l or "Rebound" in l or "Three" in l]
        print("Matched Lines:")
        print(assists_lines[:20]) # Print first 20

        await browser.close()

asyncio.run(main())
