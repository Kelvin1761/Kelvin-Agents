import asyncio
from playwright.async_api import async_playwright
import json

async def check_ssr_state(url):
    print(f"Opening Sportsbet: {url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        await page.goto(url, wait_until='networkidle')
        await page.wait_for_timeout(2000)
        
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
        
        # If apollo exists, let's grab the keys
        if state['apollo']:
            apollo_keys = await page.evaluate("() => Object.keys(window.__APOLLO_STATE__).length")
            print(f"APOLLO STATE has {apollo_keys} keys.")
            
        await browser.close()

if __name__ == "__main__":
    url = "https://www.sportsbet.com.au/betting/basketball-us/nba"
    asyncio.run(check_ssr_state(url))
