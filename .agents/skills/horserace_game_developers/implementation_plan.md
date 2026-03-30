# 「旺財街機」遊戲開發 Agent 套件計劃書 v2.0

> 喺 `.agents/skills/horserace_game_developers/` 下構建 **11 個專業 Agent**，用嚟策劃、開發、測試、維護同移動端移植「旺財街機」像素賽馬小遊戲。

---

## 設計理念

### 項目複雜度

「旺財街機」涉及 6 個互相依賴嘅系統：

| 系統 | 複雜度 | 核心文件 |
|:---|:---|:---|
| Vite + React 前端 | 高 | `ArcadePage.jsx`, `BettingPanel.jsx`, `NewsScroller.jsx` |
| HTML5 Canvas 引擎 | 極高 | `gameEngine.js`, `GameCanvas.jsx` |
| 賽事生成器 | 高 | `raceGenerator.js`, `horseDatabase.js` |
| 投注/經濟系統 | 高 | 5 種投注, 賠率算法, 資金管理 |
| 情報/策略層 | 中 | 8 種情報類型, 旺財分析法 |
| 像素美術 | 中 | 精靈圖, CRT 效果, 多層背景 |

### 設計-代碼同步協定 (Design-Code Sync Protocol)

> [!IMPORTANT]
> 所有工程師 Agent 喺修改遊戲邏輯時，**必須同步更新**以下兩份文檔：
> - `旺財街機_GAME_CONFIG.txt` — 遊戲參數及規則設定
> - `旺財街機_實作計劃書.txt` — 實作架構及流程
>
> 呢個協定確保用戶可以隨時通過修改文檔嚟指導 Agent 更新代碼，實現真正嘅「單一事實來源」。

### 採用嘅 Antigravity 設計模式

| 模式 | 應用方式 |
|:---|:---|
| Pattern 8 (批次隔離) | 前端工程師逐個組件構建，引擎每個模組獨立 |
| Pattern 10 (會話恢復) | 所有 Agent 啟動時掃描現有文件，偵測已完成工作 |
| Pattern 11 (強制 Checkpoints) | 監製喺階段轉換時暫停等用戶確認 |
| Pattern 12 (分層質檢) | QA 分輕量級 (組件) 同重量級 (全集成) |
| Pattern 13 (情報包) | 監製產出 `_Game_Design_Package.md` 供全鏈條讀取 |
| Pattern 14 (禁止 Heredoc) | 所有 Agent 只准用 `write_to_file` / `replace_file_content` |
| Pattern 16 (狀態持久化) | 運維 Agent 將會話狀態寫入 `_session_state.md` |

### 採用嘅 Awesome Skills 模式

| 技能 | 提取內容 |
|:---|:---|
| `game-development` | 遊戲循環 (INPUT→UPDATE→RENDER), 狀態機, 性能預算 (16.67ms/幀), 對象池 |
| `frontend-design` | DFII 評分 (≥8), 反 AI-slop, 「復古未來主義 × 香港霓虹」design direction |
| `testing-qa` | 測試金字塔 (70% Unit / 20% Integration / 10% E2E), Quality Gates |

---

## 11-Agent 詳細規格

---

### Agent 1: 遊戲監製 (Game Producer)

| 項目 | 內容 |
|:---|:---|
| **資料夾** | `horserace_game_developers/game_producer/` |
| **角色** | 總指揮，等同 HKJC 鏈條中嘅 Wong Choi |
| **觸發詞** | 「策劃遊戲」「設計遊戲」「下一步做咩」「遊戲藍圖」「game roadmap」「開始做遊戲」 |

**核心職責：**
1. 接收用戶需求，對照 `旺財街機_GAME_CONFIG.txt` 同 `旺財街機_實作計劃書.txt` 評估可行性
2. 產出 `_Game_Design_Package.md` (Pattern 13)，所有下游 Agent 直接讀取
3. 將任務路由畀正確嘅專業 Agent（附帶具體 @mention 指令）
4. 管理 7 階段交付流程：需求 → 設計 → 引擎 → UI → 美術 → 測試 → 發布
5. 每個階段結束時強制暫停 (Pattern 11)，向用戶提交摘要等確認

**Session Recovery (Pattern 10)：**
```
啟動時掃描：
1. 檢查 _Game_Design_Package.md 是否存在
2. 檢查 src/ 目錄有無已建立嘅組件
3. 列出已完成 / 進行中 / 未開始嘅階段
4. 問用戶：「繼續邊個階段？」
```

**防護機制：**
- Max 3 次路由重試，超出則暫停問用戶
- 禁止同時啟動 >2 個下游 Agent
- 每次路由必須附帶明確嘅完成標準 (Definition of Done)

**SKILL.md 結構 (~120 行)：**
- Frontmatter (name, description w/ 6 trigger phrases, version)
- Role & Objective
- Persona & Tone (廣東話語氣)
- Session Recovery Protocol
- 7-Stage Workflow (list format)
- Routing Table (哪個任務 → 哪個 Agent)
- Forced Checkpoint Protocol
- File Writing Protocol (Pattern 14 warning)

**Resources：**
- `resources/01_routing_table.md` — 完整路由邏輯 + 觸發條件
- `resources/02_stage_definitions.md` — 7 階段嘅輸入/輸出/評審標準

---

### Agent 2: 主遊戲策劃 (Lead Game Designer)

| 項目 | 內容 |
|:---|:---|
| **資料夾** | `horserace_game_developers/lead_designer/` |
| **角色** | 核心 GDD 守護者，確保所有設計決策符合「旺財」嘅初衷 |
| **觸發詞** | 「核心機制」「遊戲總攬」「GDD打磨」「主策劃」「game design review」「遊戲定義」 |

