#!/usr/bin/env python3
"""
claw_bet365_odds.py — Bet365 NBA Zero-Navigation Extractor V8

ARCHITECTURE: CDP Pure-Read + USER Manual Tab Click
- CDP `page.evaluate()` for reading ONLY — ZERO navigation
- USER manually clicks between tabs in Comet browser
- Script detects tab change and reads data automatically

CRITICAL RULES (Opus 2026-04-08 verified):
- ❌ NEVER use page.goto()
- ❌ NEVER use window.location.href/hash via evaluate
- ❌ NEVER use el.click() via evaluate
- ❌ NEVER use page.mouse.click()
- ✅ ONLY use page.evaluate() for pure DOM reading

TAB SELECTION (P40 — Milestones Source-First):
- ✅ "Points" = Milestones (10+, 15+, 20+)
- ❌ "Points O/U" = Main O/U with .5 lines — NEVER USE THIS

Version: 8.0.0
"""
import sys
import json
import asyncio
import argparse
from playwright.async_api import async_playwright

CDP_PORT = 9222


async def verify_page_health(page):
    """Check if the page is alive (not a Cloudflare shell)."""
    body_len = await page.evaluate("() => document.body.innerText.length")
    if body_len < 2500:
        print(f"❌ 頁面只有 {body_len} chars — 可能係空殼或 Cloudflare 攔截。")
        print("   請 USER 重新喺 Comet 手動打開 Bet365 NBA 頁面。")
        return False
    print(f"✅ 頁面健康 ({body_len} chars)")
    return True


async def read_current_tab_data(page):
    """Pure read of current DOM content — ZERO navigation."""
    text = await page.evaluate("() => document.body.innerText || ''")
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    # Extract game data section
    start = next((i for i, l in enumerate(lines)
                  if 'EARLY PAYOUT' in l or 'MULTI BET OFFER' in l), 0)
    if start > 0:
        start += 1
    end = next((i for i, l in enumerate(lines)
                if 'Receive live updates' in l or 'Information and transmission' in l),
               len(lines))

    return lines[start:end]


async def detect_selected_tab(page):
    """Detect which tab is currently selected — pure read."""
    return await page.evaluate("""() => {
        let active = '';
        // Bet365 uses class containing 'selected', 'Active', or similar
        document.querySelectorAll('[class*="Selection"], [class*="NavTab"], [class*="Tab"]').forEach(el => {
            const cls = el.className || '';
            if (cls.includes('selected') || cls.includes('Active') || cls.includes('gl-Market__selected')) {
                const txt = el.innerText ? el.innerText.trim() : '';
                if (txt) active = txt;
            }
        });
        return active;
    }""")


def check_for_decimal_lines(data, tab_name):
    """
    Detect .5 lines in extracted data — means wrong tab was selected.
    Returns True if .5 contamination detected.
    """
    text_blob = '\n'.join(data)
    import re
    # Look for patterns like "12.5" or "15.5" that are line markers (not odds)
    # Odds always have format like "1.83", "2.50" — small numbers with decimals
    # Line markers are larger: 10.5, 12.5, 15.5, 20.5, 25.5 etc.
    decimal_lines = re.findall(r'\b(\d{2,}\.5)\b', text_blob)
    if decimal_lines and tab_name == "Points":
        print(f"\n⚠️  WRONG_TAB_DETECTED!")
        print(f"   發現 .5 盤口: {decimal_lines[:5]}")
        print(f"   你極可能 click 咗 'Points O/U' 而唔係 'Points'！")
        print(f"   'Points' 喺 'Game' 右邊嗰個，'Points O/U' 喺更右邊。")
        print(f"   請重新 click 正確嘅 'Points' tab！\n")
        return True
    return False


