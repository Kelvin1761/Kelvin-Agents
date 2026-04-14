# 靈活辦公室小紅書自動化營運管家 (XHS Office Bot) - Implementation Plan

## 1. 項目概述 (Goal Description)
為「靈活辦公空間經紀業務」（Flexible Office Broker）打造一個專屬的小紅書 AI 助手。本系統重點優化「人味 (Human-like tone)」，避免一般 AI 機器產生嘅罐頭文，並強制以**簡體中文 (Simplified Chinese)** 輸出，完全迎合小紅書生態。

## 2. 核心功能與架構 (Core Features)

### A. 小紅書純人味文案生成器 (Human-like Content Writer)
- **模型選用:** Google Gemini 3.1 Pro (透過 Antigravity 環境接入)。
- **Prompt 工程重點:**
  - **語言要求:** 由於小紅書的特性，所有輸出的文案將強制使用**簡體中文 (Simplified Chinese)**。
  - **去 AI 化 (Anti-AI Tone):** 內容需要具備強烈的「人味」。嚴禁使用「首先、其次、最後」、「這篇文章將探討」等常見 AI 套話。訓練 Gemini 模擬真人筆記作者的語氣（例如多代入真實情境、分享痛點體驗、自然口語化）。
  - **小紅書風格排版:** 適當留白、運用合適的 Emoji 來建立視覺節奏，精簡字句。

### B. 內容排期與防重覆系統 (Calendar & Anti-duplication)
- **月度/週度企劃:** 自動幫助你規劃未來一週或一個月的發文日曆。
- **防止重覆 (Anti-duplication):** 所有生成的貼文主題及關鍵字，會自動按月份儲存（例如 content_plans/2026_04/ledger.json 或 Markdown index）。系統未來生成新內容前會先讀取歷史，確保不「撞橋」。

### C. 引導式盤源貼文模式 (Interactive Guided Mode)
- **應用場境:** 針對 Virtual Office, Hot Desk, Dedicated Desk, Private Office 以及 Enterprise Suite。
- **一問一答:** Bot 會引導你輸入新盤的資訊（面積、地點、主要賣點等）。
- **免費中介 USP 注入:** 自動套用專屬 Broker 模板，每篇貼文必定自然地帶出重點信息：「我们是专业的办公室中介... 提供覆盖澳洲全境及亚洲各地的免费办公室寻找服务」。

## 3. 建議整合的 API / GitHub 資源 (Integrations for Data)
要令機器人掌握最新趨勢，單靠模型內置知識未必足夠，可以借助以下開源工具：

1. **[NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)**
   - **簡介:** GitHub 上功能最完整的開源多平台爬蟲工具，支援小紅書。
   - **應用:** 用來定期拉取 #VirtualOffice 或 #悉尼办公 等 hashtag 下最新的熱門筆記。
   - **結合方式:** 把爬取到的高讚文章標題和內文餵給 Gemini 3.1 Pro 進行分析，提煉出當前最流行的詞彙和爆點風格，再進行仿寫。
2. **[ReaJason/xhs](https://github.com/ReaJason/xhs)**
   - **簡介:** Python 封裝的小紅書 API Wrapper 工具。
   - **應用:** 如果你需要用 Python 自動化檢索一些 Hashtag 或帖子數據，這是一個現成的庫，省去自己寫加密參數的麻煩。

## 4. 介面形式 (UI Preference)
- **Streamlit Web UI:** 由於你會在 Antigravity 裡運行，使用 Streamlit 建立網頁應用最為合適。它天然支持聊天對話框與側邊攔切換功能，非常適合上述的「Guided Mode」一問一答流程。

## 5. 接下來的執行步驟
1. 建立 xhs_office_bot 專案資料夾。
2. 撰寫第一版 prompts.py（設定高濃度人工感、簡體中文的 Prompt）。
3. 使用 Streamlit 與 Python 搭建包含上述三大核心功能的主程式 (pp.py)。

> [!IMPORTANT]
> 此計劃書已生成。如果你認同這份設計，請說「Proceed」，我們便隨即開始編寫代碼！
