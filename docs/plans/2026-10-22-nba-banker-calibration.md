# NBA 穩膽（combo 1）修正方案

- **日期**：2026-10-22
- **平台**：NBA（`.agents/skills/nba/nba_wong_choi/scripts/generate_nba_reports.py`）
- **起因**：2026-10-22 穩膽 9 個有結算組合只贏 3 個；2026-10-21 三個全輸。
- **用戶決定**：唔停注。要分階段、可驗證嘅修正。
- **狀態**：方案。**本文件冇改任何評分 code。** 每個 Phase 都係獨立 release，要各自過 `model-regression-gate`。
- **證據紀律**：改評分／揀腿邏輯之前要先量 baseline、預先登記判決規則、dev／holdout 分開；多項一齊郁要 ablation。以下 §1 嘅數字係**診斷，唔係證明**（2 日、87 條獨立 leg）。

## 1. 診斷（2026-10-21／22，87 條獨立 leg）

| 觀察 | 數據 |
|---|---|
| 整體過度自信 | 引擎 `p_final` 平均 0.86–0.89，實際 0.56–0.61 |
| 輸畀市場 | 今日 66 條揀入組合嘅 leg：Brier 市場隱含 0.205、引擎 0.320、L10 基礎率 0.311、MC 0.303、ML 0.321 |
| 價位段 | combo 1 腿賠率 <1.45：18/20；≥1.45：5/17 |
| 按 stat（獨立 leg） | PTS n=34 預測 88% 實際 50%；REB n=26 90%／62%；AST n=18 78%／**39%**；3PM n=9 81%／89% |
| 位置 | 中鋒 AST 3 條獨立腿 0 中；後衛 REB 11 條（含重複）10 中 |
| 轉隊 | 39 條轉隊球員 leg 命中 59.0%，同隊 59.5%；莊家隱含已低 8pp（0.584 vs 0.665） |
| L10 來源 | 今日 L10 全部係 2025-26（含季後賽），截止 2026-04；EARLY_SEASON 只放大 MC SD |
| 已排除 | 大勝／garbage time：分差 ≥15 命中 70%，close game 37.5%（n=8） |
| 已有研究 | EXP-20261021-02～05：slope ≈0.55；PTS L10 slope 0.16；調整項合起嚟令 Brier 更差；EXP-05 一個 Poisson/NB＋逐 stat 重校準層離線通過 |

### 1.1 Code 層根因
1. `p = clamp(L10 命中率 + Σ調整, 5, 98)`，10 場樣本當機率用（`generate_nba_reports.py:519`）。
2. 用 edge 揀腿＝揀模型同莊家分歧最大嘅腿（逆向選擇）。
3. `select_combo_1`：組合賠率目標 2.0–3.5x、`odds ≥ 1.20`，逼揀 1.45–1.6 價位段。
4. docstring 話「神經刀禁止」，code 只做 `cov ≤ 0.65`（fallback 0.75）；神經刀門檻係 `cov > 0.35`。
5. 季初 L10 係上季數據，冇處理轉隊同新隊友 usage 重新分配。
6. Kelly 用虛高機率計（建議 26.9% bankroll）；ML 層 `hybrid_adj_applied=0` 冇作用。

### 1.2 報告／匯出 bug（已定位）
- **Banker 速覽 `N/A`**：`extract_banker_leg()`（`generate_nba_sgm_reports.py:121`）搵「最強一關」字串，report 而家寫「最強 MC 機會」，所以永遠 `N/A`。
- **`:banker` ≠ combo 1**：`multisport_exporter._build_nba_bankers` 將 combo 1 入面最高 EV 嘅**單腿**匯出做 `nba:<date>:<tag>:banker`（`legs=[]`）。結算時佢同 combo 1 係兩樣嘢，統計時要分清，唔好當成同一注。
- **GSW_LAL**：結算檔只有 `:banker`，冇 `:combo:1/2/3`。原因未查；Phase 1 要加測試重現。

## 2. 設計決定

### 2.1 Stat 資格（穩膽）
| Stat | 決定 | 理由 |
|---|---|---|
| REB | 保留 | 實際 62%，唯一接近市場價嘅大樣本 stat |
| PTS | 有條件保留 | 莊家開 PTS 最精準，L10 命中率幾乎冇預測力（slope 0.16），要機率層修好先可以當穩膽 |
| 3PM | 只准低線（1+／2+），暫保留 | 今日 8/9、EXP-02 校準最好；n 細，Phase 1 用大樣本再定 |
| AST | **移出穩膽**（去 value 組合） | 兩日最差（39%）；依賴隊友入波，最受新隊友影響 |

