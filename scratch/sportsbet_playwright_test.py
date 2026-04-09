import asyncio
from playwright.async_api import async_playwright
import json

async def intercept_sportsbet_api(url):
    print(f"Opening Sportsbet to intercept API for: {url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        extracted_data = None
        
        # Setup Network Interceptor
        async def handle_response(response):
            nonlocal extracted_data
            if "/apigw/" in response.url or "graphql" in response.url:
                try:
                    if response.request.method == "OPTIONS": return
                    
                    data = await response.json()
                    str_data = json.dumps(data)
                    # We look for "Points" or "Rebounds" dynamically inside API responses
                    if "Player Points" in str_data or "Points" in str_data or "Rebounds" in str_data:
                        print(f"\\n[✅ JACKPOT!] Intercepted API Response: {response.url[:100]}...")
                        extracted_data = data
                except Exception:
                    pass

        page.on("response", handle_response)
        
        # We only really need domcontentloaded + a few seconds to let APIs fire
        await page.goto(url, wait_until='domcontentloaded')
        await page.wait_for_timeout(3000) # Give 3 seconds for APIs to settle
        
        if extracted_data:
            print("\\n--- PROOF OF PLAYER PROPS EXTRACTION ---")
            
            # Simple recursive search
            def find_markets(obj):
                markets = []
                if isinstance(obj, dict):
                    if obj.get('name') and 'selections' in obj:
                        markets.append(obj)
                    for k, v in obj.items():
                        markets.extend(find_markets(v))
                elif isinstance(obj, list):
                    for item in obj:
                        markets.extend(find_markets(item))
                return markets
                
            found_markets = find_markets(extracted_data)
            
            count = 0
            for m in found_markets:
                name = m.get('name', '')
                if 'Points' in name or 'Rebounds' in name or 'Assists' in name:
                    if count >= 8: break
                    count += 1
                    print(f"\\nMarket: {name}")
                    for sel in m.get('selections', [])[:4]:
                        price_obj = sel.get('price', {})
                        price = price_obj.get('winPrice') or price_obj.get('handicap') or 'N/A'
                        print(f"  - {sel.get('name')}: @ {price}")
            print("\\n(And many more...)\\n")
        else:
            print("Did not intercept the props API. Playwright might have timed out.")

        await browser.close()

if __name__ == "__main__":
    url = "https://www.sportsbet.com.au/betting/basketball-us/nba/chicago-bulls-at-washington-wizards-10345076"
    asyncio.run(intercept_sportsbet_api(url))