**核心職責：**
1. 維護同打磨核心 GDD (Game Design Document)
2. 定義遊戲整體流程：10 場賽日制，XP/等級系統，解鎖機制
3. 評審所有新功能提案同現有設定嘅一致性
4. 產出遊戲需求清單畀 Systems Designer 同 Content Designer
5. 採用 B17 迭代改善循環：Draft → Review → Refine → Completion Promise

**輸入/輸出：**
- 輸入：`旺財街機_GAME_CONFIG.txt`, `旺財街機_實作計劃書.txt`, 用戶新需求
- 輸出：更新後嘅 GDD sections (以 diff 格式)，功能需求清單

**防護機制：**
- Anti-Hallucination：唔可以憑空創作遊戲數據，所有數值必須有設計依據
- 改動前必須列出「影響範圍」(blast radius)，確認唔會破壞其他系統
- 最大迭代 5 次 (B17 loop)，之後必須提交畀用戶

**SKILL.md 結構 (~100 行)：**
- Frontmatter
- Role & Objective
- Source of Truth (指向兩份核心文檔)
- Design Review Workflow (B17 loop)
- Impact Analysis Protocol
- Output Format (diff + rationale)

**Resources：**
- `resources/01_game_config_reference.md` — 如何讀取同解析 GAME_CONFIG
- `resources/02_design_principles.md` — 遊戲設計原則 (來自 `game-development` skill)

---

### Agent 3: 系統及數值策劃 (Systems & Balance Designer)

| 項目 | 內容 |
|:---|:---|
| **資料夾** | `horserace_game_developers/systems_designer/` |
| **角色** | 數學大腦，負責所有數值平衡、賠率算法、經濟模型 |
| **觸發詞** | 「數值平衡」「賠率算法」「投注系統」「系統設計」「game balance」「經濟模型」 |

**核心職責：**
1. 設計賠率生成算法 (Odds Algorithm)：基於馬匹 10+ 項屬性
2. 設計數值曲線：速度/耐力/爆發力/心理質素等屬性嘅互相影響
3. 設計投注經濟學：初始資金、5 種投注嘅期望值、派彩倍率、破產機率
4. 量化旺財情報系統對勝率嘅實質影響
5. 提供數學驗證報告：Monte Carlo 模擬 1000 場賽事嘅統計結果
6. **破產及借貸機制** (§16)：定義 $0 觸發閾值、借貸額度 ($500)、借貸次數對評級嘅影響公式
7. **隨機意外事件觸發率表** (§11)：定義 9 種事件嘅觸發機率、效果數值、目標選擇邏輯
8. **派彩評級閾值** (§16)：S/A/B/C/D/F 各級盈虧閾值嘅合理性驗證
9. **三/四疊交通系統規則** — 定義馬群擠迫嘅數學模型：
   - 三疊觸發條件：≥3 匹馬喺同一橫排 ± 0.5 身位
   - 四疊觸發條件：≥4 匹馬同橫排，內櫄馬完全被困
   - 被困懲罰：baseSpeed -15~25% (持續 1-3 秒)
   - 脱困機率：基於騎師能力值 + 馬匹 burstChance
   - 跑法影響：後上馬受困機率 +20%，領放馬豁免
   - 檔位 (barrier draw) 影響：內櫄更易被困，外櫄兆圈損耗 stamina
10. **泥地賽差異化規則** — 定義草地 vs 泥地嘅數值差異：
    - 泥地 baseSpeed 修正：-5~10% (泥地阻力大)
    - 泥地 stamina 消耗：+15% (更費體力)
    - 泥地前置優勢：領放馬額外 +8% baseSpeed (避開踢泥)
    - 泥地後上劣勢：後上馬額外 -10% (踢泥影響視野 + 體力)
    - 新屬性 `dirtPreference`：0.5-1.5 (泥地適性倍率)
    - 泥地場地狀態：fast / wet / sloppy (區別於草地嘅 good/yielding/soft)

**輸入/輸出：**
- 輸入：Lead Designer 嘅需求清單, GAME_CONFIG 中嘅現有數值
- 輸出：數值表格 (CSV / Markdown), 平衡驗證報告, 修改建議

**防護機制：**
- 所有數值改動必須附帶「前後對比表」
- 禁止「拍腦袋」調數值，必須有公式或模擬支撐
- 改動 config 時強制觸發 Design-Code Sync Protocol

**SKILL.md 結構 (~110 行)：**
- Frontmatter
- Role & Objective
- Mathematical Framework
- Balance Methodology
- Config Sync Protocol (Design-Code Sync)
- Output Format (tables + formulas)

**Resources：**
- `resources/01_odds_formula.md` — 賠率公式及推導
- `resources/02_economy_model.md` — 投注經濟學模型
- `resources/03_balance_targets.md` — 數值平衡目標 (KPI)
- `resources/04_traffic_model.md` — 三/四疊交通數學模型及跑法影響表
- `resources/05_dirt_track_rules.md` — 泥地賽差異化規則及屬性修正表

---

### Agent 4: 內容及情報策劃 (Story & Content Designer)

| 項目 | 內容 |
|:---|:---|
| **資料夾** | `horserace_game_developers/content_designer/` |
| **角色** | 內容填充者，賦予 80+ 匹馬「生命感」 |
| **觸發詞** | 「馬匹資料庫」「情報模板」「旺財晨報內容」「內容策劃」「horse database」「game content」 |

**核心職責：**
1. 維護 80+ 匹馬嘅詳細資料庫：名稱、背景故事、性格特色、歷史戰績
2. 維護 20 位騎師 + 15 位練馬師嘅人物設定
3. 撰寫 8 種情報類型嘅文字模板（旺財晨報嘅每日內容）
4. 設定馬主彩衣配色規則同馬名彩蛋 (Fun facts)
5. 確保情報文字同隱藏數值加成邏輯一致

