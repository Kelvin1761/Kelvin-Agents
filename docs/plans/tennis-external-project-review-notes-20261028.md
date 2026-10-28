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
| P03 | [tennis-match-predictor](https://github.com/coenensam/tennis-match-predictor) | 2026-10-28 | 已讀 README、8 個核心 modules 及 test_devig；未下載語料或獨立重跑 |
| P04 起 | 待用戶提供其他項目 | — | 待比較 |

## 參考及原始資料 URL 登記表

2026-10-28 用戶另要求保留 URL，方便之後實驗查 reference／data source。
三個項目首頁已在上表；以下係從已讀程式／設定辨識嘅上游入口。呢次未下載原始語料，未驗證目前可存取性、完整性或授權適用範圍；入口存在唔等於已備妥實驗資料。

| 類別 | URL／檔名規則 | 被邊個項目引用／研究用途 |
|---|---|---|
| ATP 歷史賽事 | [JeffSackmann/tennis_atp](https://github.com/JeffSackmann/tennis_atp)；`atp_matches_{YYYY}.csv`、`atp_matches_qual_chall_{YYYY}.csv` | P01／P03；賽果、排名、serve box scores，分清 main tour／qualifying／Challenger |
| WTA 歷史賽事 | [JeffSackmann/tennis_wta](https://github.com/JeffSackmann/tennis_wta)；`wta_matches_{YYYY}.csv`、`wta_matches_qual_itf_{YYYY}.csv` | P01／P03；WTA main tour／qualifying／ITF，唔同完整度唔混為一談 |
| Sackmann 歷史鏡像 | [Aneeshers/tennis-sackmann-archive](https://github.com/Aneeshers/tennis-sackmann-archive) | P01 ETL 指明嘅 June 2026 archive fallback；須檢查 snapshot 日期及原始 hash，唔當最新資料 |
| 歷史莊家價格 | [Tennis-Data](http://www.tennis-data.co.uk/)；ATP `http://www.tennis-data.co.uk/{YYYY}/{YYYY}.xlsx`，WTA `http://www.tennis-data.co.uk/{YYYY}w/{YYYY}.xlsx` | P01／P02／P03；逐欄保留 book、opening／closing 語義及時間證據。MaxW／MaxL 跨 book 最高價唔等於單一可執行報價 |
| 發接球 charted 子集 | [Match Charting Project](https://github.com/JeffSackmann/tennis_MatchChartingProject)；[原始 CSV 入口](https://raw.githubusercontent.com/JeffSackmann/tennis_MatchChartingProject/master/charting-m-matches.csv) | P02；ATP `charting-m-matches.csv`／`charting-m-stats-Overview.csv`，WTA 對應 `charting-w-*`；需身份／時間／coverage／選樣偏差核對 |
| 即時莊家 API 候選 | [The Odds API](https://the-odds-api.com/)；API base `https://api.the-odds-api.com/v4` | P01；只登記參考，未訂閱、未新增 live provider，研究及費用另評估 |

來源程式：[P01 etl_sackmann.py](https://github.com/theayobamiakin/tennis-analytics-prediction/blob/main/src/etl_sackmann.py) blob `aa398e58673bf4cea43aff9f17fb0c02bc8f6a5f`；
[P01 odds_pipeline.py](https://github.com/theayobamiakin/tennis-analytics-prediction/blob/main/src/odds_pipeline.py) blob `063ede934409ac175b37b62b4aa6ceb43136a5a4`；
P02 config 及 P03 data module 版本見各項目章節。

正式實驗開始前：保存外部 commit SHA、精確下載 URL／檔名、擷取 UTC、資料涵蓋期、來源授權、local path、row counts 及 SHA256；大型語料按 repo 外置碟規則處理。
將來失效／轉 private 嘅入口要明示 missing，唔靜靜縮細 corpus 或換來源救結果。

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

## P03：coenensam/tennis-match-predictor

### 可核對來源及檢視範圍

- [README](https://github.com/coenensam/tennis-match-predictor/blob/main/README.md)，blob `135c12fb34845b0bd7008ce5ceca9b00c47938e2`。
- [config.py](https://github.com/coenensam/tennis-match-predictor/blob/main/src/tennis_predictor/config.py)，blob `0fc2bb63d367d1367bc3153f2add28ceae569619`。
- [data.py](https://github.com/coenensam/tennis-match-predictor/blob/main/src/tennis_predictor/data.py)，blob `766a05d086b00779471cb7921f3ce05273006cb5`。
- [elo.py](https://github.com/coenensam/tennis-match-predictor/blob/main/src/tennis_predictor/elo.py)，blob `6d4c5c6f925078d9bca91d8d977bdda5ffc45cbe`。
- [features.py](https://github.com/coenensam/tennis-match-predictor/blob/main/src/tennis_predictor/features.py)，blob `2cc5ac3f5631c8abd3ce68b07dbd84c370d98ff4`。
- [model.py](https://github.com/coenensam/tennis-match-predictor/blob/main/src/tennis_predictor/model.py)，blob `5f7c6ec8d93626bfd63d95eb3c6c6d6bc13ca845`。
- [clv.py](https://github.com/coenensam/tennis-match-predictor/blob/main/src/tennis_predictor/clv.py)，blob `06d670d27894c756b5ef462420e536ba2a1d0ae3`。
- [predict.py](https://github.com/coenensam/tennis-match-predictor/blob/main/src/tennis_predictor/predict.py)，blob `e20991c11dffbb4d251ad84e8901203e92cf8b75`。
- [pipeline.py](https://github.com/coenensam/tennis-match-predictor/blob/main/src/tennis_predictor/pipeline.py)，blob `6ab9c1dcfe6388b82a1c2c11234a6432a9696284`。
- [tests/test_devig.py](https://github.com/coenensam/tennis-match-predictor/blob/main/tests/test_devig.py)，blob `4115981ebfc295f7a0bf33b53bdebd0d5b13cb63`。
- 網址及上游 raw data 入口均保存；未下載 801k corpus，未執行作者模型／測試，未獨立重現 README 數字。

### 作者公開結果及正確比較群體

README 自報 2000–2026 約 801k ATP/WTA 賽事，時間切分後約 132k 測試；原 Elo LL 0.5979、XGBoost LL 0.5825。
呢個大群體包含 lower tiers，不能同另一個 2,409 場 tour odds-linked 群體直接互相比數字。

| 同 2,409 場 tour-level odds-linked 群體（作者 README） | Log loss |
|---|---:|
| Pinnacle 去水市場 | 0.5980 |
| Betfair Exchange（README 列出） | 0.5901 |
| XGBoost | 0.6145 |
| 原 Elo | 0.6271 |

作者模型較 Elo 好，但仍落後市場。README 報 encompassing `b_close=1.128`／`b_model=−0.141`；本次冇取得該擬合嘅 row-level 證據或係數 CI。
目前 `clv.py` headline 報 Pinnacle proportional／Shin、XGB、Elo，冇輸出 Betfair 列；README 嘅 exchange 數字不可當現行 module 已驗證重現。

### 值得借鏡，同既有候選去重

1. **學習特徵之間嘅非線性關係**：XGBoost 同時讀 Elo、排名、近期勝率、rest、H2H、serve／return、ace、break-save、對手排名等 18 欄。
   呢個有別於我哋現役 Elo + 手定 nudges；可與同特徵簡單 logistic／ridge 做公平比較，唔因係 boosting 就當更準。
   我哋 `fit_hold_ml.py` 曾量 boosted hold regressor，但目標係保發率；唔代表已做相同嘅勝負分類實驗。
2. **對手賽程強度**：最近 20 場對手排名平均，再計雙方差；作為對手品質摘要，可同既有 opponent buckets／Elo 控制獨立量。
   Rank 平均受極端排名、缺值及跨 tier 影響，必須看額外貢獻，而唔係只看 feature importance。
3. **市場以外資訊診斷**：`outcome ~ market_logit + model_logit` 可補充 paired LL/Brier，問模型有冇條件增量。
   係額外研究診斷，唔取代 frozen ruler；係數正負本身唔足以當證明，應以 match-level uncertainty、穩定性及未用資料驗證。
4. **自適應場地權重**：`0.7 * n_surface/(n_surface+20)`，併入 C03，唔另開重複候選或直接搬 0.7／20。
5. **薄資料旗標**：列出無排名對手往績、無 serve history、少於 10 場等具體原因；併入 C04 資料品質及推論一致性盤點。
   作者薄資料旗標唔可以代替我哋投注 eligibility／證據閘。
6. **長休 rating decay**：我哋 EXP-20261009-01 C3 已 REJECT；只記重疊，不因另一個 repo 有此功能就重試失敗 arm。

### 程式核對見到嘅限制

- `data.load_matches` 用 `tourney_date + round_ord * 1.3 days` 人工估比賽時間，原始排序仍係 `tourney_date/round_ord/match_num`。
  呢個唔係已證實 actual start／result-available time；會影響 rest、排序同 train/test 邊界。先記洩漏風險，未量實際污染場數。
- `predict.predict` 將 `rank_diff` 固定填 0，而訓練用實際雙方排名差；存在明確 train/inference 輸入差異。
  其他欄位兩邊亦分開手寫，不能單憑 docstring 話「exactly same」就接受 parity。
- `pipeline` bundle 保存整份資料 replay 後嘅最後 Elo／hist；`predict(match_date=...)` 只改計 rest／decay，唔重建該日之前 state。
  所以不能攞此入口回到歷史日做 PIT 回測；向前預測亦要保存 state 的 trained-through／observed-through cutoff。
- 只 randomise A/B 方向，未強制兩次交換調用嘅 `P(A,B)+P(B,A)=1`；tree model 需另做 player-swap 測試／設計。
- `score_clean` 只供可選 margin 更新使用；WO／RET rows 仍會更新 Elo、form 及進入分類 label。需按研究目標及投注結算合約另定 eligibility，唔混用未完賽結果。
- `_join_odds_to_preds` 只用無序姓名 pair + 最近日期（容忍 16 日），冇強制 tour／surface／event／round 一致；重賽、同名及多來源配對要審計。
- 名叫 CLV 嘅 module 實際係對 close 做勝負評分及假設 ROI，冇 entry-price／entry-time 配對；不能當已量到真正 closing-line value。
- ROI 用 Pinnacle 價判 edge，卻用 `MaxW/MaxL` 跨 book 最高價結算；可以標明做歷史研究，但唔係固定 Sportsbet 策略或可執行收益。
  多 threshold t-stat 冇提供 paired／cluster bootstrap 或多重比較控制，唔直接搬作成功閘。
- Encompassing regression 把兩邊鏡像當兩行 fit，冇係數 CI；負 `b_model` 亦唔係「無任何額外資訊」嘅充分證明，可能受共線／校準／反向訊號影響。
- `train` 係單次 chronological 80/20，test 作 `eval_set`；現有 default 無 early stopping，不能因此直接稱訓練洩漏，但亦未見獨立 dev／calibration／多 fold 穩定性證據。
- 已讀 tests 只涵蓋去水及兩組姓名 key，不足以證明時間安全、完整 odds linkage、inference parity 或盈利顯著性。

### 本次結論

保留非線性勝負 head、對手賽程強度、以及市場條件增量診斷；場地 shrink／資料品質歸併，長休 decay 保留舊 REJECT。
模型輸市場同工程限制一併記錄。沒有新實驗、模型改動或表現改善宣稱。

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
| C03 | 場地樣本量驅動嘅 Elo 收縮 | P01／P03 | 同固定混合基準比較，須可靠場地及歷史樣本數；唔改已 frozen shadow | 待整合，未開實驗 |
| C04 | 訓練／預測一致性及資料來源時間檢查 | P01／P02／P03 | 核對日期、當時已知資料、報價、rank／serve 缺值、薄資料原因及 A/B 交換；先盤點現有修正 | 待整合，未開實作 |
| C05 | 發接球／局數／排名候選歸併 | P01／P02 + EXP07/08/09 | 只記低重疊；新假設須解釋同失敗設計嘅實質分別，保留舊 REJECT | 去重清單，唔重跑舊候選 |
| C06 | Serve profiles 時間衰減、按 points 曝光量加權及收縮 | P02 | 分開比較 recency／exposure／prior，每項及組合消融；與 EXP09 保持可辨識差異 | 待整合，未開實驗 |
| C07 | MCP serve／return 資料可用性盤點 | P02 | 先量授權、日期、身份、覆蓋及選樣偏差；canonical match 去重，再考慮新 source A/B | 待整合，未抽資料 |
| C08 | 精確 DP 取代或核對 Monte Carlo | P02 | 先做小範圍 kernel parity，正確 server／tie-break state；量速度、數值誤差，模型精度獨立量 | 待整合，未開實驗 |
| C09 | Match-winner 與 props 聯合一致性／anchor | P02 | 不只配勝率；驗證總局、set score、handicap，避免單一目標過度約束；先查已有設計 | 待整合，未開實驗 |
| C10 | 多 book 訓練資料及 ROI 診斷規格 | 用戶補充 | 保留來源、價格時間與市場合約；dev-only ROI，不挑最好 book，Sportsbet forward 另驗 | 已確認允許，待實驗規劃 |
| C11 | 非線性 match-winner head（XGBoost 等）對照簡單 logistic | P03 | 先鎖相同賽前特徵／cohort；分離新特徵同 head 增量；time folds、缺值及 inference parity 要完整 | 待整合，未開實驗 |
| C12 | 最近對手賽程強度摘要 | P03 | 與 Elo／排名／opponent buckets 控制比較；缺值及跨 tier 分層，獨立及組合消融 | 待整合，未開實驗 |
| C13 | 市場條件增量／encompassing 診斷 | P03 | 同場 market＋model，match-level CI／穩定性驗證；不以係數符號取代 paired LL／Brier 或 frozen gate | 待整合，未實作診斷 |

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
