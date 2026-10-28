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
| P02 起 | 待用戶提供其他項目 | — | 待比較 |

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
| C01 | Sportsbet 勝負：市場 fixed-logit offset + 網球特徵修正 | P01 | 查舊 residual 實驗；凍結同場現役／市場／候選對照；需要可信 PIT、資料量及新 forward 證據 | 待整合，未開實驗 |
| C02 | Sportsbet 勝負去水方法獨立比較 | P01 | 用同一筆配對最早賽前價，dev 選方法；獨立於 C01，唔同時換模型及市場基準 | 待整合，未開實驗 |
| C03 | 場地樣本量驅動嘅 Elo 收縮 | P01 | 同固定混合基準比較，須可靠場地及歷史樣本數；唔改已 frozen shadow | 待整合，未開實驗 |
| C04 | 訓練／預測一致性及資料來源時間檢查 | P01 | 核對日期、當時已知資料、報價、缺值及球員方向；先盤點現有修正 | 待整合，未開實作 |
| C05 | 發接球／局數／排名候選歸併 | P01 + EXP07/08/09 | 只記低重疊；新假設須解釋同失敗設計嘅實質分別，保留舊 REJECT | 去重清單，唔重跑舊候選 |

## 完成項目比較後嘅統一執行框架

1. 合併相同想法，標示已有工具、缺資料、已否決及真正新假設；先確認工程缺陷係咪仍存在。
2. 以同一份凍結語料、同一可用時間及同一群體量 baseline；市場資料暫按既有偏好只用 Sportsbet。
3. 每個模型假設另寫 `docs/experiments/` 事前登記；沿用 frozen tennis ruler、舊 dev/holdout 規則，唔以已睇過嘅資料冒充全新 holdout。
4. 工程正確性修正同模型候選分開量；多特徵須單項及組合消融，唔靠一個合併結果歸功。
5. 報同場 paired LL／Brier、分層、coverage／缺值，以及可執行價格下嘅 P/L／ROI／CLV；未證實可執行就只報研究診斷。
6. 開發失敗即保留 REJECT，不換窗或挑 subgroup 救結果；過開發閘先凍結候選做新 forward shadow。
7. 正式上線仍需完整 gate；筆記中嘅優先次序或外部正 ROI 都唔代表已批准部署。

## 後續項目記錄格式

每個新項目記：URL／檢視日期／版本、讀過嘅程式、作者結果及限制、同我哋重疊之處、真正新想法、資料與時間風險、候選 ID、實驗依賴。
完成全部比較之前先累積筆記，唔因逐個項目出現新功能就即時改正式模型。
