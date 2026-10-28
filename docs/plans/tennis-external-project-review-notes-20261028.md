# Tennis Wong Choi：外部項目比較及待辦研究筆記

- 建立：2026-10-28（Australia/Sydney）。
- 狀態：收集項目中；尚未啟動新實驗，未批准或部署任何候選模型。
- 用戶意圖：逐個外部項目一齊睇，累積到同一份筆記；完成比較後，統一安排改善及實驗。
- 使用方式：每個項目新增一節，候選想法集中入下方清單；相似想法合併，保留來源及舊實驗判決。
- 「一次過做」指統一規劃及安排執行；多項特徵不可只做一次合併測試，仍須逐項消融。
- 本文件係研究筆記，唔係事前登記協議、正式模型說明或改善證據。

## 項目清單

| 編號 | 項目 | 比較日期 | 狀態 |
|---|---|---|---|
| P01 | [tennis-analytics-prediction](https://github.com/theayobamiakin/tennis-analytics-prediction) | 2026-10-28 | 已讀 README、advanced model、公開 metrics 及測試；未獨立重跑 |
| P02 | [Tennis-Modelling](https://github.com/DanielTomaro13/Tennis-Modelling) | 2026-10-28 | 已讀 features／sim／evaluate／predict／ratings、config 及公開 backtest；未獨立重跑 |
| P03 起 | 待用戶提供其他項目 | — | 待比較 |

## 訓練資料範圍（2026-10-28 用戶補充）

用戶明確允許：可以用其他莊家嘅歷史資料及 ROI 做訓練用途／研究，資料不足時尤其有用。
呢個更新取代本筆記之前「所有市場資料只用 Sportsbet」嘅限制；歷史實驗文件保留當時約束，唔倒改舊判決。

- 可用逐場歷史賠率、賽果、可證明賽前嘅網球資料做模型訓練；開發期歷史 ROI 可作策略／門檻研究指標。
  一個公開總 ROI 數字本身唔係逐場訓練資料，唔可直接當球員實力特徵；未來收益亦不可倒流入當場預測。
- 凍結 book／quote type／timestamp／market contract／source／split；同一場多個 book 係相關觀察，唔當多場獨立樣本；切 train/dev/test 時同一場所有 book 必須留喺同一時間 fold。
- 跨 book 嘅 closing 價可以標明做收市基準、研究或 auxiliary target；不能當我哋較早預測時已知嘅輸入。
  無 timestamp 嘅資料只作有限歷史研究，唔冒充已驗證 PIT 或可執行回報。
- 用多 book 資料訓練，不等於上線要多 book 同時有價；需驗證只提供 Sportsbet 可用輸入時仍可定價。
  如果模型實際要新 book 價做輸入，方法論及資料依賴必須另行明示。
- 其他 book 嘅開發期 ROI 不能代替 Sportsbet forward 表現；不以今日結果挑最好 book／年份／價型去救失敗候選。
  同一預先鎖定候選同時報 LL／Brier、校準、coverage、分 book 結果及收益不確定性。
- 已看過或已用來選參嘅資料全部標 dev；擴充 bookmaker 資料唔會令舊 holdout 再次變成 untouched。

## P01：tennis-analytics-prediction

### 可核對來源

- [README](https://github.com/theayobamiakin/tennis-analytics-prediction/blob/main/README.md)
- [模型程式](https://github.com/theayobamiakin/tennis-analytics-prediction/blob/main/src/advanced_betting_model.py)
- [公開評估](https://github.com/theayobamiakin/tennis-analytics-prediction/blob/main/models/advanced_match_winner_metrics.json)，檢視時 blob SHA：`19ba49e7f35294fce903f9bdc5bf2548758c1088`。
- [測試](https://github.com/theayobamiakin/tennis-analytics-prediction/blob/main/tests/test_advanced_betting_model.py)，檢視時 blob SHA：`fb0c55e01a1b91be1270df90a1d56d9b909514c4`。
- 連結指向可變 main；正式重現之前須凍結外部 commit、程式及原始資料 hash。今次未下載或執行對方模型。

### 公開結果及解讀

同一批 7,051 場 2025 年起嘅 odds-linked 測試：

| 指標 | 模型 | 去水市場 |
|---|---:|---:|
| Accuracy | 68.3449% | 68.3307% |
| Log loss | 0.590846 | 0.591276 |
| Brier | 0.203002 | 0.203313 |

模型減市場 ΔLL = −0.000430，paired bootstrap 95% CI [−0.001431, +0.000617]，500 次重抽。
方向輕微正面，但未證實優於市場。2,427 個歷史假設投注 ROI +1.6325%；歷史價無確切 snapshot timestamp，不能當可執行回報。
以上係作者公開報告，非我哋獨立重現；不可跨語料同我哋嘅 LL／ROI 直接比較。

### 值得保留嘅想法

1. 市場做底：`logit(p_final) = logit(p_market_fair) + regularised tennis correction`。
   研究額外特徵對市場嘅增量，而非只對較弱 Elo 對照；市場輸入必須明示。
2. 開發期比較 proportional／power／Shin 去水，鎖定後先驗證；我哋已有五種方法嘅基建，唔使照抄工具。
3. 場地樣本少時向 overall Elo 收縮：對方權重 `n / (n + 20)`；呢個只係對方設定，未證明適合我哋，唔直接採用 20。
4. 發接球表現按對手實力調整；用局數幅度補充勝負資訊。
5. 分期做擬合、選參、校準及測試；球員 A/B 交換對稱，並報 tour／surface 分層。

### 程式檢視見到嘅限制

- 特徵按 `tourney_date / tour / tourney_id / match_num / match_id` 排序更新；部分 workload 日期用 odds-linked `match_date`。
  日期語義及跨賽事結果可用時間需驗證。呢個係洩漏風險，今次未用 raw data 證實實際污染場數。
- 訓練有 rest_days／matches_14d／minutes_14d；`prediction_frame` 將呢幾項設 NaN，存在訓練同實際預測輸入差異。
- 歷史價接近最新賽前價但無精確時鐘；唔能夠同我哋 earliest pre-match quote 混用。
- 對方評估重點係 ATP/WTA main-tour 勝負，唔係我哋全部 Challenger／ITF／props。
- 測試涵蓋去水及特徵翻轉，未足以單憑綠燈證明整條時間隔離安全。

## P02：DanielTomaro13/Tennis-Modelling

### 可核對來源及範圍

- [README](https://github.com/DanielTomaro13/Tennis-Modelling/blob/main/README.md)：註明 September 2026 Actions 暫停，網站／資料停留最後 build；唔當當日 live forecast。
- [features.py](https://github.com/DanielTomaro13/Tennis-Modelling/blob/main/src/features.py)，blob `311f8e0094e17dd1124e28a2703c2f572dc90d01`。
- [sim.py](https://github.com/DanielTomaro13/Tennis-Modelling/blob/main/src/sim.py)，blob `17937451bd1e65fafbfcc7b7c314c77bc374d217`。
- [evaluate.py](https://github.com/DanielTomaro13/Tennis-Modelling/blob/main/src/evaluate.py)，blob `e01c4aa7351f652a403484ce55d595feb79afa81`。
- [predict.py](https://github.com/DanielTomaro13/Tennis-Modelling/blob/main/src/predict.py)，blob `56333b657533b94fc250c2ba9195bb599efc0c9b`。
- [ratings.py](https://github.com/DanielTomaro13/Tennis-Modelling/blob/main/src/ratings.py)，blob `454a9c80a01a3a58608e1fd43ea3eba1d2d383c0`。
- [config.yaml](https://github.com/DanielTomaro13/Tennis-Modelling/blob/main/config.yaml)，blob `bb44ada95b3802966e9a5a24aed9b1f3782d0e3b`。
- [reports/backtest.json](https://github.com/DanielTomaro13/Tennis-Modelling/blob/main/reports/backtest.json)，blob `a0516c0f93b0030804b6b515277de5cbac63ae10`。
- 只讀程式及公開結果，冇執行作者程式或模型；main 可變，正式重現仍需凍結 commit／raw data。

### 公開結果：唔係已證明贏市場

程式以 2024 起作測試；serve profiles 凍結喺 2024 之前，Elo 按歷史次序更新。
公開報告如下，市場係 closing odds proportional 去水，唔係 Sportsbet 開盤價：

| Tour | 全部 N | 有市場 N | 模型 LL（同有市場群體） | 市場 LL | 模型−市場 |
|---|---:|---:|---:|---:|---:|
| ATP | 7,368 | 7,362 | 0.6301 | 0.5946 | +0.0355 |
| WTA | 6,934 | 6,927 | 0.6288 | 0.5905 | +0.0383 |

兩邊都落後市場。全部樣本 blend 對 Elo-only：ATP LL 0.6300 vs 0.6310；WTA 0.6287 vs 0.6288，增量細且此報告冇 paired CI。
Elo-only fallback ATP 2,843/7,368、WTA 3,271/6,934，serve stats 覆蓋唔完整。
已讀 backtest 只驗勝負；不能由勝負 LL 推論 totals／handicap／ace 等 props 已過閘，亦冇從呢個檔案取得可核對盈利證據。

### 值得學嘅設計，同我哋嘅差別

1. **精確機率遞推引擎**：實際 `sim.py` 用 closed-form／dynamic programming，
   每分→保發→單盤→全場，輸出同一個 joint distribution 嘅勝負、盤數、局數及讓局。
   README／config 仍提 Monte Carlo，但現有單打程式唔係靠抽樣。
   我哋已有 hold→set→match Monte Carlo，引擎換 DP 首先係消除抽樣誤差／工程速度候選，唔等於改善 hold estimate 或勝負辨識力。
2. **時間衰減 + 發球分數曝光量加權**：`weight=2^(-age/half_life)`，再乘 service／return points；
   樣本按加權 points 收縮，唔只按場數平均。對方 half-life=365、prior=250 points、min=60 係佢設定，唔直接搬。
   我哋 serve profile 用最近 25 場及最少 5 場，呢個係可獨立消融嘅實質差別。
3. **新資料來源**：Match Charting Project 的 Overview aggregates 可作 serve／return／ace／double-fault 資料候選。
   它係被 charted 嘅子集，唔等於完整 tour；要量時間新鮮度、球員／場地覆蓋、選樣偏差及授權，避免同現有來源重複計同一場。
4. **勝負同衍生盤一致性**：用 Elo／serve blend 勝率反求 point edge，再重算全本盤。
   呢個係不同於現有 match-winner 與 props 各自輸出嘅設計，但一個勝率唔足以唯一決定兩位球員保發率或總局數；需保留 serve-level 證據及多市場驗證。
5. **Ace／DF 建模用 rate × opportunities**：方向合理，但我哋已有 ace exposure 候選及研究工具；
   不能當新模型即刻採用，更不能只因同一分佈輸出好多市場就自動開 family。

### 程式檢視見到嘅問題／證據限制

- `project_match`／`distributions` 按盤號固定 A、B、A 輪流首發，state 冇保存上一盤完結後 server。
  例如首盤 6-4 有 10 局，下一盤應沿用同一首發方向；固定換人係可辨識嘅規則錯誤。
  我哋同類修正已記 [EXP-20261026-05](../experiments/EXP-20261026-05-tennis-simulator-service-order.md)，唔應搬返呢個做法。
- Ace／DF exposure 用 `exp_games_a`（A 贏嘅局數）乘 `game_expected_points(p_a)`，當成 A 發球 points。
  贏局數唔等於發球局數，break 亦計入贏局；呢個量綱／計數錯配會污染 ace means。需追蹤真正服務局及 tie-break points，唔照抄。
- `features._f` 缺失／非數字回傳 0；部分比例有分母保護但無完整值域／缺值旗標。不能假定缺 ace／serve count 就等於零。
- Config 註解提到用 holdout testing 揀 Elo 比重；無獨立 untouched 分割／選參紀錄之前，唔因程式標榜 leakage-safe 就當完整 OOS 證據。
- Backtest serve profiles 固定喺測試前，但 production 用更新後 profiles；係合法固定前期基準，但未完全重演每日更新嘅生產流程。
- Elo 按日期排序逐行更新，無同日開賽時間／結果可用時間證據；同日多場次序需另驗，今次未量實際污染場數。
- `anchor_to` 調整 point edge 只係令一個目標勝率相近，唔證明整個 props distribution 校準。缺 profile 用 league mean 亦要向用戶標明薄資料，唔當實際球員資料。

### 本次結論

保留 DP 引擎參考、曝光量／時間加權、MCP 來源及跨市場一致性研究；拒絕直接搬模型／參數。
作者公開回測未贏市場，程式存在可辨識正確性問題；今次冇新 A/B 或改善證據。

## 已做研究：避免重複及改寫失敗判決

| 方向 | 既有記錄 | 已知結果／約束 |
|---|---|---|
| Elo 骨幹及場地混合 | [EXP-20261009-01](../experiments/EXP-20261009-01-tennis-elo-backbone.md) | 歷史 C0/C2 有增量；forward shadow 未完成 promotion 證據 |
| 移除全部或單項 nudges | [EXP-20261027-06](../experiments/EXP-20261027-06-tennis-stored-nudge-ablation.md) | 移除候選 REJECT；不可憑直覺刪分項 |
| 過往局數實力 | [EXP-20261027-07](../experiments/EXP-20261027-07-tennis-game-share-strength.md) | 有方向訊號，確認 CI 跨零，未過上線閘 |
| 連續排名先驗 | [EXP-20261027-08](../experiments/EXP-20261027-08-tennis-continuous-rank-prior.md) | 預測有增量證據，盈利／上線 REJECT |
| 對手調整發接球 | [EXP-20261027-09](../experiments/EXP-20261027-09-tennis-opponent-adjusted-serve-return.md) | 未過 dev 穩定性，仍輸市場，REJECT 上線 |
| WTA fresh serve history 直接接線 | [EXP-20261026-04](../experiments/EXP-20261026-04-tennis-wta-fresh-history.md) | 直接接線及 90 日硬截 REJECT；新資料唔自動等於更準 |
| 既有市場 residual／校準 | [既有 audit](../../tennis-wong-choi/docs/performance-audit-2026-08-21.md) | 已有 props 研究失敗；勝負 fixed-logit offset 係不同設計，但須先完整檢索舊證據，唔假定一定新或有效 |

舊審計列出嘅 bug 唔自動代表今日仲未修；每次實作前對照最新 main，同時保留歷史判決。

## 集中候選清單（暫定，等其他項目比較後再排序）

| ID | 想法 | 來源 | 下一步／依賴 | 狀態 |
|---|---|---|---|---|
| C01 | 勝負市場 fixed-logit offset + 網球特徵修正；可先用多 book 歷史訓練 | P01 + 用戶補充 | 查舊 residual 實驗；明示輸入 book，驗證只用 Sportsbet 輸入可行；同場比較及新 forward 證據 | 待整合，未開實驗 |
| C02 | 勝負去水方法比較，分 book 研究再驗 Sportsbet | P01 + 用戶補充 | 每個 book 同一筆配對價；標 opening／closing，dev 選方法；獨立於 C01 | 待整合，未開實驗 |
| C03 | 場地樣本量驅動嘅 Elo 收縮 | P01 | 同固定混合基準比較，須可靠場地及歷史樣本數；唔改已 frozen shadow | 待整合，未開實驗 |
| C04 | 訓練／預測一致性及資料來源時間檢查 | P01／P02 | 核對日期、當時已知資料、報價、缺值及球員方向；先盤點現有修正 | 待整合，未開實作 |
| C05 | 發接球／局數／排名候選歸併 | P01／P02 + EXP07/08/09 | 只記低重疊；新假設須解釋同失敗設計嘅實質分別，保留舊 REJECT | 去重清單，唔重跑舊候選 |
| C06 | Serve profiles 時間衰減、按 points 曝光量加權及收縮 | P02 | 分開比較 recency／exposure／prior，每項及組合消融；與 EXP09 保持可辨識差異 | 待整合，未開實驗 |
| C07 | MCP serve／return 資料可用性盤點 | P02 | 先量授權、日期、身份、覆蓋及選樣偏差；canonical match 去重，再考慮新 source A/B | 待整合，未抽資料 |
| C08 | 精確 DP 取代或核對 Monte Carlo | P02 | 先做小範圍 kernel parity，正確 server／tie-break state；量速度、數值誤差，模型精度獨立量 | 待整合，未開實驗 |
| C09 | Match-winner 與 props 聯合一致性／anchor | P02 | 不只配勝率；驗證總局、set score、handicap，避免單一目標過度約束；先查已有設計 | 待整合，未開實驗 |
| C10 | 多 book 訓練資料及 ROI 診斷規格 | 用戶補充 | 保留來源、價格時間與市場合約；dev-only ROI，不挑最好 book，Sportsbet forward 另驗 | 已確認允許，待實驗規劃 |

## 完成項目比較後嘅統一執行框架

1. 合併相同想法，標示已有工具、缺資料、已否決及真正新假設；先確認工程缺陷係咪仍存在。
2. 以同一份凍結語料、同一可用時間及同一群體量 baseline；允許多 book 歷史訓練／開發期 ROI，分 book 報告，Sportsbet forward 可執行性另驗。
3. 每個模型假設另寫 `docs/experiments/` 事前登記；沿用 frozen tennis ruler、舊 dev/holdout 規則，唔以已睇過嘅資料冒充全新 holdout。
4. 工程正確性修正同模型候選分開量；多特徵須單項及組合消融，唔靠一個合併結果歸功。
5. 報同場 paired LL／Brier、分層、coverage／缺值，以及可執行價格下嘅 P/L／ROI／CLV；未證實可執行就只報研究診斷。
6. 開發失敗即保留 REJECT，不換窗或挑 subgroup 救結果；過開發閘先凍結候選做新 forward shadow。
7. 正式上線仍需完整 gate；筆記中嘅優先次序或外部正 ROI 都唔代表已批准部署。

## 後續項目記錄格式

每個新項目記：URL／檢視日期／版本、讀過嘅程式、作者結果及限制、同我哋重疊之處、真正新想法、資料與時間風險、候選 ID、實驗依賴。
完成全部比較之前先累積筆記，唔因逐個項目出現新功能就即時改正式模型。
