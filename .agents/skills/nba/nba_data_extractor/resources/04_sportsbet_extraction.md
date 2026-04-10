# 04 — Sportsbet 自動防封鎖提取協議 (Claw V2)

> **版本**: 3.0.0 | **最後更新**: 2026-04-10
> **狀態**: ✅ PRODUCTION — 經 API 直接提取驗證 (CDP Bypass, `curl_cffi` 底層)

## 概述

Sportsbet 賠率提取使用 **Claw V2** (`claw_sportsbet_odds.py`)，透過 `curl_cffi` 直接模仿 Chrome 120 的 TLS 指紋，避開 Cloudflare 封鎖，並透過解析 `window.__PRELOADED_STATE__` 取得完整 JSON。完全自動化，**零跳轉、零用戶互動**。

---

## ✅ 提取流程（全自動）

提取腳本已完全封裝所有邏輯（讀取目錄、查找賽事、下載 HTML 並轉為 JSON）：

**執行指令** (必須使用絕對路徑):
```bash
python3 "./.agents/skills/nba/nba_data_extractor/scripts/claw_sportsbet_odds.py" \
  --outdir "{TARGET_DIR}"
```

### 腳本執行內容
1. 自動透過 API `Competitions/6927` 獲取當日所有 NBA 賽事。
2. 自動利用 `curl_cffi` (impersonate="chrome120") 下載每場賽事嘅 html 源代碼。
3. 自動正則提取 `__PRELOADED_STATE__`。
4. 將過渡後嘅盤口轉換成 `Sportsbet_Odds_{AWAY}_{HOME}.json`，並直接保存至 `--outdir` 資料夾內。

若提取成功，所有 `Sportsbet_Odds_*.json` 會全部出配並存妥。
若提取出現 403 Forbidden 或是缺少 `curl_cffi` → 報錯 `extraction_failed` → 必須中斷並要求用戶運行 `pip install curl_cffi` 解決。

### 🚨 廢除舊版 CDP 及 browser_subagent
嚴禁使用以下任何「手動或半手動」工具提取 Sportsbet：
- ❌ Playwright / Puppeteer navigation (必定被 Ban)
- ❌ Comet CDP manual execution + User Clicks (已由 V2 API 腳本取代，不需要用戶手動 click)
- ❌ `browser_subagent` / `read_browser_page`

**唯一允許合法提取盤口嘅方式為執行 `claw_sportsbet_odds.py` 腳本。**
