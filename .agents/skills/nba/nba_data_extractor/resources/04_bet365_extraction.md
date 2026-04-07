# 04 — Bet365 即時盤口提取協議 (MCP Playwright Method)

> **版本**: 1.0.0 | **最後更新**: 2026-04-07
> **狀態**: ✅ PRODUCTION — 已驗證可 bypass Bet365 反爬蟲

## 概述

Bet365 賠率提取使用 **MCP Playwright** 工具直接由 `bet365.com.au` 嘅 DOM 提取即時盤口。
此方法是唯一成功 bypass Bet365 Cloudflare + 反指紋檢測嘅方案。

> [!CAUTION]
> **以下方法全部失敗，嚴禁再嘗試：**
> - ❌ `curl_cffi` / `requests` 直接抓取 → 403 Forbidden
> - ❌ `playwright` Python standalone (Chromium/WebKit/CDP) → 反指紋攔截
> - ❌ `selenium` / `undetected-chromedriver` → 被檢測
> - ❌ The Odds API (第三方) → 需付費 + 延遲
> - ❌ Tampermonkey injection → 需要用戶手動操作

## 提取流程 (Step-by-Step)

### Step 1: 導航到 Basketball Index
```
Tool: mcp_playwright_browser_navigate
URL: https://www.bet365.com.au/#/AS/B18/
```
等待 5-8 秒讓 SPA 完全渲染。

### Step 2: 驗證 NBA 數據已載入
```
Tool: mcp_playwright_browser_evaluate
Code: () => { 
  const text = document.body.innerText; 
  const idx = text.indexOf('NBA'); 
  if(idx > -1) return text.substring(idx, idx + 600); 
  return 'NBA_NOT_FOUND'; 
}
```
若返回 `NBA_NOT_FOUND` → 等多 5 秒再試。最多重試 3 次。

### Step 3: 提取 Index 頁面所有 Game Lines
由 Step 2 嘅返回文字中解析所有賽事嘅：
- 球隊名、開賽時間
- Line (讓分盤 + 賠率)
- Total (總分盤 + 賠率)
- To Win (獨贏賠率)

### Step 4: 導航入個別賽事頁面
```
Tool: mcp_playwright_browser_run_code
Code: async (page) => {
  const target = page.getByText('{TEAM_NAME}');
  await target.first().click();
  await page.waitForTimeout(5000);
  return await page.url();
}
```

### Step 5: 提取 Player Props (Full Snapshot)
```
Tool: mcp_playwright_browser_snapshot
filename: {SNAPSHOT_PATH}
```
Snapshot 會捕獲所有已展開嘅 Player Props tabs:
- **Points** — 球員名、Jersey#、L5 逐場得分、各 line 賠率
- **Threes Made** — Same structure
- **Rebounds** — Same structure
- **Assists** — Same structure

### Step 6: 解析 Snapshot 結構
Snapshot 嘅 DOM tree 結構如下：
```
generic: "Points" / "Threes Made" / "Rebounds" / "Assists"  ← Tab 標題
  generic: "Player / Last 5"  ← 表頭
    generic [cursor=pointer]:  ← 每個球員行
      img "Basketball Fallback Kit":
        generic: "{JERSEY_NUM}"  ← 球衣號碼
      generic:
        generic: "{PLAYER_NAME}"  ← 球員全名
        generic:
          generic: "{L5_GAME_1}"  ← 最近 5 場逐場數據
          generic: "{L5_GAME_2}"
          ...
  generic:  ← 盤口區域
    generic: "{LINE_VALUE}"  ← e.g. "5", "10", "15"
    generic [cursor=pointer]: "{ODDS}"  ← 各球員在此 line 嘅賠率
    ...
```

**關鍵 Pattern**: 球員順序同盤口區域嘅賠率順序一一對應（第 N 個球員 = 第 N 個賠率）。

### Step 7: 輸出結構化 JSON
```json
{
  "source": "Bet365_MCP_Playwright",
  "extraction_time": "{ISO_TIMESTAMP}",
  "game": { "matchup": "...", "date": "...", "time": "..." },
  "game_lines": { "line": {...}, "total": {...}, "moneyline": {...} },
  "player_props": {
    "points": { "{PLAYER}": { "jersey": "...", "last5": [...], "lines": {...} } },
    "threes_made": { ... },
    "rebounds": { ... },
    "assists": { ... }
  }
}
```

## 重要注意事項

1. **無需登入** — Bet365 AU 嘅賠率頁面不需要登入即可查看
2. **SPA 路由** — Bet365 使用 hash-based SPA routing，直接用 URL navigate 到個別賽事可能失敗，必須從 index 頁面 click 入去
3. **渲染延遲** — 每次 navigate 後必須等 5+ 秒讓 SPA 完全渲染
4. **Market 關閉** — 某些時段 Bet365 可能暫停某些 market，會顯示 "no markets currently available"
5. **Playwright Session** — MCP Playwright 使用獨立嘅 Chromium 實例，不會被 Bet365 檢測為自動化工具

## 與 nba_extractor.py 嘅整合

Bet365 提取嘅 JSON 應該被保存為 `{TARGET_DIR}/Bet365_Odds_{GAME_TAG}.json`，
然後由 Wong Choi Orchestrator 讀入並附加到球員數據卡中。

Analyst 應該直接引用 JSON 中嘅 `lines` 作為盤口分析嘅基礎，
而非使用 `nba_extractor.py` 輸出嘅估算盤口。
