import asyncio
from playwright.async_api import async_playwright

async def main():
    url = "https://www.sportsbet.com.au/betting/basketball-us/nba"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Let's hit the main game URL
        game_url = "https://www.sportsbet.com.au/betting/basketball-us/nba/chicago-bulls-at-washington-wizards-10345076"
        page = await browser.new_page()
        await page.goto(game_url, wait_until="networkidle")
        await asyncio.sleep(3)
        
        # Click "Player Props" tab
        try:
            print("Clicking 'Player Props'...")
            await page.locator("div.navItem_f1n50o3f >> text='Player Props'").first.click(timeout=3000)
        except:
            try:
                await page.locator("text='Player Props'").first.click(timeout=3000)
            except:
                print("Failed to click Player Props tab")
        
        await asyncio.sleep(3)
        
        # Check accordion headers
        print("\nDumping headers related to 'Player':")
        headers = await page.locator("span").all_inner_texts()
        player_headers = set([h.strip() for h in headers if "Player" in h or "Markets" in h])
        print(player_headers)

        await browser.close()

asyncio.run(main())
