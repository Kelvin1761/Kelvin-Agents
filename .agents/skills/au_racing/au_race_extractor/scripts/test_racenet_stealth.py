from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

url = "https://www.racenet.com.au/form-guide/horse-racing/caulfield-heath-20260304/briga-fliedner-2026-lady-of-racing-finalist-race-1/overview"

def main():
    try:
        with Stealth().use_sync(sync_playwright()) as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
            
            # Handle dialogs automatically
            page.on("dialog", lambda dialog: dialog.dismiss())
            
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=15000)
                page.wait_for_timeout(3000)
            except Exception as e:
                print("Timeout or error:", e)
            
            html = page.content()
            browser.close()
            
            print("Length:", len(html))
            print("Contains title?", "Racenet" in html)
            print("Contains '10 Results'?", "10 Results" in html)
            print("Contains 'Access Denied'?", "Access Denied" in html or "Cloudflare" in html or "ERROR" in html)
            
            with open('/Users/imac/Desktop/Drive/Antigravity/racenet_stealth.html', 'w') as f:
                f.write(html)
    except Exception as e:
        print("Stealth error:", e)

if __name__ == "__main__":
    main()
