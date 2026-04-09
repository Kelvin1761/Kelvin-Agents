#!/usr/bin/env python3
"""
claw_sportsbet_odds.py — Sportsbet NBA Zero-Navigation Extractor V1
Replaces Bet365 extraction via DOM scraping (bypassing GraphQL/Apollo SSR limitations)
"""

import sys
import json
import asyncio
import argparse
import urllib.request
import re
from datetime import datetime
from playwright.async_api import async_playwright

class SportsbetNBAExtractor:
    def __init__(self, output_file="/tmp/nba_sportsbet_odds_latest.json"):
        self.competition_url = "https://www.sportsbet.com.au/apigw/sportsbook-sports/Sportsbook/Sports/Competitions/6927"
        self.base_event_url = "https://www.sportsbet.com.au/betting/basketball-us/nba"
        self.output_file = output_file

    def fetch_daily_matches(self):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔍 正在探索 Sportsbet 當日 NBA 賽事...")
        req = urllib.request.Request(
            self.competition_url,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        try:
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode('utf-8'))
                events = data.get('events', [])
                
                urls = []
                for event in events:
                    raw_name = event.get('name', '')
                    event_id = event.get('id', '')
                    if not raw_name or not event_id:
                        continue
                        
                    slug = re.sub(r'[^a-z0-9]+', '-', raw_name.lower()).strip('-')
                    full_url = f"{self.base_event_url}/{slug}-{event_id}"
                    urls.append((raw_name, full_url))
                
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 成功發現 {len(urls)} 場 NBA 賽程！")
                return urls
        except Exception as e:
            print(f"❌ 獲取賽事名單失敗: {e}")
            return []

    async def traverse_and_extract(self, matches):
        all_odds_data = {}
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 啟動 Playwright DOM 提取引擎 (無頭模式)...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            for idx, (game_name, url) in enumerate(matches, 1):
                print(f"\n[{idx}/{len(matches)}] 🕵️ 正在提取賽事: {game_name}")
                
                extracted_for_game = {}
                
                try:
                    await page.goto(url, wait_until='domcontentloaded')
                    await asyncio.sleep(4)
                except Exception as e:
                    print(f"   ⚠️ 載入頁面超時或錯誤: {e}")
                    continue

                # 1. 強制打開所有主目錄
                for cat in ["Player Points", "Player Rebounds", "Player Assists", "Player Threes"]:
                    try:
                        cat_headers = await page.locator(f"span:has-text('{cat} Markets')").all()
                        for header in cat_headers: 
                            await header.click(timeout=800)
                            await asyncio.sleep(0.3)
                    except: pass

                await asyncio.sleep(1)

                # 2. 強制打開所有 Milestone 子目錄
                try:
                    sub_headers = await page.locator("span:has-text('To Score '), span:has-text('To Record '), span:has-text('Made Three')").all()
                    for header in sub_headers[:25]: # 略作限制以防超時
                        await header.click(timeout=800)
                        await asyncio.sleep(0.2)
                except: pass
                
                await asyncio.sleep(2)

                # 3. 直取 DOM 字串並解析
                text = await page.evaluate("() => document.body.innerText")
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                
                current_market = "Unknown"
                captured_count = 0
                for i, line in enumerate(lines):
                    # 辨認當前盤口類別
                    if line.startswith("To Score ") or line.startswith("To Record ") or "Made Three" in line:
                        current_market = line
                        continue
                        
                    try:
                        price = float(line)
                        # Sportsbet 有時會喺名同賠率中間攝句 "Last 5: LLLWW"
                        player_name = lines[i-1] if "Last 5" not in lines[i-1] else lines[i-2]
                        
                        # 排除垃圾字元
                        if len(player_name) > 3 and "Market" not in player_name and "Betting" not in player_name and "Win " not in player_name:
                            if current_market not in extracted_for_game:
                                extracted_for_game[current_market] = {}
                            extracted_for_game[current_market][player_name] = price
                            captured_count += 1
                    except ValueError:
                        continue
                        
                if extracted_for_game:
                    print(f"   ✅ 成功提取 {captured_count} 個盤口數據！")
                    all_odds_data[game_name] = extracted_for_game
                else:
                    print(f"   ⚠️ 失敗：未能提取到數據。")

            await browser.close()
            
        return all_odds_data

    def format_to_bet365_schema(self, raw_data):
        # Bet365 schema output mapping for downstream compatibility
        bet365_json = {
            "extraction_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "player_props": {
                "Points": {},
                "Rebounds": {},
                "Assists": {},
                "Threes Made": {}
            }
        }
        
        for game_name, markets in raw_data.items():
            for market_str, players in markets.items():
                category = None
                if "Points" in market_str: category = "Points"
                elif "Rebounds" in market_str: category = "Rebounds"
                elif "Assists" in market_str: category = "Assists"
                elif "Made Threes" in market_str: category = "Threes Made"
                
                if not category: continue
                
                # Extract integer threshold out of "To Score 15+ Points" -> "15"
                # Or "2+ Made Threes" -> "2"
                import re
                match = re.search(r'(\d+)\+', market_str)
                if not match: continue
                threshold = match.group(1)
                
                for player, odds in players.items():
                    if player not in bet365_json["player_props"][category]:
                        bet365_json["player_props"][category][player] = {}
                    
                    try:
                        # Only keep valid odds digits
                        if isinstance(odds, (float, int)):
                            if "lines" not in bet365_json["player_props"][category][player]:
                                bet365_json["player_props"][category][player]["lines"] = {}
                            bet365_json["player_props"][category][player]["lines"][threshold] = odds
                    except:
                        pass
                        
        return bet365_json

    def run(self):
        matches = self.fetch_daily_matches()
        if not matches:
            print("❌ 沒有發現任何 NBA 賽事，程式終止。")
            return
            
        print(f"\n--- 開始逐場提取 Player Props ---")
        odds_data = asyncio.run(self.traverse_and_extract(matches))
        
        bet365_formatted = self.format_to_bet365_schema(odds_data)
        
        try:
            import os
            os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(bet365_formatted, f, ensure_ascii=False, indent=4)
            print(f"\n🎉 完美！Sportsbet 賠率已轉化為 Bet365 格式並儲存至: {self.output_file}")
            
        except Exception as e:
            print(f"\n❌ 儲存 JSON 失敗: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # Output defaults directly to where generate_nba_reports expects it
    parser.add_argument('--output', default='.agents.agents/tmp/bet365_all_raw_data.json', help='Output JSON path')
    args = parser.parse_args()
    
    # Auto convert path fixing Antigravity common mistake
    out_path = args.output.replace('.agents.agents/tmp/', '/tmp/') if '.agents.agents/tmp/' in args.output else args.output
    out_path = out_path.replace('.agents/tmp/', '/tmp/') if '.agents/tmp/' in out_path else out_path
    
    extractor = SportsbetNBAExtractor(output_file=out_path)
    extractor.run()
