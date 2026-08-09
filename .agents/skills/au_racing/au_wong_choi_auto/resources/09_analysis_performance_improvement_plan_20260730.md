# AU Wong Choi Analysis Performance Improvement Plan — 2026-07-30

## 目標同不可退讓條件

目標係提高 AU Wong Choi 對真正爭勝馬嘅排序能力，同時令資料層同 scoring
更簡單、可追蹤、容易除錯。今輪唔以增加規則數量做「改善」，亦唔會因單一
archive window 數字好睇就升 production。

固定 baseline（710 場、7,530 匹已對齊馬匹）：

| 指標 | Current |
|---|---:|
| Gold | 40 / 710（5.63%） |
| Good positional | 136 / 710（19.15%） |
| Pass any-one | 623 / 710（87.75%） |
| 0-hit | 87 / 710（12.25%） |
| Top-3 capture@4 | 55.55% |
| Top-3 capture@5 | 65.74% |
| Winner@3 / Winner@5 | 52.25% / 71.97% |
| Competitive recall@5 | 63.81% |
| NDCG@5 | 52.73% |
| Top-5 false contender | 38.11% |

語義固定：

- `Gold`：model Top 3 全部跑入 actual Top 3。
- `Good positional`：model Rank 1 同 Rank 2 都跑入 actual Top 3。
- `Pass any-one`：model Top 3 至少一匹跑入 actual Top 3。
- 新增 promotion gate：actual Top 3 全部落入 model Top 4，並以 dead-heat-safe
  方法計算。

任何 production 候選都必須同時守住 Good、Top3-in-Top4、competitive
recall@5、NDCG@5、winner@5，同時 0-hit 不得上升。市場 SP、結果或任何
post-race 欄位只可用作 outcome label／cohort review，唔可進入 pre-race
feature。

## 第一輪發現

### 1. Sectional 資料喺 extractor 中途流失

Racenet archived payload 嘅 `competitorFormBenchmark` 本身包含：

- overall `runnerTimeDifference`
- `runnerTimeDifferenceL800/L600/L400/L200`
- `runnerTempoQuantileRank`
- runner / leader tempo label
- L800/L600/L400/L200 position

舊 active extractor 只將 overall race time、pace label、L600 delta 同 RT
傳入 Formguide；L800、L400、L200 同 tempo quantile 中途被丟棄。canonical
engine 其實已識解析完整 split token，因此問題係 transport gap，唔係需要
再造一套 parser。

本地 `scratch/pf_backfill_staging` 26 個 historical patch 覆蓋 246 場、
2,673 匹 PF 馬：

| 欄位 | 有值 |
|---|---:|
| Race time | 2,673 |
| L800 | 2,668 |
| L600 | 2,673 |
| L400 | 2,673 |
| L800 + L600 + L400 complete | 2,668（99.8%） |

即係一旦 PF source 存在，較完整分段 profile 有足夠 coverage；真正瓶頸係
歷史 meeting 有冇被 backfill，而唔係欄位本身稀疏。

### 2. 重複 parser 增加維護風險

`build_au_logic.py` 保留咗一套未被呼叫嘅舊 PF／jockey-trainer parser，
實際 build 已全部交畀 `racing_engine.engine_core` canonical parser。保留兩套
會令日後 schema 修正容易只改一邊，所以今輪直接移除 dead duplicate，
canonical engine 成為唯一解析來源。

### 3. 舊資料已接近規則搜尋極限

上一輪對 class、distance、race shape、jockey change、matrix transfer、
large-field consensus 同 pairwise ranker 做過時間 folds + terminal holdout。
部分窗口有改善，但冇候選同時通過所有 corrected gates。下一輪應優先增加
獨立 evidence／修復 missing evidence，而唔係繼續喺同一 710 場調 threshold。

## 外部資料與研究矩陣

