# AU 速度部分重建計劃（2026-11-01）

> 用戶決定：「rebuild the speed section, first of all use the simplest code and formulas on our current speed scores … speed is not
> the condition of the horse, it should be reflecting a horse's ability … we dont have to remove the old code first, we can start using
> new code as long as we proven it has same or better performance」；「表現一樣，但 code 更簡單、bug 更少、dashboard 睇得明 this already
> a great results」。

## 原則

1. **速度 = 能力，唔係狀態。** 答「呢匹馬喺正常情況下跑得幾快」。狀態由狀態與穩定性處理。
2. **新 code 先 1:1 重現現行分數（A/A 逐匹一樣），先至改公式。** 每個公式改動獨立預先登記、獨立量度。
3. **舊 code 唔即刻拆。** 新模組喺 shadow 並行，證實同樣或者更好先切換，之後先拆舊嘢。
4. **判決照合約**（v3 + §8）。逐匹 walk-forward logistic（EXP-20261101-39）只做參考報告；用佢做判決 = 改把尺，要另外論證。

## 第 0 步：現行速度 code 盤點

排名用嘅只有一個 leaf：`pace_figure_score`（L600 環境分），維度 `pace_perf`（速度考驗背景，係數 0.1139）。

| 層 | 位置 | 做咩 |
|---|---|---|
| 抽取 | `claw_sportsbet_form._l600_delta` | Sportsbet 賽事 `Sectionals 600m` − `_lookup_standard_l600(場地, 路程)` → 寫入 Formguide `PF[L600 Delta: x]`（**只存 delta**） |
| 標準 | `engine_core._STANDARD_600M`／`_DISTANCE_ONLY_L600`／`_monotone`／`_lookup_standard_l600` | 手寫 36 個場地 × 路程表，冇地況；其餘場地用淨按路程後備 |
| 解析 | `_parse_formguide_pf_metrics`、`_parse_pf_token` | 逐仗 PF 行：`l600_delta`、`margin`、日期、路程、位置、頭馬時間、`run_kind` |
| 後備 | `_pf_backfill_for_race`、`_merge_pf_sources`、`backfill_pf_metrics`（`WC_PF_BACKFILL`） | Racenet 2026-07-13 歷史 cache；每次 enrich 都會叫，但只覆蓋 07-13 前嘅場次 |
| 正式賽過濾 | `performance_pf_metrics` | 剔走試閘行，再重算 aggregates |
| 聚合 | `_pf_aggregates` | `own_l600_delta = l600_delta + margin × 0.17`；近期加權 0.8^k（EXP-30）；另外計一堆冇人用嘅 `_avg`／`_best` |
| 場內統計 | `au_auto_orchestrator._build_field_summary` | Logic 全部馬嘅 own／race 場均同 pstdev |
| 分數 | `RacingEngine._pace_figure_score` | own（≥3 匹）否則 race；60 − 20z，clip |
| 顯示 | `_l600_speed_brief`、`_latest_l600_rt_*`、`_sectional_trend_brief`、`pace_perf` anchors | 部分讀死欄位 |
| 並存 | `sectional_score`（0 權重）、`full_time_speed` overlay（RQ 全程，gain 1.5） | |

## 已知 bug／唔合理嘅邏輯

1. **Formguide 只存 delta**：標準一改歷史就錯（08-23 改表後 7,547 場前後 delta 唔一致；EXP-31）。應該存原始秒數。
2. **場內其實只係「按輸距排」**：同一場賽事 L600 對全場一樣，`own` 場內排名 = 終點輸距排名（同真實末段 600m 相關 0.599）。
3. **假設 600m 時同頭馬齊頭**：`+ margin × 0.17` 將全部輸距當成末段造成。800m 位置可以修正（RQ 真值測試：0.59 → 0.906）。
4. **Sportsbet「賽事 L600」定義唔明**：比頭馬末段慢約 1.4 秒、比 600m 領放馬慢約 0.7 秒（3,055 場 RQ 對照）。
5. **標準表**：只有 36 個場地、冇地況、手寫冇更新；場地平均大部分係馬匹質素（EXP-32）。
6. **死欄位**：`_PF_SPLIT_KEYS` 除 `l600_delta`／`own_l600_delta` 外 0% 有值；`timing_600m_*`（Racenet 遺留）仲有顯示代碼讀；`early_*_pace` 永遠 null。
7. **固定 0.17 秒／馬位**，冇按速度或者路程調。
8. **全程速度係 overlay**，同速度維度分開，dashboard 要另外顯示。

## 新速度部分（目標設計）

每仗往績（只用正式賽）量兩樣，全國覆蓋：

- **末段速度**：本駒末段 600m 估算 = 由 RQ 真值學出嚟嘅估算式（800m／400m 位置 + 輸距 + 賽事資料）；昆士蘭有 RQ 就用真值。
- **全程速度**：頭馬時間 + 輸距推完成時間；昆士蘭用 RQ 真值。

一個 point-in-time 標準（路程曲線 + 地況 + 同日場地修正；場地只扣純路面效應）兩樣共用。
每匹馬：各仗合併（方法要測：近期加權 vs 穩定可重複嘅較好水平），證據少就向中間收縮。同場比：60 − 20z。
Dashboard：逐仗證據（日期、場地、估算末段、對標準差）。

## 步驟

| 步 | 內容 | 判斷 |
|---|---|---|
| 0 | 盤點（本文件） | — |
| 1 | `au_racing_engine/speed.py`：最簡單嘅純函數，1:1 重現現行 `pace_figure_score` | A/A：全語料逐匹 0 差 |
| 2a | 存原始 L600 秒數（抽取層），標準可以重算 | 正確性修正（§7），排名唔變 |
| 2b | 末段估算式（RQ 學，point-in-time） | 預先登記，v3 + §8 |
| 2c | 全程速度併入速度維度（取代 overlay） | 預先登記 |
| 2d | 標準（point-in-time，只扣路面） | 預先登記（EXP-39：單獨換標準唔會加分，要同 2b 一齊睇） |
| 2e | 聚合方法（能力取向） | 預先登記 |
| 3 | 生產 shadow 並行 + forward 監察 | 證實同樣或者更好先切換 |
| 4 | 拆舊 code | 切換之後 |
