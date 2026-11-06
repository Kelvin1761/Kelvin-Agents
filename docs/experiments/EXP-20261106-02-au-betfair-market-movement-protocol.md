# EXP-20261106-02 預先登記：Betfair 交易所價格走勢有冇訊號（AU 純種馬）

- **日期**：2026-11-06（寫喺任何數據下載同量度之前）；**平台**：AU；**類型**：落注層研究，**唔係模型改動**。
- **用戶**：「start tracking market movements, and see if there is signals or like bets we should made base on the movements」；
  同意先用免費歷史數據回測，證實有訊號先考慮 API（live key 一次過 £299）。
- **背景**：EXP-20261104-10 —— 模型喺市場價以外冇資訊；Betfair BSP 盲買打和（−3%～+6%，CI 跨零）；
  要贏要「市場唔知」嘅資訊。免費 BSP CSV 嘅 `morningwap`／`ppwap` 唔係時點價（2026-11-06 篩查：34.9% ppwap 低過 ppmin、
  morningwap 書率 138%，按佢分走勢造出 +50% ROI 假象）→ 今次**唔用**呢兩欄。

## 數據

- **價格**：Betfair Historic Data **Basic**（免費、每分鐘最後成交價 LTP、冇成交量），AU 純種馬 **WIN** 市場，用戶自己登入下載。
  原檔當不可信數據：放 `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/betfair-basic/raw/`，解析腳本放第二個目錄，`python3 -I`。
- **結算價**：同一 `selection_id` 嘅 BSP（Basic 檔自帶，或者 `dwbfprices` CSV），扣 **5% 佣金**；`win_lose` 做結果。
- **時點**：以市場 `marketTime`（預定開跑）做 T0；取 T−60、T−15、T−5 分鐘或之前最近一個 LTP，**一定要 `inPlay == false`**。

## 資料檢查（要全部過先睇結果；唔過就停，報數據問題）

1. T−5 同 T−60 都有 LTP 嘅馬 ≥ 80%（按場計，剔走 LTP 缺失嘅場，唔補值）。
2. T−5 LTP 落喺 `[ppmin, ppmax]`（BSP CSV）範圍內 ≥ 95% —— 防止重演 WAP 假象。
3. 冇一個 LTP 時間戳 ≥ 真實開跑時間（`inPlay` 轉 true 嘅時間）。
4. 場內 T−5 書率中位 95%–110%。

## 特徵（全部喺 T−5 拎得到）

- `p5` = 1/LTP(T−5)，場內正規化；`m60` = log(LTP(T−5)/LTP(T−60))；`m15` = log(LTP(T−5)/LTP(T−15))。負 = 入水。

## Q1 訊號：走勢喺 T−5 價／BSP 以外有冇資訊

- 條件 logit（場內 softmax），時間切：頭 50% 賽日 fit、後 50% 測。
  - A：logit(p5) vs logit(p5) + m60 + m15
  - B：logit(BSP 隱含機率) vs logit(BSP) + m60 + m15
- OOS Δlogloss，賽日 bootstrap 2000、seed 7。

## Q2 落注規則（四條，Holm 校正；只喺後 50% 賽日判）

全部 BSP 落贏注、扣 5% 佣金、平注：
- R1 跟入水：m60 ≤ −0.223（入水 ≥ 20%）
- R2 反入水：同 R1 嘅場，買場內 T−5 第二熱門以外最熱門而冇入水嗰匹（固定定義：m60 > −0.051 嘅最細 LTP）
- R3 跟飛起：m60 ≥ +0.223
- R4 R1 限 T−5 LTP ≤ 10

ROI、賽日 bootstrap 95% CI。

## 判決（預先固定）

- **值得做 API**：Q1-B 嘅 Δlogloss CI 全負（BSP 以外有資訊），**或者** Q2 某條規則 Holm 後 p < 0.05 而且 CI 下限 > 0。
- 否則：**唔開 API**，記錄「1 分鐘 LTP 走勢喺 BSP 以外冇訊號」；如果用戶仍然想，可以考慮付費 Advanced（有成交量）另開協議。
- 唔准換時點（例如試 T−30、T−2 揀最好）、換門檻或者換切法去救結果。
- 只係研究：**唔會自動落注**；就算過閘，落注同 API 都係用戶決定。