### 2.2 角色適配（唔按位置一刀切）
數據支持「中鋒 AST 唔係穩膽」，但後衛 REB 低線（4+）係正常產出。規則改為：該 stat 係咪呢個球員角色嘅主要產出（例如佔全隊該 stat 比例、每 36 分鐘產出對比同位置中位數）。

### 2.3 轉隊同新隊友
- 本人轉隊：上季數據收縮；分鐘改用今季實際。
- 新隊友：每隊「usage 流入／流出」＝進出球員上季 USG × 上場時間嘅淨變化。進高 usage 球員，原有球員 PTS／AST 下調（例：76ers 加 LeBron）。
- 今季場數增加就逐步將權重由上季轉去今季。

## 3. 分階段計劃

### Phase 0｜手動指引（即刻，唔停注）
- 唔跟 Kelly 個數，用細平注。
- 避開含 AST 腿同中鋒 AST 嘅組合。
- 偏向全部腿 <1.45 嘅組合。
- **註：** 呢三點由 §1 嘅 2 日數據事後睇出，只係假設，Phase 2 先正式驗證。

### Phase 1｜數據底同 bug（1–2 日）
1. **回測語料**：Drive 上上季 33 日、131 份 Sportsbet 賠率快照＋今季 `market_legs.json` sidecar；結算用 BoxScoreTraditionalV3。每條 leg 記價、當時 `p_final`、賽果、分鐘。
2. **新欄位**：位置、上季球隊／今季球隊、球隊陣容變動（資料已喺 `nba_game_data_*.json`）。
3. **洩漏檢查**（`leakage-audit`）：`odds_extraction_time < event_start_time`；L10 截止喺開賽前。
4. **Baseline**：逐腿 reliability、對市場 Brier、穩膽組合命中率同按 Sportsbet 價 ROI；按 stat、位置、是否轉隊分開報；日 cluster bootstrap。
5. **Bug 修正**（各自獨立 PR、各自帶測試）：§1.2 三項。

### Phase 2｜穩膽資格規則（Phase 1 之後，2–3 日）
改 `select_combo_1`，**每條規則逐個 ablation**：
1. Stat 白名單（§2.1）。
2. 角色適配（§2.2）。
3. 落實神經刀禁止：`cov ≤ 0.35`，fallback 唔准放寬。
4. 取消硬性 2.0–3.5x 目標，組合賠率自然出嚟。
5. 臨時「新環境」旗號：轉隊、或球隊高 usage 球員進出，今季未打夠 N 場唔入穩膽（Phase 3 完成前嘅替代）。

判決：組合宣稱命中率同實際對得上；ROI（Sportsbet 價）唔差過 baseline。

### Phase 3｜陣容變動模型（同 Phase 2 並行，改 extractor）
§2.3 全部。驗證：用 2025 年 10–11 月回放「季初用 2024-25 L10」做 baseline 對比。

### Phase 4｜機率層
預先登記三個 arm：
- **A**：EXP-05 嘅 Poisson/NB＋逐 stat 重校準。
- **B**：Beta 收縮（`(hits+a)/(n+a+b)`）取代 98% 上限。
- **C**：同去水市場機率做 logit 混合，權重只喺 dev 擬合。

過關：calibration slope ∈ [0.85, 1.15]；高機率桶殘差 CI 包 0；Brier 唔差過純市場。**坦白預期**：C 好可能將大部分權重交返市場，edge 會縮細，但組合機率會講真話。

### Phase 5｜組合同注碼
- 用同場共享比賽劇本（節奏、大勝）嘅 MC 計組合機率，取代人手相關性懲罰。
- 注碼改 quarter-Kelly，每組合上限 2–3% bankroll。

### Phase 6｜監察
- Reflector 每日按 stat／tier／新環境出 reliability 表。
- `健康.sh` 加滾動 30 日校準警報（預測同實際差 >10pp）。
- Reflector ML 退役，累積到約 2,000 行先重訓。

## 4. 發佈次序
Phase 1 bug → Phase 2 → Phase 3 → Phase 4 → Phase 5。Release 係嚴格串行（見 AGENTS.md），每個獨立 `./保存.sh --path … --expected-result …`。Phase 2 最快見效，因為直接攔住今日嗰類失手。

## 5. 現實限制
- 每日約 10 個穩膽組合，單靠今季數據要幾個星期先判得到；Phase 1 嘅上季語料係關鍵。
- 上季 Drive 語料可能係賽後重新生成（AU 有同類問題），Phase 1 要核實 `odds_extraction_time`。
- Drive 內容讀取可能 stall（見 `au-drive-content-reads-stall`），要用 SIGALRM 偵測並先複製去本機 scratch。