**數據來源政策 — 「現役優先」：**

> [!IMPORTANT]
> 所有數據必須盡量反映**最新嘅現役陣容**，確保遊戲有「真實感」：
>
> | 類別 | 規則 | 例子 |
> |:---|:---|:---|
> | **馬匹** | 以現役馬為主，但經典名駒可以保留作為「傳奇馬」彩蛋 | ✅ 現役馬 80+；🏆 傳奇馬如精英大師、蓮華生輝可保留 |
> | **騎師** | 必須用現役騎師嘅最新數據 | ✅ 潘頓、莫雷拉、何澤堯等現役；❌ 已退役嘅唔好用 |
> | **練馬師** | 必須用現役練馬師嘅最新數據 | ✅ 蔡約翰、方嘉柏、呂健威等現役 |
>
> **傳奇馬保留標準**：只有喺香港賽馬歷史上具標誌性地位嘅馬先可保留（例如：精英大師、翠河、祿怡）。呢啲馬應標記為 `legendary: true`，喺遊戲中做特殊彩蛋出現。

**輸入/輸出：**
- 輸入：Lead Designer 嘅內容需求, Systems Designer 嘅數值框架
- 輸出：`horseDatabase.js` 嘅數據結構, 情報文字模板庫, 彩衣配色表

**防護機制：**
- Anti-Hallucination：馬匹名必須來自 GAME_CONFIG 中嘅 80+ 個預設名
- 情報內容必須標註「對應隱藏數值」(e.g. 「今日狀態極佳」→ +15% 心理質素)
- 批次隔離：每次處理 5-10 匹馬嘅資料 (Pattern 8)
- **現役驗證**：騎師/練馬師名單每季至少對照 HKJC 官網更新一次

**SKILL.md 結構 (~100 行)：**
- Frontmatter
- Role & Objective
- Database Schema Reference
- Intel Template Gallery (8 types)
- Anti-Hallucination Protocol
- Batch Processing Rules

**Resources：**
- `resources/01_horse_name_registry.md` — 80+ 匹馬名單同背景框架
- `resources/02_intel_templates.md` — 8 種情報模板同數值映射
- `resources/03_commentary_templates.md` — 香港賽馬經典評述句式模板庫 (仿梁浩賢風格)

---

### Agent 5: 前端工程師 (Frontend Engineer)

| 項目 | 內容 |
|:---|:---|
| **資料夾** | `horserace_game_developers/frontend_engineer/` |
| **角色** | UI 建造師，負責 React 組件 (Canvas 引擎除外) |
| **觸發詞** | 「整遊戲UI」「遊戲前端」「投注面板」「街機頁面」「frontend UI」「React組件」 |

**核心職責：**
1. 開發核心 React 組件：
   - `ArcadePage.jsx` — 主頁面佈局
   - `BettingPanel.jsx` — 投注面板 (5 種投注方式)
   - `NewsScroller.jsx` — 旺財晨報滾動新聞
   - `RaceResult.jsx` — 賽後結算畫面
   - `DaySummary.jsx` — 每日總結
   - `LiveRankingPanel.jsx` — **比賽中即時排名面板** (參考 HKJC Live)
   - `LiveCommentary.jsx` — **即時文字評述捲動條**
2. 執行「復古未來主義 × 香港霓虹」設計方向
3. 使用 Press Start 2P 字體 + CRT 掃描線 + 霓虹燈效果
4. 所有 CSS 通過 CSS Variables 統一管理
5. 響應式佈局：1440px / 768px / 375px 三個斷點
6. **Mobile-Ready 約束**：觸控友好嘅按鈕大小 (≥ 44px)、viewport meta tag、禁止 hover-only 交互

**LiveRankingPanel 規格 (參考 HKJC Live)：**
```
即時排名面板顯示內容：
│ 排名 │ 馬號 │ 綼衣色塊 │ 馬名 │ 與前馬距離 │
│  1  │  #3  │  🟥⬜  │ 金槍六十 │  ---   │
│  2  │  #7  │  🟦🟨  │ 加州星球 │  1.5L  │
│  3  │  #1  │  ⬜🟪  │ 精英大師 │  0.5L  │
│ ... │ ... │  ...  │  ...   │  ...   │

更新頻率：每 0.5 秒一次（命令式渲染，唯讀 Engine 的 state）
位置：Canvas 右側/下方疊加（手機版可收縮為前 3 名）
```

**LiveCommentary 規格 (可選但建議)：**
```
文字評述滾動條，正宗香港賽馬評述風格 (仿梁浩賢)：

起步階段：
- 「開閘啦！一起步個陣呀，金槍六十應聲彈出！」
- 「一起步個陣呀，XXX 出閘慢左、擺左喺後面」

中段：
- 「到五百米、帶出仍然係金槍六十」
- 「去到XXX米處，前面放頭既有XXX、XXX、XXX，中間有XXX、XXX，後少少既馬仲有XXX」
- 「XXX 俾人夾住左！」
- 「XXX 一路領放、走勢幾勁！」

入直路：
- 「入正直路！後面馬開始變速！」
- 「前面放頭既仲有XXX、XXX、XXX，中間XXX、XXX 追左上黎呀」
- 「XXX 喺外疊衝左上黎！」
- 「最後200米，領先緊既仲有XXX」
- 「XXX 追緊上黎呀」

衝線：
- 「衝線！跑第一名既馬XXX」
- 「衝線啦！XXX 從後趕上勝出！」
- 「衝線！XXX 從由頭帶到落尾勝出！」
- 「XXX 贏到好似晨操咁跑番黎！」
- 「跑第二名既馬係XXX」
- 「跑第三名既馬XXX」

觸發：基於 Engine 嘅賽事階段 + 事件 自動生成
位置：Canvas 下方或排名面板下方，單行滾動
```