| 來源 | 可用資料／結論 | 適合用途 | 風險／限制 |
|---|---|---|---|
| [Racing NSW Punter's Intelligence](https://www.racingnsw.com.au/punters-intelligence/) | 官方說明 saddle-cloth transmitters 每秒收集 50 次；提供 race time、sectionals、distance travelled、top speed、position | NSW measured sectionals、走位、額外路程；驗證 Racenet derived data | 要逐項確認歷史/API 可得性及使用條款；唔可假設可批量再發布 |
| [Racing Victoria sectional rollout](https://www.racing.com/news/2017/10/11/track-talk-wednesday) | Victorian TAB meetings 提供 200m splits、cumulative sectionals、position-in-running | Victoria forward data、跨來源核對 | Racing.com page／feed 結構可能改變；先做 read-only source adapter |
| [Racing Australia official trial fields](https://www.racingaustralia.horse/FreeFields/Nominations.aspx?Key=2026May05%2CNSW%2CTaree%2CTrial) | 官方 trial nomination／field 頁 | prep recency、trial count、trial spacing | 頁面有 copyright；只保存必要 derived facts，先確認 point-in-time timestamp |
| [Animals 2026 Australian race-speed study](https://doi.org/10.3390/ani16101433) | 200,601 starts；final-600 speed 同 distance、track condition、rating、weight 有關 | 支持 condition-normalized sectional，而唔係直接用 raw time | 研究結論係 feature design 依據，唔代表某個權重已被證實 |
| [Equine Vet J statistical model](https://pubmed.ncbi.nlm.nih.gov/8944806/) | Distance、track、surface、field size、weight、barrier 影響 finish time | 設計 benchmark normalization covariates | 年代較早，只用作結構性依據 |
| [Pacing strategy study](https://pmc.ncbi.nlm.nih.gov/articles/PMC3391435/) | 44,803 starts；pacing strategy 同 drafting 對表現／結果有實質影響 | 支持 early-vs-late efficiency、race-shape interaction hypothesis | 唔可直接將研究 sample coefficient搬入 AU production |
| [Training speed / recovery study](https://doi.org/10.3390/ani14091342) | Training speed、heart-rate recovery有預測價值，但個體差異大 | 長期可研究 training／trial workload | 現時公開 racecard coverage不足，屬較後優先 |

來源使用規則：

1. 優先官方、免費、point-in-time 可重現資料。
2. 保存 source、retrieved-at、event date 同欄位 coverage。
3. 唔以 race result 反向補 pre-race feature。
4. 未確認授權前，只做 derived facts／internal research，唔鏡像整個第三方資料庫。

## 優先次序

### P0 — 完整 PF transport 同 provenance（已開始實作）

範圍：

- extractor 保留 L800/L600/L400/L200 delta 同 tempo quantile；
- canonical parser 記錄 source 同每個欄位 value count；
- meeting field summary 顯示各 split coverage／mean／stdev；
- scoring 權重完全不變。

成功標準：

- 有值就 round-trip 保留；
- missing 欄位唔 fabricated；
- 舊 L600 consumers 兼容；
- full AU test suite 通過。

### P1 — Standardized sectional / pace-efficiency shadow

先建立可解釋、無 outcome input 嘅 diagnostics：

- overall benchmark delta；
- early-to-late profile（L800 → L600 → L400 → L200）；
- tempo quantile；
- distance、track condition、field size、weight normalization context；
- observation count、recentness 同 source reliability。

第一版只輸出 shadow CSV／audit JSON，唔進入 production total score。要有新增
forward meetings，先用相同時間 folds 同 terminal gate 評估：

- complete-profile cohort；
- 13+ runners 大場；
- 0-hit／1-hit races；
- false contenders；
- extreme outsider outcome cohort。

### P2 — Prep workload / trials

建立 point-in-time trial ledger：最近 30/60/90 日 trial 次數、距離、場地、
trial-to-race gap、是否正式賽前首次／二次 trial。先測 missing-evidence recall，
避免單純將 trial placing 當能力分。

### P3 — Leakage-safe rolling jockey / trainer

按每場開跑時間做 expanding history，禁止 season-end aggregate 倒灌；至少設
minimum sample、shrinkage 同 source timestamp。現有靜態 ratings 可作 baseline，
新 rolling feature 先 shadow。

### P4 — Interaction-based race shape

只喺 P1 coverage穩定後重開：expected pace × settled pattern × sectional
efficiency × field size。採少量預先註冊 interaction，唔做數百個 threshold
搜尋。

### P5 — Formline rebuild

以共同對手、race strength、subsequent performance 做 point-in-time graph。
呢項工程量最大，而且最容易 outcome leakage，所以排喺完整 provenance、
timestamp 同 rolling evaluation 之後。

## 實驗合約

每個候選必須：

1. 由 raw Logic/current engine 重跑，唔只比較舊 CSV snapshot。
2. development 用時間順序 folds；只准 folds 1–4 選參數。
3. fold 5 同 terminal 15% holdout只作一次 confirmation。
4. 報完整 baseline、coverage、missing cohort，同唔同場地／field-size結果。
5. 同時通過：
   - Good positional 不跌；
   - exact actual Top3-in-model-Top4 不跌；
   - competitive recall@5、NDCG@5、winner@5 不跌；
   - 0-hit 不升。
6. 至少一個主要目標有實質改善，而唔係全部只係 rounding noise。
7. 單一場地、單一月份、細 cohort 或單一 seed 改善，只保留 shadow。

## 當前實作狀態

已完成第一個安全 milestone：

- active extractor 傳送完整 benchmark split profile；
- canonical parser 加 source/value-count provenance；
- field summary 加完整 split coverage diagnostics；
- 移除 `build_au_logic.py` dead duplicate PF/JT parser；
- production feature scores、matrix weights、ranking 同 grade contract冇改。

下一個 promotion decision 唔會基於現有 710 場再調參；會先建立 P1 shadow
dataset，再累積新增前瞻 meeting window。若 corrected gate 未過，資料仍保留
作 diagnostics，但唔會升 production。