async def wait_for_tab(page, tab_name, timeout=90):
    """Wait for USER to click the specified tab, then read data."""
    print(f"\n{'='*55}")
    print(f"📢  請喺 Comet 手動 click  >>>  {tab_name}  <<<  tab")
    if tab_name == "Points":
        print(f"")
        print(f"⚠️  注意！請確認係 'Points' tab，唔係 'Points O/U' tab！")
        print(f"    'Points' 喺 'Game' 右邊（第 2 個 tab）")
        print(f"    'Points O/U' 喺 'Points' 右邊（第 3 個 tab）— 唔好撳呢個！")
    print(f"{'='*55}")

    for elapsed in range(timeout):
        selected = await detect_selected_tab(page)

        if tab_name in selected:
            print(f"✅ 偵測到 '{tab_name}' 已啟動！等待 3 秒渲染完畢...")
            await asyncio.sleep(3)

            # Verify page still healthy after tab switch
            if not await verify_page_health(page):
                return None

            data = await read_current_tab_data(page)

            # .5 contamination check for Points tab
            if tab_name == "Points" and check_for_decimal_lines(data, tab_name):
                # Give USER another chance
                print(f"⏳ 等待 USER 重新 click 正確嘅 'Points' tab...")
                continue

            print(f"✅ {tab_name}: 成功提取 {len(data)} 行數據")
            return data

        # Progress indicator
        remaining = timeout - elapsed
        if remaining % 15 == 0 and remaining > 0:
            print(f"   ⏳ 等待中... ({remaining}s 剩餘)")

        await asyncio.sleep(1)

    print(f"⚠️ 超時 ({timeout}s)！未能檢測到 '{tab_name}' tab")
    return []


async def main():
    parser = argparse.ArgumentParser(description='Bet365 NBA Zero-Navigation Extractor V8')
    parser.add_argument('--output', default='.agents.agents/tmp/bet365_all_raw_data.json',
                        help='Output JSON file path (use absolute path!)')
    parser.add_argument('--port', type=int, default=9222,
                        help='Comet CDP port (default: 9222)')
    args = parser.parse_args()

    global CDP_PORT
    CDP_PORT = args.port

    print("=" * 55)
    print("  🏀 NBA Wong Choi — Bet365 Extractor V8")
    print("  📋 Zero-Navigation Architecture")
    print("  🎯 Milestones Source-First (P40)")
    print("=" * 55)

    async with async_playwright() as p:
        print(f"\n🔌 連接 Comet CDP (port {CDP_PORT})...")
        try:
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
        except Exception as e:
            print(f"❌ 無法連接 Comet！錯誤: {e}")
            print("   請確保 Comet 已用 --remote-debugging-port=9222 啟動")
            return

        context = browser.contexts[0]

        # Find Bet365 tab — iterate all pages
        page = next(
            (pg for pg in context.pages if "bet365.com.au" in pg.url),
            None
        )

        if not page:
            print("❌ 搵唔到 Bet365 tab！")
            print("   請先喺 Comet 打開 bet365.com.au → NBA 賽事列表")
            await browser.close()
            return

        print(f"✅ 搵到 Bet365 tab: {page.url[:60]}...")

        # Verify page health
        if not await verify_page_health(page):
            await browser.close()
            return

        all_data = {}

        # ═══ Phase A: Game Lines (全自動 — 默認 tab) ═══
        print(f"\n{'─'*55}")
        print(f"📊 Phase A: 讀取 Game Lines（全自動）")
        print(f"{'─'*55}")

        game_data = await read_current_tab_data(page)
        all_data["Game Lines"] = game_data
        print(f"✅ Game Lines: {len(game_data)} 行")

        # ═══ Phase B: Player Props (需要 USER 手動 click) ═══
        print(f"\n{'─'*55}")
        print(f"🎯 Phase B: 讀取 Player Props（USER 手動 Click）")
        print(f"{'─'*55}")

        # P40: 正確 Tab 名 — "Points" (Milestones), 唔係 "Points O/U"！
        prop_tabs = ["Points", "Rebounds", "Assists", "Threes Made"]

        for tab_name in prop_tabs:
            data = await wait_for_tab(page, tab_name)
            if data is None:
                print(f"⚠️ {tab_name} 提取失敗或頁面死亡")
                all_data[tab_name] = []
            else:
                all_data[tab_name] = data

        # ═══ Phase C: Save ═══
        print(f"\n{'─'*55}")
        print(f"💾 Phase C: 儲存數據")
        print(f"{'─'*55}")

        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(all_data, f, indent=2, ensure_ascii=False)

        # Summary
        print(f"\n{'='*55}")
        print(f"🏆 提取完成！")
        print(f"{'='*55}")
        for key, val in all_data.items():
            status = "✅" if len(val) >= 10 else ("⚠️" if len(val) > 0 else "❌")
            print(f"  {status} {key}: {len(val)} 行")
        print(f"\n💾 已儲存至: {args.output}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