**Design-Code Sync Protocol：**
```
每次修改 UI 邏輯或狀態流時：
1. 更新 旺財街機_實作計劃書.txt 中對應嘅 UI 章節
2. 如果增加/移除咗組件，更新計劃書嘅「組件清單」section
3. Commit message 註明：「[DocSync] 更新計劃書 Ch.X」
```

**防護機制：**
- DFII 評分 ≥ 8 先可以 commit (來自 `frontend-design` skill)
- 批次隔離：每節會話只聚焦 1 個組件 (Pattern 8)
- 禁止 inline styles，全部用 CSS variables
- Anti-AI-slop：禁止 Inter/Roboto 字體，禁止 purple-on-white 漸變

**SKILL.md 結構 (~130 行)：**
- Frontmatter
- Role & Objective
- Design System (color palette, typography, spacing)
- Component Development Workflow
- DFII Scoring Gate
- Doc Sync Protocol
- Anti-AI-slop Checklist
- File Writing Protocol (Pattern 14)

**Resources：**
- `resources/01_design_system.md` — 完整顏色、字體、間距、CRT 效果定義
- `resources/02_component_specs.md` — 每個組件嘅 props + state + 事件定義

---

### Agent 6: 遊戲引擎開發員 (Game Engine Developer)

| 項目 | 內容 |
|:---|:---|
| **資料夾** | `horserace_game_developers/game_engine_dev/` |
| **角色** | 核心引擎建造師，負責 Canvas 渲染同賽事物理 |
| **觸發詞** | 「遊戲引擎」「比賽引擎」「Canvas渲染」「馬匹物理」「game physics」「race simulation」 |

**核心職責：**
1. `gameEngine.js` — 馬匹物理模型：
   - 4 階段賽程 (起步 → 中段 → 直路 → 衝線)
   - 12 匹馬同時模擬，互不干擾
   - 碰撞/阻擋邏輯
   - 爆發力 (Sprint) 觸發機制
2. `raceGenerator.js` — 賽事生成：
   - 馬匹配對算法 (class rating matching)
   - 動態賠率生成 (基於 Systems Designer 嘅公式)
   - 情報觸發規則
3. `GameCanvas.jsx` — HTML5 Canvas 渲染迴圈：
   - `requestAnimationFrame` 固定 16.67ms timestep
   - 精靈圖動畫 (2-frame horse sprites)
   - 多層背景視差捲動 (parallax)
4. `horseDatabase.js` — 80+ 匹馬/20 騎師/15 練馬師數據結構
5. **Input Abstraction Layer (Mobile-Ready)**：將滑鼠同觸控事件統一抽象為 ACTION
6. **近六場賽績生成** (§12)：根據馬匹評級 (S→D) 自動生成模擬歷史名次分佈
7. **隨機意外事件實作** (§11)：實作 9 種事件嘅觸發邏輯同視覺效果
8. **成就系統判定** (§15)：實作 3 級 12 個成就嘅條件判斷引擎
9. **多人 Draft Pick 狀態機** (§14)：輪轉邏輯、公開下注、回合管理
10. **破產觸發邏輯** (§16)：$0 偵測 → 借貸 UI 觸發 → 評級懲罰
11. **三/四疊交通系統實作** — 基於 Systems Designer 嘅數學模型：
    - 每幀偵測馬匹 Y 軸距離，判斷三/四疊狀態
    - 觸發速度衰減 + 視覺效果 (馬匹變紅/閃爍)
    - 脱困判定：每 0.5 秒檢查一次，基於騎師能力 + burstChance
    - 跑法加權：後上馬喺中段/彎位時檢查觸發、領放馬豁免
    - 內櫄 vs 外櫄：barrierDraw 1-3 受困機率 +10%，10-12 兆圈損耗 stamina -5%
12. **泥地賽引擎邏輯** — 基於 Systems Designer 嘅差異化規則：
    - 每場賽讀取 `trackSurface` (turf/dirt) 屬性
    - 泥地時套用不同嘅速度/耐力修正係數
    - 泥地場地狀態 (fast/wet/sloppy) 影響全場馬匹
    - 馬匹 `dirtPreference` 屬性嘅倍率應用
    - Canvas 渲染：泥地賽道顏色變化 + 泥濺粒子效果
13. **即時排名數據引擎** — 比賽中每 0.5 秒計算並廣播：
    - 12 匹馬嘅即時排名 (基於 X 軸位置)
    - 與前馬距離 (以「馬位 L」為單位)
    - 當前賽事階段標記 (起步/中段/彎位/直路)
    - 提供畀前端 `LiveRankingPanel` 嘅 state 接口
14. **即時評述事件生成器** — 基於賽事狀態自動產生評述文字 (梁浩賢風格)：
    - 起步：「一起步個陣呀，XXX 應聲彈出」
    - 三/四疊：「XXX 俾人夾住左！」
    - 爆發：「XXX 喺外疊衝左上黎！」
    - 入直路：「入正直路！」
    - 衝線：「XXX 從由頭帶到落尾勝出！」/「XXX 贏到好似晨操咁跑番黎！」
    - 賽後：「跑第二名既馬係XXX」「跑第三名既馬XXX」
    - 用模板 + 馬名動態插入，從 Content Designer 嘅評述模板庫讀取

**Config Persistence (Design-Code Sync)：**
```
每次修改物理參數或算法時：
1. 將新配置值寫入 旺財街機_GAME_CONFIG.txt 嘅對應 section
2. 如果增加/移除咗配置項，更新 GAME_CONFIG 嘅 schema 描述
3. 保留舊配置值喺 config 文件嘅註釋中（方便回退）
4. Commit message 註明：「[ConfigSync] 更新 CONFIG Section X」
```

**性能預算 (來自 `game-development` skill)：**

