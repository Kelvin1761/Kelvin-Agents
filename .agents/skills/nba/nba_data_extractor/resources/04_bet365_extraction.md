# 04 — Bet365 即時盤口提取協議 (Claw V8 — Zero-Navigation Architecture)

> **版本**: 3.0.0 | **最後更新**: 2026-04-09
> **狀態**: ✅ PRODUCTION — 經 Opus 實戰驗證 (CDP Fingerprinting Bypass)

## 概述

Bet365 賠率提取使用 **Claw V8** (`claw_bet365_odds.py`)，透過 Comet 瀏覽器嘅 CDP 遠端調試介面，**只做讀取 (Evaluate)**，絕不觸發任何 navigation 或 click 事件。

> [!CAUTION]
> ## 🚨 ZERO-NAVIGATION 黃金法則（經 Opus 2026-04-08 實戰驗證）
>
> **Cloudflare 嘅 CDP Fingerprinting 會 block 任何由 CDP execution context 觸發嘅 navigation event。**
> 呢個唔止包括 `page.goto()`，仲包括 `window.location.href`、`window.location.hash`、`el.click()` via evaluate、同 `page.mouse.click()`。
>
> **以下操作 100% 會觸發 Cloudflare 攔截並殺死 Tab（頁面變成 ~2193 chars 空殼）：**
>
> | 操作 | 結果 | 驗證日期 |
> |------|------|----------|
> | `page.goto(url)` | ❌ 空殼 | 2026-04-08 |
> | `window.location.href = url` (via evaluate) | ❌ 空殼 | 2026-04-08 |
> | `window.location.hash = hash` (via evaluate) | ❌ 空殼 | 2026-04-08 |
> | `page.mouse.click()` on tab/link | ❌ 空殼 | 2026-04-08 |
> | `el.click()` via `page.evaluate()` | ❌ 空殼 | 2026-04-08 |
> | `page.evaluate(() => document.body.innerText)` (純讀取) | ✅ 成功 | 2026-04-08 |
> | USER 手動 click → CDP 讀取 | ✅ 成功 | 2026-04-08 |
>
> **唯一安全操作 = `page.evaluate()` 純讀取 DOM 內容。其他任何操作都嚴禁。**

---

## ✅ 經驗證嘅提取架構：Plan A（CDP 讀取 + USER 手動 Click Tab）

### 前置條件
1. Comet 已安裝：`/Applications/Comet.app/`
2. Comet 已用 `--remote-debugging-port=9222` 啟動
3. USER 已喺 Comet 手動打開 `bet365.com.au` → 入去 **NBA 賽事列表（Index Page）**
4. 畫面上可見到球隊名同賠率（確認唔係空殼）

### 提取流程（Gemini Agent 嚴格按照以下步驟執行）

> [!IMPORTANT]
> **嚴禁跳過任何步驟。嚴禁「自行發明」新方法。呢套流程係經過雙重驗證（Opus + 實戰）嘅唯一可行方案。**

#### Step 0：連接 Comet CDP
```python
import asyncio
from playwright.async_api import async_playwright

async def connect():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        
        # 搵到 Bet365 tab — 唔好用 pages[0]！遍歷搵含 bet365 嘅 tab
        page = next(
            (pg for pg in context.pages if "bet365.com.au" in pg.url),
            None
        )
        if not page:
            print("❌ 搵唔到 Bet365 tab。請 USER 先打開 Bet365 NBA 頁面。")
            return None
        
        # 驗證頁面健康（唔係空殼）
        body_len = await page.evaluate("() => document.body.innerText.length")
        if body_len < 2500:
            print(f"❌ 頁面只有 {body_len} chars — 可能係空殼或 Cloudflare 攔截。")
            print("請 USER 重新喺 Comet 手動打開 Bet365 NBA 頁面。")
            return None
        
        print(f"✅ 已連接 Bet365 tab ({body_len} chars)")
        return page
```

> [!CAUTION]
> **嚴禁操作：**
> - ❌ `page.goto(any_url)` — 會觸發 Cloudflare
> - ❌ `await page.evaluate("window.location.href = ...")` — 會觸發 Cloudflare
> - ❌ `await page.evaluate("el.click()")` — 會觸發 Cloudflare
> - ❌ `await page.mouse.click(x, y)` — 會觸發 Cloudflare
> - ❌ `context.new_page()` — 新 Tab 注入自動化指紋
>
> **唯一允許嘅操作：**
> - ✅ `await page.evaluate("() => document.body.innerText")` — 純讀取
> - ✅ `await page.screenshot()` — 截圖記錄
> - ✅ `page.on("response", handler)` — 網路攔截

