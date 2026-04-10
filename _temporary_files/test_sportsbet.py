import asyncio
import json
import urllib.request
import re
from datetime import datetime
from playwright.async_api import async_playwright

class SportsbetNBAExtractor:
    def __init__(self):
        self.competition_url = "https://www.sportsbet.com.au/apigw/sportsbook-sports/Sportsbook/Sports/Competitions/6927"
        self.base_event_url = "https://www.sportsbet.com.au/betting/basketball-us/nba"
        self.output_file = ".agents/tmp/nba_sportsbet_odds_latest.json"

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

    async def traverse_and_intercept(self, matches):
        all_odds_data = {}
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 啟動 Playwright 攔截引擎 (無頭模式)...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            for idx, (game_name, url) in enumerate(matches, 1):
                print(f"\n[{idx}/{len(matches)}] 🕵️ 正在入侵賽事: {game_name}")
                print(f"   🔗 {url}")
                
                extracted_for_game = {}
                
                async def intercept(response):
                    nonlocal extracted_for_game
                    if "/apigw/" in response.url or "graphql" in response.url:
                        if response.request.method == "OPTIONS": return
                        try:
                            data = await response.json()
                            str_data = json.dumps(data)
                            
                            with open(f".agents/tmp/debug_{game_name.replace(' ', '_')}.json", "a") as f:
                                f.write(str_data + "\n")
                                
                            if "Player Points" in str_data or "Match Betting" in str_data or "selections" in str_data:
                                extracted_for_game.update(self._parse_markets(data))
                        except Exception:
                            pass

                page.on("response", intercept)
                
                try:
                    await page.goto(url, wait_until='domcontentloaded')
                    await page.wait_for_timeout(4000)
                except Exception as e:
                    print(f"   ⚠️ 載入頁面超時或錯誤: {e}")
                
                page.remove_listener("response", intercept)
                
                if extracted_for_game:
                    print(f"   ✅ 成功攔截 {len(extracted_for_game)} 種類別嘅盤口！")
                    all_odds_data[game_name] = extracted_for_game
                else:
                    print(f"   ⚠️ 失敗：未能攔截到 Player Props 數據。")

            await browser.close()
            
        return all_odds_data

    def _parse_markets(self, raw_data):
        structured = {}
        
        def find_markets(obj):
            markets = []
            if isinstance(obj, dict):
                if obj.get('name') and 'selections' in obj and isinstance(obj['selections'], list):
                    markets.append(obj)
                for k, v in obj.items():
                    markets.extend(find_markets(v))
            elif isinstance(obj, list):
                for item in obj:
                    markets.extend(find_markets(item))
            return markets

        found = find_markets(raw_data)
        for m in found:
            name = m.get('name', '')
            if 'Points' in name or 'Rebounds' in name or 'Assists' in name or 'Match Betting' in name or 'Line' in name:
                selections = {}
                for sel in m.get('selections', []):
                    price_obj = sel.get('price', {})
                    price = price_obj.get('winPrice') or price_obj.get('handicap') or "N/A"
                    selections[sel.get('name')] = price
                    
                structured[name] = selections
                
        return structured

    def run(self):
        matches = self.fetch_daily_matches()[:1]
        if not matches:
            print("❌ 沒有發現任何 NBA 賽事，程式終止。")
            return
            
        print(f"\n--- 開始逐場攔截 Player Props ---")
        odds_data = asyncio.run(self.traverse_and_intercept(matches))
        
        try:
            import os
            os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(odds_data, f, ensure_ascii=False, indent=4)
            print(f"\n🎉 完美！所有賠率已成功導出至: {self.output_file}")
        except Exception as e:
            print(f"\n❌ 儲存 JSON 失敗: {e}")


if __name__ == "__main__":
    extractor = SportsbetNBAExtractor()
    extractor.run()