| 系統 | 預算 |
|:---|:---|
| Input 處理 | ≤ 1ms |
| 物理計算 (12馬) | ≤ 3ms |
| AI 決策 | ≤ 2ms |
| 遊戲邏輯 | ≤ 4ms |
| Canvas 渲染 | ≤ 5ms |
| Buffer | 1.67ms |
| **合計** | **16.67ms (60 FPS)** |

**防護機制：**
- 對象池 (Object Pooling)：精靈圖同粒子效果禁止 new/delete，必須用 pool
- 禁止喺 game loop 入面做 DOM 操作
- 每次引擎修改後必須行性能測試 (console.time)

**SKILL.md 結構 (~140 行)：**
- Frontmatter
- Role & Objective
- Game Loop Pattern (INPUT→UPDATE→RENDER)
- Physics Spec Summary
- Performance Budget Table
- Config Sync Protocol
- Object Pooling Rules
- File Writing Protocol (Pattern 14)

**Resources：**
- `resources/01_physics_spec.md` — 4 階段物理模型詳解
- `resources/02_performance_budget.md` — 性能預算同優化策略
- `resources/03_sprite_rendering.md` — Canvas 精靈圖渲染規範
- `resources/04_traffic_system.md` — 三/四疊實作規範（偵測、衰減、脱困、視覺效果）
- `resources/05_dirt_track_engine.md` — 泥地賽引擎實作規範（係數、渲染、狀態切換）

---

### Agent 7: QA 測試員 (QA Tester)

| 項目 | 內容 |
|:---|:---|
| **資料夾** | `horserace_game_developers/game_qa/` |
| **角色** | 品質守門員，兩層質檢 (Pattern 12) |
| **觸發詞** | 「測試遊戲」「行測試」「QA檢查」「bug報告」「test game」「品質檢查」 |

**輕量級 QA (每次組件提交後)：**
1. 結構掃描：組件 props 類型檢查，必要 state 是否存在
2. 視覺回歸：3 個 viewport (1440/768/375px) 截圖對比
3. 單元測試執行：`npx vitest run` 確保全 pass
4. Performance 快檢：Canvas FPS ≥ 55 (留 buffer)

**重量級 QA (每個開發階段結束後)：**
1. 模擬 5 個完整賽日 (50 場)：檢查有無邏輯死循環
2. 經濟系統壓測：連續玩 50 日，驗證唔會通脹/通縮
3. 投注準確性：所有 5 種投注方式嘅派彩計算
4. 多人模式：2/3/4 人 Draft Pick 全路徑覆蓋
5. 記憶體泄漏：開 50 場賽事後 heap snapshot 對比
6. 響應式佈局：iPhone SE / iPad / Desktop 全覆蓋
7. **移動端測試** (Mobile-Ready)：iOS Safari + Android Chrome 觸控操作、SafeArea 適配、Canvas 幀率測試

**測試金字塔 (來自 `testing-qa` skill)：**
- 70% 單元測試 (Vitest) — 組件邏輯, 數值計算, 工具函數
- 20% 集成測試 — 組件交互, 狀態流轉, API 模擬
- 10% E2E — 完整賽事流程 (browser_subagent 驗證)

**Bug Report 格式：**
```
## BUG-[編號]: [標題]
- 嚴重度：P0/P1/P2/P3
- 重現步驟：1. ... 2. ... 3. ...
- 預期結果：...
- 實際結果：...
- 截圖/錄影：[附件]
- 建議修正 Agent：@[agent_name]
```

**SKILL.md 結構 (~120 行)：**
- Frontmatter
- Role & Objective
- Lightweight QA Checklist
- Heavyweight QA Scenarios
- Test Pyramid Configuration
- Bug Report Template
- Performance Profiling Protocol

**Resources：**
- `resources/01_test_strategy.md` — 測試策略同覆蓋率目標
- `resources/02_test_scenarios.md` — 具體測試案例清單

---

### Agent 8: 運維及文檔同步 (Game Ops & Doc Sync)

| 項目 | 內容 |
|:---|:---|
| **資料夾** | `horserace_game_developers/game_ops/` |
| **角色** | 發布後守護者 + 文檔同步專員 |
| **觸發詞** | 「更新遊戲」「整返好個bug」「加新馬」「文檔同步」「game maintenance」「update game」 |

**核心職責：**
1. Bug 修正及分類實作 (根據 QA 嘅 Bug Report)
2. 向數據庫添加新馬匹/騎師/練馬師
3. 功能微調：新投注方式、成就系統、隨機事件
4. 維護更新日誌 (CHANGELOG.md)

**文檔同步職責 (Design-Code Sync 嘅最終守門)：**
```
每次更新後執行文檔同步掃描：
1. 比對 GAME_CONFIG.txt 同代碼中嘅常量，標記不一致項
2. 比對 實作計劃書.txt 同實際組件結構，標記過時描述
3. 產出「同步差異報告」畀用戶確認
4. 用戶確認後，更新文檔 OR 代碼（視乎邊個係最新嘅真相）
```

**Session State Persistence (Pattern 16)：**
```markdown
# _session_state.md
- LAST_UPDATE_TYPE: [bugfix / feature / db_update]
- LAST_UPDATED_FILES: [file1, file2...]
- DOC_SYNC_STATUS: [synced / out_of_sync]
- CHANGELOG_LATEST: [v1.2.3 description]
```

**SKILL.md 結構 (~100 行)：**
- Frontmatter
- Role & Objective
- Bug Triage Workflow
- Database Update Protocol
- Doc Sync Scanning Protocol
- Session State Persistence
- Changelog Format

---

### Agent 9: 像素美術師 (Pixel Artist)

| 項目 | 內容 |
|:---|:---|
| **資料夾** | `horserace_game_developers/pixel_artist/` |
| **角色** | 視覺資產創作者 |
| **觸發詞** | 「像素美術」「遊戲素材」「馬匹精靈圖」「pixel art」「sprites」「UI素材」 |