## 修訂 1（2026-11-06）：Basic 歷史數據資料檢查唔過 → 停；改用 API 自己記錄（**冇睇過任何賽果**）

用戶下載咗 Basic（2025-11 → 2026-10，131,724 個市場檔，1 個壞檔剔走）。解析：`scratch/au_betfair_basic_parse_20261106.py`
→ 16,999 場 AU 純種馬 WIN、163,088 匹。判決腳本 `scratch/au_betfair_basic_judge_20261106.py` 喺資料檢查唔過時即停，**Q1／Q2 冇跑**。

| 檢查 | 要求 | 結果 |
|---|---|---|
| 1. T−60 同 T−5 都有 LTP | ≥ 80% | **67.1%** ❌（每月 62–72%；細場開跑前一個鐘冇成交） |
| 2. T−5 LTP 喺 ppmin–ppmax 內 | ≥ 95% | **80.9%** ❌（37,204 匹；BSP 配對 100% 一致；連成交 ≤1 分鐘嘅價都只 82% → ppmin／ppmax 本身唔可靠） |
| 3. 開跑早過 T−5 | 0 | **13 場** ❌ |
| 4. T−5 書率中位 | 95–110% | 100.6% ✅ |

另外 T−5 LTP 對 BSP 中位差 14.5%（≤ $10：10.5%）—— 分唔開真走勢同過期 LTP。用戶揀（2026-11-06）：「用 API 自己記錄」。

### 修訂後數據同規則（其餘不變）

- **記錄器**：`.agents/skills/au_racing/au_betfair/au_betfair_logger.py`（只讀 client，`placeOrders` 等一律拒絕）；launchd 每 60 秒快照
  未來 75 分鐘開跑嘅 AU 純種馬 WIN 市場：每匹 LTP、最佳買價／賣價同量；每晚 23:45 結算（WINNER／LOSER、actualSP）。
  delayed key：價延遲 1–180 秒（每行記 `delayed`），冇成交量。資料：外置碟 `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/betfair-market-log/<悉尼日期>/`（用戶 2026-11-06 要求；冇掛載就停手唔寫入內置碟、每晚推 Telegram）。
- **時點價**：T−60／T−15／T−5 = 開跑前 [70,60]／[18,15]／[8,5] 分鐘窗口內最後一張 `OPEN` 兼未開跑快照；
  價 = **最佳買賣中間價**（兩邊都有）否則 LTP；記低用咗邊個。冇齊三個時點 → 唔計。
- **資料檢查（替換上面四項）**：(1) 合資格場 ≥ 60% 已結算場；(2) T−5 中間價買賣差 ≤ 2 格嘅馬 ≥ 80%；
  (3) 冇一張用到嘅快照係 `inplay`；(4) T−5 中間價書率中位 95–110%；(5) T−5 中間價對 BSP |log| 中位 ≤ 0.15。
- **樣本**：夠 **2,000 場**合資格賽事（forward tracker `betfair_market_log`，第一次夠數推 Telegram）先跑 Q1／Q2；
  切法改為頭 50% 賽日 fit、後 50% 測（同原協議）。
- 判決規則、四條規則、Holm、唔准換時點／門檻全部不變。

## 補充（2026-11-06，用戶：「can we track place as well」）

記錄器加埋 **PLACE** 市場（同一個快照 job）：目錄記 `type`、`event_id`，快照記 `winners`（派位數）。PLACE 市場名係「To Be Placed」，
冇 Pace／Trot 字眼，所以只收同 event、同開跑時間有純種馬 WIN 市場嘅 PLACE。**PLACE 只係記錄，唔喺今次預先登記範圍**；
2,000 場進度照舊只計 WIN（狀態檔另列 `place_markets_collected`）。要分析位市場走勢就另開協議。
