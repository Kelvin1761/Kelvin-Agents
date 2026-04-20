#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
claw_discover_v5.py — Network Interception Discovery (DEPRECATED)

⚠️ DEPRECATED: This script was designed for Bet365 and is no longer the primary
extraction method. Use claw_sportsbet_odds.py instead.

Bypasses Cloudflare's DOM content blocking by intercepting
the pushnotification API response that contains all Event IDs.

Usage: python claw_discover_v5.py [--games MIL_DET,MIN_ORL,...]
"""
import asyncio
import json
import re
from playwright.async_api import async_playwright

CDP_PORT = 9222

# Default team → tag mapping (away team is key)
TEAM_TO_TAG = {
    "MIL Bucks": "MIL_DET",
    "DET Pistons": "MIL_DET",
    "MIN Timberwolves": "MIN_ORL",
    "ORL Magic": "MIN_ORL",
    "MEM Grizzlies": "MEM_DEN",
    "DEN Nuggets": "MEM_DEN",
    "POR Trail Blazers": "POR_SAS",
    "SAS Spurs": "POR_SAS", 
    "SA Spurs": "POR_SAS",
    "OKC Thunder": "OKC_LAC",
    "LAC Clippers": "OKC_LAC",
    "LA Clippers": "OKC_LAC",
    "DAL Mavericks": "DAL_PHX",
    "PHX Suns": "DAL_PHX",
    "ATL Hawks": "ATL_CLE",
    "CLE Cavaliers": "ATL_CLE",
}

async def main():
    async with async_playwright() as p:
        print("[Claw-v5] 🔌 Connecting to Comet via CDP...")
        browser = await p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
        page = next((pg for pg in browser.contexts[0].pages
                     if "sportsbet.com.au" in pg.url), None)
        if not page:
            print("[Claw-v5] ❌ No Sportsbet tab found")
            await browser.close()
            return

        game_responses = []

        async def handle_response(response):
            try:
                body = await response.text()
                if 'PA;NF=' in body:
                    game_responses.append(body)
                    print(f"[Claw-v5] 🎯 Intercepted game data ({len(body)} chars)")
            except:
                pass

        page.on("response", handle_response)

        # Reload to trigger fresh network requests
        print("[Claw-v5] 🔄 Reloading page to trigger API fetch...")
        await page.reload(wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(15000)

        page.remove_listener("response", handle_response)

        if not game_responses:
            print("[Claw-v5] ❌ No game data intercepted!")
            await browser.close()
            return

        best = max(game_responses, key=len)

        # Parse: |PA;NF={EVENT_ID};NA={GAME_NAME};
        pattern = r'\|PA;NF=(\d+);NA=([^;]+);'
        matches = re.findall(pattern, best)

        results = {}
        for event_id, game_name in matches:
            url = f"https://www.sportsbet.com.au/betting/basketball-us/nba/{event_id}"
            
            tag = None
            for team_key, tag_val in TEAM_TO_TAG.items():
                if team_key in game_name:
                    tag = tag_val
                    break
            if not tag:
                parts = game_name.split(" @ ")
                if len(parts) == 2:
                    away_abbr = parts[0].split()[0]
                    home_abbr = parts[1].split()[0]
                    tag = f"{away_abbr}_{home_abbr}"
                else:
                    tag = game_name.replace(" ", "")[:12]
            
            results[tag] = url

        with open(".agents.agents/tmp/sportsbet_game_urls.json", 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)

        print(f"\n{'='*60}")
        print(f"📋 DISCOVERED {len(results)} GAMES:")
        for tag, url in results.items():
            print(f"  ✅ {tag}: {url}")
        print(f"{'='*60}")
        print(f"\n✅ Saved to .agents.agents/tmp/sportsbet_game_urls.json")

        await browser.close()

asyncio.run(main())