**核心職責：**
1. 12 種馬身配色方案 (32×24px, 2-frame idle/run animation)
2. 騎師彩衣圖案 (8×8px per owner)
3. 背景 Tilesets：沙田日景 / 跑馬地夜景 / 天氣疊加層
4. UI 像素素材：按鈕、邊框、面板、icon set
5. CRT 掃描線疊加層 + 霓虹發光效果
6. 使用 `generate_image` 工具生成素材草稿
7. 導出為 Base64 或 PNG sprite sheets

**美術風格約束：**
- 調色板：限制 16 色 (NES 風格)，加 4 個霓虹高光色
- 字體：Press Start 2P (display), 像素化中文 (body)
- 動畫：最多 4 幀循環，禁止超過 6 幀嘅複雜動畫

**SKILL.md 結構 (~80 行)：**
- Frontmatter
- Role & Objective
- Pixel Art Style Guide
- Sprite Sheet Specifications
- Asset Export Protocol
- Tool Usage (generate_image)

---

### Agent 10: 音效設計師 (Sound Designer)

| 項目 | 內容 |
|:---|:---|
| **資料夾** | `horserace_game_developers/sound_designer/` |
| **角色** | 街機聲音靈魂，負責所有音效同音樂 |
| **觸發詞** | 「遊戲音效」「音樂」「sound effects」「BGM」「街機音效」「馬蹄聲」 |

**核心職責：**
1. **街機核心音效** (必須)：
   - 🪙 投幣聲 (開局)
   - 🏇 馬蹄聲 (比賽中，按速度變頻)
   - 📣 起步鐘聲 + 閘門開啟聲
   - 🎉 衝線歡呼 / 爆冷驚嘆
   - 💰 派彩金幣聲 / 輸錢嘆息聲
   - 🔔 投注確認叮噹聲
2. **BGM 音軌** (按場景)：
   - 旺財晨報 BGM (輕快復古 chiptune)
   - 投注倒數 BGM (緊張感遞增)
   - 比賽進行 BGM (節奏隨賽程加速)
   - 賽後結算 BGM (沙田日間 vs 跑馬地夜間)
3. **事件音效**：
   - 9 種隨機意外嘅獨特音效 (§11)
   - 成就解鎖音效 (§15)
   - 情報揭示音效 (§10)
4. **多人模式音效**：Draft Pick 輪轉提示、對手下注提示

**技術規格：**
- 格式：Web Audio API / HTML5 `<audio>` 元素
- 文件：`.mp3` (兼容性) + `.ogg` (Chrome 優化)
- 大小限制：單個音效 < 50KB，BGM < 500KB
- 使用 `generate_image` 工具生成 chiptune 風格描述，再用 code 合成
- 音量控制：全局音量 + 分類音量 (SFX / BGM / UI)

**防護機制：**
- 所有音效必須有 mute 開關（無障礙要求）
- 禁止自動播放 BGM（瀏覽器政策），必須等用戶首次互動後播放
- 音效預載 (preload) 喺開局時完成，避免比賽中卡頓

**SKILL.md 結構 (~90 行)：**
- Frontmatter
- Role & Objective
- Sound Design Brief (街機復古 chiptune 風格)
- Audio Asset List (all SFX + BGM)
- Technical Specs (Web Audio API)
- Accessibility (mute, volume controls)

**Resources：**
- `resources/01_sound_asset_list.md` — 完整音效清單同優先級
- `resources/02_audio_tech_spec.md` — Web Audio API 實作規範

---

### Agent 11: 移動平台工程師 (Mobile Platform Engineer)

| 項目 | 內容 |
|:---|:---|
| **資料夾** | `horserace_game_developers/mobile_engineer/` |
| **角色** | 跨平台移植專家，將 Web 遊戲帶到 iOS/Android |
| **觸發詞** | 「iOS」「Android」「手機版」「移動端」「mobile app」「上架 App Store」 |

**核心職責：**
1. 用 **Capacitor** 將現有 Web app 打包成 iOS / Android 原生 App
2. 觸控輸入適配：
   - 將 Frontend Engineer 嘅 click 事件同 Engine Dev 嘅 Input Abstraction 映射到 touch/swipe/pinch
   - 投注面板嘅滑動操作優化
   - 虛擬搖桿 (virtual joystick) 評估（如需要）
3. 原生功能整合：
   - 震動回饋 (haptic feedback)：衝線/意外事件時觸發
   - 推送通知：賽事提醒（可選）
   - SafeArea 同 notch 適配
4. App Store / Google Play 提交：
   - 截圖準備、描述文字、年齡分級
   - 版本管理 (semantic versioning)
5. 移動端性能優化：
   - Canvas 在低端手機嘅 FPS 保障 (目標 ≥30 FPS)
   - 記憶體使用控制 (手機 RAM 限制)
   - 離線模式支援 (localStorage 已有，確保 Capacitor 層運作)

**技術路線建議：**
> [!TIP]
> 「旺財街機」係像素風 HTML5 Canvas 遊戲，用 **Capacitor** 打包係最低成本且最高保真嘅方案。
> 原因：100% 重用 Web 代碼，只需處理平台差異 (觸控、SafeArea、App Store)。
> React Native 或原生重寫成本過高，不建議。

**防護機制：**
- 每次移動端 build 前必須確認 Web 版 QA 已通過
- 平台專屬 bug 與 Web bug 分開追蹤
- Config Sync：移動端特有配置 (觸控參數、性能陞值) 寫入 `GAME_CONFIG.txt` 嘅新 section

