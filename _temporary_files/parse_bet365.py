from playwright.sync_api import sync_playwright
import time

def extract():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.bet365.com.au/#/AS/B18/")
        time.sleep(5)
        try:
            page.get_by_text("MIN Timberwolves").first.click()
            time.sleep(5)
            # Expand all tabs if needed or just get text
            text = page.evaluate("() => document.body.innerText")
            with open("2026-04-08 NBA Analysis/bet365_raw_MIN_IND.txt", "w") as f:
                f.write(text)
            print("OK")
        except Exception as e:
            print("ERROR", str(e))
        finally:
            browser.close()

if __name__ == "__main__":
    extract()