#### Step 1：讀取 Game Lines（全自動 — 無需 USER 操作）

NBA Index Page 嘅 `Game` tab 係默認選中嘅。直接讀取：

```python
# 純讀取 — ZERO navigation
text = await page.evaluate("() => document.body.innerText || ''")
lines = [l.strip() for l in text.split('\n') if l.strip()]

# 提取 game data 區域
start = next((i for i, l in enumerate(lines) if 'EARLY PAYOUT' in l or 'MULTI BET OFFER' in l), 0)
if start > 0: start += 1
end = next((i for i, l in enumerate(lines) if 'Receive live updates' in l or 'Information and transmission' in l), len(lines))

game_lines = lines[start:end]
print(f"✅ Game Lines: {len(game_lines)} 行")
```

#### Step 2：逐個 Prop Tab 讀取（需要 USER 手動 Click）

> [!WARNING]
> ## 🎯 正確 Tab 名稱（2026-04-09 截圖確認）
> 
> | # | Tab 名 | 提取內容 | ⚠️ 易混淆 Tab |
> |---|--------|----------|--------------|
> | 1 | **`Points`** | 得分 Milestones (10+, 15+, 20+) | ❌ `Points O/U`（產出 .5 盤口） |
> | 2 | **`Rebounds`** | 籃板 Milestones | — |
> | 3 | **`Assists`** | 助攻 Milestones | — |
> | 4 | **`Threes Made`** | 三分 Milestones | — |
>
> **`Points O/U` 係陷阱 Tab！** 佢產出 12.5, 15.5 等 .5 盤口，同 Milestones 嘅 10+, 15+ 完全唔同。

```python
# ⚠️ 正確嘅 Tab 列表 — 嚴禁使用 "Points O/U"！
prop_tabs = ["Points", "Rebounds", "Assists", "Threes Made"]

for tab_name in prop_tabs:
    print(f"\n{'='*50}")
    print(f"📢 請喺 Comet 手動 click '{tab_name}' tab")
    if tab_name == "Points":
        print(f"⚠️  注意！請確認係 'Points' tab，唔係 'Points O/U' tab！")
        print(f"    'Points' 喺 'Game' 右邊，'Points O/U' 喺 'Points' 右邊")
    print(f"{'='*50}")
    
    # 等 USER click（最多 60 秒）
    for countdown in range(60, 0, -1):
        # 偵測當前選中嘅 tab
        selected = await page.evaluate("""() => {
            let active = '';
            // Bet365 用 class 含 'selected' 或 'Active' 嘅元素標記當前 tab
            document.querySelectorAll('[class*="MarketSelection"], [class*="NavTab"]').forEach(el => {
                if ((el.className || '').includes('selected') || 
                    (el.className || '').includes('Active')) {
                    active = el.innerText.trim();
                }
            });
            return active;
        }""")
        
        if tab_name in selected:
            print(f"✅ 偵測到 '{tab_name}' 已啟動！等待 3 秒渲染...")
            await asyncio.sleep(3)  # 等 SPA 渲染完畢
            
            # 純讀取
            text = await page.evaluate("() => document.body.innerText || ''")
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            
            # 提取 game data 區域
            start = next((i for i, l in enumerate(lines) 
                         if 'EARLY PAYOUT' in l or 'MULTI BET OFFER' in l), 0)
            if start > 0: start += 1
            end = next((i for i, l in enumerate(lines) 
                       if 'Receive live updates' in l or 'Information and transmission' in l), 
                      len(lines))
            
            tab_data = lines[start:end]
            
            # ⚠️ .5 偵測 — 去錯 Tab 警報
            has_decimal = any('.' in word and word.replace('.','').isdigit() 
                           for line in tab_data for word in line.split()
                           if '.' in word and not any(c.isalpha() for c in word))
            if has_decimal and tab_name == "Points":
                print(f"⚠️ WRONG_TAB_DETECTED: 發現 .5 盤口！")
                print(f"   你可能 click 咗 'Points O/U' 而唔係 'Points'！")
                print(f"   請重新 click 正確嘅 'Points' tab（喺 'Game' 右邊嗰個）")
                continue  # 重試
            
            print(f"✅ {tab_name}: {len(tab_data)} 行數據")
            all_data[tab_name] = tab_data
            break
        
        if countdown % 10 == 0:
            print(f"   ⏳ 等待中... ({countdown}s)")
        await asyncio.sleep(1)
```