**SKILL.md 結構 (~100 行)：**
- Frontmatter
- Role & Objective
- Platform Strategy (Capacitor)
- Touch Input Mapping
- Native Integration (haptics, notifications)
- App Store Submission Guide
- Mobile Performance Budget
- Config Sync Protocol

**Resources：**
- `resources/01_capacitor_setup.md` — Capacitor 初始化及構建流程
- `resources/02_touch_input_mapping.md` — 觸控輸入映射規範
- `resources/03_app_store_checklist.md` — iOS/Android 提交準備清單

---

## 跨系統分工表 (GAME_CONFIG §11-§16)

以下系統涉及多個 Agent 協作，呢度明確定義邊個做咩：

### 隨機意外事件 (§11, 9 種)
| 階段 | 負責 Agent | 具體工作 |
|:---|:---|:---|
| 定義觸發率同效果數值 | Systems Designer | 9 種事件嘅機率表 + 效果公式 |
| 實作觸發邏輯 | Game Engine Dev | 寫入 `gameEngine.js`，每場最多 1 件 |
| 視覺效果 | Pixel Artist | 事件圖標 + 閃爍動畫 |
| 音效 | Sound Designer | 每種事件獨特音效 |
| 測試 | QA Tester | 50 場驗證觸發頻率符合設計目標 |

### 成就系統 (§15, 3 級 12 個)
| 階段 | 負責 Agent | 具體工作 |
|:---|:---|:---|
| 定義成就清單同閾值 | Lead Designer | 3 級成就嘅解鎖條件 |
| 實作條件判斷引擎 | Game Engine Dev | `achievementEngine.js` |
| 解鎖 UI 動畫 | Frontend Engineer | 彈出通知 + 成就列表頁 |
| 解鎖音效 | Sound Designer | 青銅/白銀/金色各一 |
| 成就圖標 | Pixel Artist | 12 個像素圖標 |

### 多人 Draft Pick (§14)
| 階段 | 負責 Agent | 具體工作 |
|:---|:---|:---|
| 定義輪轉規則同策略設計 | Lead Designer | 輪轉順序、公開/隱藏規則 |
| 實作狀態機 | Game Engine Dev | 回合管理、玩家切換、下注鎖定 |
| 多人 UI 流程 | Frontend Engineer | 玩家面板、等待畫面、結果對比 |
| 輪轉提示音效 | Sound Designer | 「輪到你」提示音 |

### 近六場賽績 (§12)
| 階段 | 負責 Agent | 具體工作 |
|:---|:---|:---|
| 定義名次分佈規則 | Content Designer | S→D 各級嘅模擬名次範圍 |
| 實作生成算法 | Game Engine Dev | 自動生成 6 場歷史記錄 |
| UI 顯示 | Frontend Engineer | 場地+距離+名次圓圈 |

### 破產及借貸機制 (§16)
| 階段 | 負責 Agent | 具體工作 |
|:---|:---|:---|
| 定義閾值同公式 | Systems Designer | $0觸發、$500借貸、評級影響 |
| 實作觸發邏輯 | Game Engine Dev | 餘額監控 → 借貸流程 |
| 借貸 UI | Frontend Engineer | 確認對話框 + 借貸記錄顯示 |

### 即時排名 + 評述 HUD (Live Race HUD)
| 階段 | 負責 Agent | 具體工作 |
|:---|:---|:---|
| 插入綼衣色塊到馬匹資料 | Content Designer | 每匹馬嘅綼衣主色/副色 hex code |
| 綼衣像素圖標 | Pixel Artist | 8×8px 綼衣 sprite，嵁入排名面板 |
| 即時排名數據引擎 | Game Engine Dev | 每 0.5 秒計算 12 馬排名 + 距離 |
| 即時評述事件生成 | Game Engine Dev | 基於賽事狀態產生評述文字 |
| 評述文字模板庫 | Content Designer | 各階段嘅評述句式模板 |
| 排名面板 UI | Frontend Engineer | `LiveRankingPanel.jsx` (排名 + 馬號 + 綼衣 + 距離) |
| 評述捲動條 UI | Frontend Engineer | `LiveCommentary.jsx` (單行滾動) |
| 評述音效 | Sound Designer | 評述出現時嘅提示音 |

---

## Agent Chaining 協作流

```
用戶 → 遊戲監製 (項目規劃 + 任務路由)
         ↓
       ┌─ 主策劃 (GDD 打磨)
       │  ↓ 需求清單
       ├─ 系統數值策劃 (賠率 + 平衡 + 破產機制 + 意外觸發率)
       │  ↓ 數值表
       └─ 內容情報策劃 (馬匹資料庫 + 晨報 + 賽績分佈規則)
         ↓ _Game_Design_Package.md
       ┌──────────┬──────────┬──────────┐
       ↓          ↓          ↓          ↓
   前端工程師   引擎開發    像素美術   音效設計
   (UI/React)  (Canvas)   (視覺素材)  (SFX/BGM)
       ↓          ↓          ↓          ↓
       └────── 寫回 CONFIG / 計劃書 ──────┘
                  ↓
              QA 測試員 (輕量 → 重量級質檢 + 移動端測試)
                  ↓ 通過 ✅          ↓ 失敗 ❌
              遊戲監製              負責 Agent (修正)
                  ↓
              用戶 (正式遊玩 Web 版)
                  ↓ (Web 版穩定後)
              移動平台工程師 (打包 iOS/Android + App Store 上架)
                  ↓ (發布後)
              運維及文檔同步 (BUG修復 + 配置持久化)
```

---

## Health Check 對照表

每個 Agent 喺建立後都必須通過以下檢查：

