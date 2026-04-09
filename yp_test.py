from playwright.sync_api import sync_playwright
import time
import json

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        print("Navigating to YellowPages...")
        try:
            page.goto('https://www.yellowpages.com.au/search/listings?locationArea=Australia&what=gun+shop', timeout=30000, wait_until='networkidle')
            print("Page loaded. Title:", page.title())
            # Let's see if we see "Verify you are human"
            if 'security check' in page.content().lower() or 'cloudflare' in page.content().lower():
                print("Cloudflare detected.")
            else:
                listings = page.query_selector_all('.listing-name')
                print(f"Found {len(listings)} listings on first page via class .listing-name")
                
                # Try finding them via xpath or generic anchor
                links = page.query_selector_all('a')
                gun_count = sum(1 for l in links if l.inner_text() and 'gun' in l.inner_text().lower())
                print("Anchor tags mentioning 'gun':", gun_count)
        except Exception as e:
            print("Exception:", e)
        browser.close()

run()
