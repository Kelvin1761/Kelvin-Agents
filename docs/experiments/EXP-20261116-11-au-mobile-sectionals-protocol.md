# EXP-20261116-11 預先登記：sportsbetform 手機版逐駒分段（前段／末段速度）

- **日期**：2026-11-16；**平台**：AU；**類型**：新數據來源 + 候選特徵（只做離線評估，唔改生產模型）。
- **寫喺量度之前**：呢份喺睇任何候選結果之前寫好、commit。抓取同覆蓋率統計可以同時做（唔睇賽果）。

## 背景（先查咗舊記錄）

- EXP-20260831-09：桌面版 `Sectionals 600m` 係 **race-level**，唔係逐駒。
- EXP-20261101-39：用 Sportsbet 桌面數據，L600 標準已到資訊上限；「Sportsbet 冇逐駒分段」。
- EXP-20261101-42：Racing Queensland 逐駒 200m 分段（5,413 場，只得 QLD）：前段／L800／L600／L400／L200
  **單獨全部輸畀完成時間**；疊加喺完成時間上 log-lik 微升但場內 AUC 冇一個 CI 全正，加前段反而 CI 全負。
  → 呢個係強先驗：逐駒分段大概唔會改善排名。今次新嘅地方只係**全國覆蓋**（唔止 QLD）同**直接接上現行綜合分**。

## 來源

`https://www.sportsbetform.com.au/mobile/{eventId}/{n}/` 嘅 Speed 分頁（`mobile-sectional-times`）係**成場**
server-render（`FormGuide.getSectionalsCacheable(sportsbetEventId)`），所以每場一版就夠（唔使逐匹馬）。
每匹馬最近 10 仗，每仗：名次／馬數、場地、狀況、日期、路程、本駒完成時間、6 格 200m 分段（1000m／800m／600m／400m／200m／Fnsh）。
Sportsbet 自己計嘅 EARLY／MID／LATE／AVG 摘要係用「抓取嗰刻」嘅 10 仗計，**唔用**（point-in-time 唔安全）。

## 語料

- 我哋有評分（`Meeting_Auto_Scoring.csv` 嘅 `final_rank_score`，live 版）而 Sportsbet `AllRacing/{day}` 仲攞到 event ID 嘅賽日：
  2026-11-06 → 2026-11-15（AllRacing 只回溯約 10 日；11-04／11-05 已經 400）。賽果：`AU_Historical_Raw_Race_Results.csv`。
- 每場一版，隔 25 秒，非 200 即停，唔重試；21:35 前收手（避開 22:00 生產排程）。抓到幾多用幾多，全部如實報。

## 特徵（三個 arm，同一家族，Holm）

逐仗只用日期**嚴格早過**今仗嘅行（同日亦剔），而且行要喺我哋賽果 CSV 以外都得（純用頁面資料）。
每仗計：
- `late`：本駒 L600 速度 km/h = 600 / (400m + 200m + Fnsh 三格) × 3.6（三格齊先有）。
- `early`：L600 之前嘅平均速度 = (路程 − 600) / (完成時間 − L600) × 3.6（路程 > 800m 先計）。
- `avg`（對照）：本駒全程平均速度 = 路程 / 完成時間 × 3.6。呢個基本上係「完成時間」，桌面版已經有（頭馬時間＋輸距）。

每個量喺 (場地, 路程段 ≤1100／1101–1400／1401–1800／>1800) 內標準化做 z（樣本 < 20 退返場地，再退返全體）；
標準只用 **2026-11-06 之前**嘅行（全部目標賽事之前）。逐匹特徵 = 最近 ≤4 仗有值嘅 z 平均。冇值 = 場內 0（唔郁）。

- arm **E**：`early`
- arm **L**：`late`
- arm **A**：`avg`（對照；如果 E／L 唔贏 A 又唔加到落 A 上面，就係同完成時間重複）

## 幅度同判決

- 候選分 = `final_rank_score + β·z場內(特徵)`。β walk-forward：每個賽日用**之前賽日**嘅結果 fit
  conditional logistic（入頭三 ~ a + b·(綜合分 − 場均) + c·z），β = c/b（b ≤ 0 → 0），夾 [−10, 10]；
  頭 2 個賽日冇訓練 → β = 0。
- 判決器：`model_evaluation_decision.evaluate_full_record(domain="au", mode="walk_forward_oos")`，賽日 bootstrap 2000、6 個時間塊。
- 另報（唔係閘）：逐匹 top-3 log-likelihood Δ（walk-forward）、場內 AUC Δ、單獨 leaf AUC、同 `avg` 嘅相關。

## 功效（量之前寫）

約 10 個賽日、最多 ~500 場。Gold／Good 嘅賽日 bootstrap CI 半闊預計 ±3pp 以上；EXP-42 見到嘅效應係 0.0004 nats／上名馬，
呢個語料**一定量唔到**。所以：
- 判 REJECT 只可以因為**明確有害**（primary 點估計負且時間塊唔達標、或者 ranking CI 全負）。
- 「CI 跨零」= 量唔到，判 **NEEDS MORE TESTING**，跟住要決定值唔值得每日累積語料。

## 洩漏檢查（量之前定）

1. 頁面有冇包今仗（同日同場地行）—— 有就剔，同埋數幾多。
2. 賽後頁同賽前頁同一仗嘅分段係咪一樣（今晚 22:00 前抓一版明日場次、賽後再抓同一場比較）。
3. 試閘有冇出現喺分段表（同 long-form 嘅 `isTrial` 對）。