| 檢查項 | 要求 | 對應 Pattern |
|:---|:---|:---|
| Frontmatter 完整 | name + description (≥3 觸發詞) + version | A.結構合規 |
| 四大 Section | Role + Objective + Scope + Interaction Logic | A.結構合規 |
| SKILL.md ≤ 200 行 | 重度內容喺 resources/ | B12 漸進式揭露 |
| Session Recovery | 啟動時掃描已完成工作 | Pattern 10 |
| Forced Checkpoints | 階段轉換暫停 | Pattern 11 |
| Anti-Laziness | 批次處理，禁止壓縮分析 | Pattern 8,9 |
| File Writing Protocol | 禁止 heredoc / cat EOF | Pattern 14 |
| Design-Code Sync | 工程師必須同步文檔 | 新增協定 |
| Language | 廣東話語氣，騎師/練馬師名全英文 | 生態系統慣例 |
| 上下游接口 | data contract 同鏈條中嘅 Agent 一致 | D.生態整合 |

---

## 驗證計劃

### 自動化結構驗證
```powershell
$agents = @("game_producer", "lead_designer", "systems_designer", "content_designer", "frontend_engineer", "game_engine_dev", "game_qa", "game_ops", "pixel_artist", "sound_designer", "mobile_engineer")
foreach ($agent in $agents) {
    $path = "g:\我的雲端硬碟\Antigravity Shared\Antigravity\.agents\skills\horserace_game_developers\$agent\SKILL.md"
    if (Test-Path $path) { Write-Host "✅ $agent" } else { Write-Host "❌ $agent MISSING" }
}
```

### 手動觸發測試
建立後可用以下句子測試路由：
1. 「策劃遊戲」→ Game Producer
2. 「核心機制」→ Lead Designer
3. 「數值平衡」→ Systems Designer
4. 「馬匹資料庫」→ Content Designer
5. 「整遊戲UI」→ Frontend Engineer
6. 「遊戲引擎」→ Game Engine Dev
7. 「測試遊戲」→ QA Tester
8. 「更新遊戲」→ Game Ops
9. 「像素美術」→ Pixel Artist
10. 「遊戲音效」→ Sound Designer
11. 「手機版」→ Mobile Platform Engineer

---

## 未來擴展：線上多人模式 (Online Multiplayer)

> [!NOTE]
> 以下功能作為未來擴展規劃，喺 Web 版 + 本地多人模式穩定後再實作。
> 不需要新 Agent，由現有 Agent 擴展職責即可。

### 構想：QR Code 加入 + 手機遊玩
1. 主機 (Host) 生成房間 + QR Code
2. 其他玩家掃 QR → 手機瀏覽器打開 → 加入房間
3. 實時同步投注 + 比賽畫面

### 技術路線
| 組件 | 技術 | 負責 Agent |
|:---|:---|:---|
| 實時通訊 | WebSocket (Socket.IO) | Engine Dev (擴展) |
| 房間管理 | 簡單 Node.js 服務器 | Engine Dev (擴展) |
| QR Code 生成 | `qrcode.js` 庫 | Frontend (擴展) |
| 手機 UI | 已有 Mobile-Ready UI | Frontend + Mobile Eng |
| 狀態同步 | Room State 廣播 | Engine Dev (擴展) |
| 反作弊 | Server-side 驗證 | Systems Designer (擴展) |

### 實作前提
- Web 版單機模式完全穩定
- 本地多人 Draft Pick 經過 QA 驗證
- 遊戲邏輯已與 UI 完全分離 (方便加入網絡層)

---

## 分階段構建計劃 (Build Phases)

11 個 Agent 分為 **4 個階段**構建，每個階段完成後設置 checkpoint，可以隨時停下再繼續。

### Phase 1：核心指揮鏈 (3 個 Agent)
| Agent | 原因 |
|:---|:---|
| ✅ Game Producer | 全局統籌，其他 Agent 依賴佢嘅路由表 |
| ✅ Lead Designer | GDD 守護者，定義遊戲核心 |
| ✅ Systems Designer | 數值大腦，其他 Agent 需要佢嘅公式 |

> **Checkpoint 1**: 完成後可停下。遊戲嘅規則層已完備。

### Phase 2：內容同素材 (2 個 Agent)
| Agent | 原因 |
|:---|:---|
| ✅ Content Designer | 馬匹資料庫 + 情報，引擎同前端需要呢啲數據 |
| ✅ Pixel Artist | 像素素材，前端同引擎需要呢啲 assets |

> **Checkpoint 2**: 完成後可停下。遊戲嘅數據同美術層已完備。

### Phase 3：工程開發 (3 個 Agent)
| Agent | 原因 |
|:---|:---|
| ✅ Game Engine Dev | Canvas + 物理引擎，遊戲核心 |
| ✅ Frontend Engineer | React UI，依賴引擎同素材 |
| ✅ Sound Designer | 音效，可與前端平行開發 |

> **Checkpoint 3**: 完成後可停下。遊戲嘅開發層已完備。

### Phase 4：質檢、運維同移動端 (3 個 Agent)
| Agent | 原因 |
|:---|:---|
| ✅ QA Tester | 質檢，必須喺開發 Agent 後面 |
| ✅ Game Ops | 運維，發布後才需要 |
| ✅ Mobile Engineer | 移動端，Web 版穩定後才做 |

> **Checkpoint 4**: 全部完成。

### Recovery Log 機制

每個 Phase 完成後，我會寫入一個 `_build_recovery.md` 到 `horserace_game_developers/` 資料夾：

```markdown
# 🛠️ Agent Build Recovery Log
- LAST_COMPLETED_PHASE: [1/2/3/4]
- LAST_COMPLETED_AGENT: [agent_name]
- AGENTS_DONE: [list]
- AGENTS_REMAINING: [list]
- NEXT_STEP: [description]
- TIMESTAMP: [ISO datetime]
```

如果你中途停下，下次對話只需講：
> 「繼續建立 Game Developer agents」

我會自動讀取 `_build_recovery.md`，從上次停下嘅位置繼續。
