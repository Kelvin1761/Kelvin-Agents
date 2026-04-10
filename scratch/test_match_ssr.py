import asyncio
from playwright.async_api import async_playwright
import json
import sys

async def check_match_page(url):
    print(f"Opening Sportsbet Match Page: {url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        await page.goto(url, wait_until='domcontentloaded')
        await page.wait_for_timeout(3000)
        
        # Check window state variables commonly used by Vue/React
        state = await page.evaluate("""() => {
            return {
                nuxt: typeof window.__NUXT__ !== 'undefined',
                next: typeof window.__NEXT_DATA__ !== 'undefined',
                initialState: typeof window.INITIAL_STATE !== 'undefined',
                apollo: typeof window.__APOLLO_STATE__ !== 'undefined'
            }
        }""")
        
        print("SSR State objects found:", state)
        
        if state['nuxt']:
            print("Found __NUXT__. Extracting...")
            data = await page.evaluate("() => window.__NUXT__")
            with open("scratch/nuxt_dump.json", "w") as f:
                json.dump(data, f)
            print("Dumped to nuxt_dump.json")
            
        elif state['initialState']:
            print("Found INITIAL_STATE. Extracting...")
            data = await page.evaluate("() => window.INITIAL_STATE")
            with open("scratch/initial_dump.json", "w") as f:
                json.dump(data, f)
            print("Dumped to initial_dump.json")

        await browser.close()

if __name__ == "__main__":
    url = "https://www.sportsbet.com.au/betting/basketball-us/nba/indiana-pacers-at-brooklyn-nets-10339077"
    asyncio.run(check_match_page(url))
