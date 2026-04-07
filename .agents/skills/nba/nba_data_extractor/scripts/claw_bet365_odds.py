import asyncio
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright

# Path Setup
SCRIPT_DIR = Path(__file__).parent
STATE_FILE = SCRIPT_DIR / "bet365_state.json"
OUTPUT_FILE = SCRIPT_DIR / "bet365_extracted_raw.json"

import subprocess

async def extract_bet365_odds():
    async with async_playwright() as p:
        
        print("[Claw] Launching Comet Natively with Remote Debugging...")
        comet_cmd = [
            "/Applications/Comet.app/Contents/MacOS/Comet",
            "--remote-debugging-port=9222",
            "--no-first-run",
            "--no-default-browser-check",
            "--user-data-dir=/tmp/comet_bet365_profile"
        ]
        
        # Launch Comet outside of Playwright to avoid Playwright's launch fingerprints
        proc = subprocess.Popen(comet_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await asyncio.sleep(5)
        
        print("[Claw] Connecting Playwright to Comet via CDP...")
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        
        all_data = {
            "source": "Bet365_Claw",
            "games_raw": [],
            "props_raw": {}
        }
        
        try:
            print("[Claw] Initializing SPA on Homepage...")
            await page.goto("https://www.bet365.com.au/", wait_until="domcontentloaded")
            
            print("\n" + "="*60)
            print("[!] COMET CDP RUN DETECTED!")
            print("[!] Please click 'Accept All Cookies' and navigate any Captchas IN COMET.")
            print("[!] You have 45 seconds to get past the loading screen.")
            print("="*60 + "\n")
            await page.wait_for_timeout(45000)
                
            print("[Claw] Navigating to Basketball Index...")
            await page.goto("https://www.bet365.com.au/#/AS/B18/", wait_until="domcontentloaded")
            await page.wait_for_timeout(6000)
                
            print("[Claw] Clicking into NBA...")
            await page.locator("text=NBA").first.click()
            await page.wait_for_timeout(8000)
            
            # Dump debug screenshot just in case
            await page.screenshot(path="/tmp/bet365_nba_debug.png", full_page=True)
            
            print("[Claw] Extracting Game Lines...")
            game_data = await page.evaluate("() => { const c = document.querySelector('.gl-MarketGroupContainer') || document.querySelector('.gl-MarketGroup'); return c ? c.innerText : null; }")
            all_data["games_raw"] = game_data.split('\\n') if game_data else []
            print(f"       -> Extracted {len(all_data['games_raw'])} lines of Game Data.")
            
            # Helper for Tabs
            async def grab_prop(prop_name):
                print(f"[Claw] Navigating to {prop_name}...")
                try:
                    await page.locator(f"text={prop_name}").first.click(timeout=5000)
                    await page.wait_for_timeout(4000)
                    data = await page.evaluate("() => { const c = document.querySelector('.gl-MarketGroupContainer') || document.querySelector('.gl-MarketGroup'); return c ? c.innerText : null; }")
                    lines = data.split('\\n') if data else []
                    print(f"       -> Extracted {len(lines)} lines of {prop_name} Data.")
                    return lines
                except Exception as e:
                    print(f"       -> Failed to click {prop_name}: {e}")
                    return []
            
            all_data["props_raw"]["Points"] = await grab_prop("Points O/U")
            all_data["props_raw"]["Assists"] = await grab_prop("Assists")
            all_data["props_raw"]["Rebounds"] = await grab_prop("Rebounds")
            all_data["props_raw"]["Threes"] = await grab_prop("Threes Made")
                
        except Exception as e:
            print(f"[Claw] Error occurred: {e}")
        finally:
            print("[Claw] Closing browser.")
            await browser.close()
            
        return all_data

def run():
    print("====================================")
    print("   NBA WONG CHOI - BET365 CLAW")
    print("====================================")
    data = asyncio.run(extract_bet365_odds())
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[Claw] Raw extraction saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    run()