#### Step 3：儲存 Raw JSON

```python
import json

output_path = f"{TARGET_DIR}/bet365_all_raw_data.json"
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(all_data, f, indent=2, ensure_ascii=False)
print(f"💾 已儲存至 {output_path}")
```

#### Step 4：解析為 Per-Game Structured JSON

使用 `bet365_parser.py` 將 raw text lines 拆分為每場波獨立嘅結構化 JSON：
```bash
python3 .agents/skills/nba/../nba_wong_choi/scripts/bet365_parser.py \
  --raw "{TARGET_DIR}/bet365_all_raw_data.json" \
  --output-dir "{TARGET_DIR}/"
```

每場波會輸出 `Bet365_Odds_{GAME_TAG}.json`。

---

## 執行指令（完整一鍵版）

```bash
python3 "./.agents/skills/nba/nba_data_extractor/scripts/claw_bet365_odds.py" \
  --output "{TARGET_DIR}/bet365_all_raw_data.json"
```

腳本會自動：
1. 連接 Comet CDP
2. 讀取 Game Lines（全自動）
3. 提示 USER 手動 click 4 個 Prop Tab（`Points` → `Rebounds` → `Assists` → `Threes Made`）
4. 每個 Tab click 後自動讀取數據
5. 儲存完整 Raw JSON

---

## ⛔ 嚴禁清單（Never-Do Rules）

以下所有方法**已經被 Opus 於 2026-04-08 實測證明 100% 失敗**，嚴禁再嘗試：

| # | 方法 | 失敗原因 |
|---|------|----------|
| 1 | `page.goto(url)` | Cloudflare CDP Fingerprinting 攔截 |
| 2 | `window.location.href = url` via evaluate | 同上 |
| 3 | `window.location.hash = hash` via evaluate | 同上 |
| 4 | `page.mouse.click(x, y)` on tab/link | 同上 |
| 5 | `el.click()` via evaluate | 同上 |
| 6 | `context.new_page()` | 新 Tab 注入自動化指紋 |
| 7 | Standalone Playwright (headless/headed) | 非 Comet 瀏覽器 = 被檢測 |
| 8 | `curl_cffi` / `requests` | 403 Forbidden |
| 9 | `selenium` / `undetected-chromedriver` | 被檢測 |
| 10 | MCP Playwright `browser_navigate` | Headless Chromium 被封鎖 |
| 11 | `MCP Playwright (mcp_playwright_browser_*)` 模擬點擊 | 用嘅係 Headless Chromium |
| 12 | Tampermonkey `el.click()` 自動切換 Tab | Cloudflare 攔截所有程式化 click（2026-04-09 實測驗證）|

> [!CAUTION]
> **如果你（Gemini Agent）正在考慮「自行發明」新嘅提取方法 → ⛔ STOP**
> 
> 以上 11 種方法全部經過實戰驗證為失敗。唯一可行方案就係：
> 1. USER 手動打開 Bet365 → 手動 click Tab
> 2. CDP `page.evaluate()` 純讀取 DOM
> 
> **唔好嘗試任何「創意」方案。按照本文件嘅步驟一步一步執行。**

---

## Comet 前置條件

- Comet 已安裝：`/Applications/Comet.app/`
- 用 `--remote-debugging-port=9222` 啟動（或腳本自動偵測）
- **首次啟動可能需要 USER 手動處理 Cookie / Captcha**
- 之後嘅 session 會自動記住

## 驗證 Checklist

提取完成後，Gemini Agent 必須逐項驗證：

- [ ] `Game Lines` 有 ≥10 行
- [ ] `Points` 有 ≥30 行（⚠️ 確認冇 `.5` 盤口）
- [ ] `Rebounds` 有 ≥30 行
- [ ] `Assists` 有 ≥30 行
- [ ] `Threes Made` 有 ≥20 行
- [ ] 所有 JSON 盤口 key 為整數（`"10"`, `"15"` → ✅ | `"12.5"`, `"15.5"` → ❌ 去錯 Tab）

若任何 category 為空或行數太少 → 提示 USER 重新 click 該 Tab。
