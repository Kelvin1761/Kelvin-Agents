# EXP-20261116-19 預先登記：sportsbetform 手機版逐駒分段（前段／末段速度）

> 編號更正：原本以 EXP-20261116-11 登記（commit `e9bf1628`，內容同時間未改），但 main 上 -11 已經俾 HKJC 用咗，改做 -17；之後 -17 又俾 tennis 用咗，再改做 -19。

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

## 補充登記（2026-11-16 19:0x，抓取未完、未睇任何結果）

Kelvin 經主 session：「照做落去 and see if we can find any signals to improve the analysis performance there」。加一個 arm：

- arm **D**（末段減速）：每仗 `fade` = 最後 200m 速度 ÷ (600→400、400→200 兩段平均速度)，即 `Fnsh` km/h 對前兩格 km/h 平均嘅比率
  （三格齊先計；越大 = 收得越好）。同樣喺 (場地, 路程段) 內 z、最近 ≤4 仗平均。同一家族，Holm 由 3 個 arm 變 4 個。
- **同場名次相對值計唔到**：頁面只有今場出賽馬嘅往績，冇往績嗰場其他馬嘅分段，所以「喺嗰場入面排第幾」量唔到。
  （要做就要抓嗰場往績本身嘅頁，即係歷史 event ID —— AllRacing 只回溯 ~10 日，攞唔到。）唔加，唔係 REJECT。

## 補充登記 2（2026-11-16 19:1x，抓取未完、未睇任何候選結果）

Kelvin 經主 session（「好，交俾佢」）加候選。

- arm **E2**（前段速度，可變基準）：前段長度 = 路程 − 200 × 有值格數；前段時間 = 本駒完成時間 − 有值格嘅時間（由 km/h 反推，避開 0.1 秒捨入）。
  前段長度 ≤ 0 當缺值。同 E 一樣喺 (場地, 路程段) 內 z、最近 ≤4 仗平均。E2 係 E 嘅消融兄弟：兩個都報，邊個都唔可以揀完再報。
  Holm 家族 = E、E2、L、A、D 共 5 個。
- **Sportsbet 摘要（EARLY／MID／LATE／AVG）唔開臂**：量度（未睇賽果）證實佢係頁面顯示嘅 ≤10 行嘅平均 ——
  AVG 同 `路程/時間` 一樣（中位差 0.003）、LATE = 最後兩格 km/h 平均（0.025）、EARLY ≈ E2 嘅前段速度（0.033，76% 差 ≤0.15）。
  所以佢唔係新資訊；而且「最近 10 仗」由抓取時間決定，唔用佢，用行重算。
- **`RacecardWithContext` 欄位**（`speed`、`dryRating`、`wetRating`、`horseJockey`、`expectedSettlingPosition`、勝率／位率）：
  呢次**唔開臂**。我哋只可以喺賽後抓舊賽事嘅 API，未知佢會唔會賽後更新、`speed`／`rating` 計法未知 → leakage audit 答唔到 → flag。
  做法：抓少量賽後 API，用我哋賽前 Racecard 嘅生涯紀錄／騎師配搭對 `winPercentage`／`horseJockey` 有冇包今仗；
  再用賽前快照（今晚抓 11-17、聽日賽後再抓同一批）比 `speed`／`rating` 有冇郁。
  `expectedSettlingPosition` 疑似就係 EXP 已 REJECT 嘅 Sportsbet Speedmap（記憶 `au-sportsbet-speedmap-rejected`），要對返。
- **試閘 600m**：只量覆蓋率（long-form 列表），唔開臂。
