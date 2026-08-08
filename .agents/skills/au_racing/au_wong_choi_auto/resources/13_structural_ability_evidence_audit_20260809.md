# AU structural ability evidence audit — 2026-08-09

> **後續基準修正：** Formguide digest identity refresh 發現舊 Logic 保留跨馬錯配資料；
> 修復後 Gold 維持 16.15%，Good 24.35% → 24.84%，Pass 45.71% → 45.84%，
> Top-5 AUC 0.6842 → 0.6864。詳見 `14_formguide_identity_and_matrix_followup_20260809.md`。

## Decision

現役 matrix v2 維持不變。今輪只研究馬匹能力 evidence，同時明確禁止 Top-2 lock、
slot 3/4 rerank、賠率同任何 post-race feature。所有候選都要對 805 場 current-runtime
corpus 做完整賽日切分、development time folds、latest-date holdout 同 paired AUC 驗證。

冇候選同時證明能改善未見樣本並守住 Gold／Good，因此今輪冇 production scoring 改動。

## Two correctness bugs fixed

### 1. Jockey evidence state drift

現役騎師分已改用 `unified_place_rate`，但 evidence classifier 仍只認舊
`jockey_ly_stats`／`jockey_rating_db`。結果 8,242／8,249 匹實際有 Sportsbet
騎師統計嘅馬被誤標成 fallback。

修正後：

- jockey missing/fallback rate：99.9% → **0.7%**；
- 排名／ability score：完全不變；
- coverage、confidence 同 failure diagnostics 回復真實狀態；
- regression test 鎖住 `unified_place_rate = observed`。

### 2. Research ablation harness used the retired schema

`au_unhealthy_leaf_test.py` 仍讀舊 `features/name/pos/wet` schema，對現役 runtime
snapshot 直接 `KeyError`；holdout 亦按 race index 切，而唔係完整賽日。已改用 canonical
`au_eval.load_races()`／`date_partitions()`，並移除早已退出排名嘅 sectional no-op 實驗。

簡化後只測現役弱 standalone 維度：

| Ablation | Dev Gold | Dev Good | Dev Pass | Holdout Gold |
|---|---:|---:|---:|---:|
| drop track | -0.34pp | -0.67pp | -1.68pp | -1.42pp |
| drop race_shape | +0.17pp | -3.54pp | -1.68pp | 0.00pp |
| drop both | -0.84pp | -2.19pp | -2.19pp | +1.90pp |

即使兩個維度單獨 AUC 接近 0.5，development marginal contribution 仍然存在，尤其
`race_shape` 對 Good 有明顯保護；證據唔支持刪除。

## Raw PF transport for structural research

Runtime audit snapshot 新增保存已經過 pre-race filter 嘅 `pf_aggregates`，唔加入評分，
亦唔複製 `actual_pos`／SP。完整 1,027 Logic rescore 得到 805 場／8,249 匹：

| Pre-race PF field | Coverage |
|---|---:|
| L600 average / best | 94.4% |
| whole-race time average / best | 82.8% |
| L800 average / best | 46.7% |
| L400 / L200 average / best | 46.9% |

## Structural candidates

### Continuous recency-weighted form

將最新四仗正式名次變成連續能力分，再沿用現役 1.0／0.8／0.6／0.4 recency decay：

- feature-alone AUC：all 0.6182、dev 0.6174、holdout 0.6224；
- blend 75% candidate：dev Top-5 AUC +0.0069，但 holdout -0.0007，
  95% CI [-0.0089, +0.0068]；Gold -0.37pp；
- stability 40% old form／20% consistency／40% candidate：dev +0.0037、holdout
  +0.0020，但 CI [-0.0063, +0.0093]；Gold -1.24pp、Good -0.50pp。

結論：訊號本身健康，但同現有 form／consistency 重複，未證明有 incremental value。

### Full-race speed and last-200 speed

「最佳一次」PF 變體全部差過多仗平均，唔應用 peak run 救馬：

| Raw signal | All AUC | Dev | Holdout |
|---|---:|---:|---:|
| L600 average | 0.5855 | 0.5904 | 0.5721 |
| L600 best | 0.5621 | 0.5646 | 0.5553 |
| whole-race time average | **0.5911** | 0.5861 | **0.6166** |
| whole-race time best | 0.5607 | 0.5573 | 0.5781 |
| L200 average | **0.5927** | 0.5927 | 0.5930 |

以相同 60-centred field-relative scale 混入現役 pace leaf：

- 20% whole-race speed：dev +0.0015、holdout +0.0002，95% CI
  [-0.0051, +0.0058]；Gold -0.12pp；
- 20% L200：dev +0.0032、holdout -0.0008，95% CI
  [-0.0022, +0.0006]；Gold -0.50pp。

兩者只保留 shadow，唔入 production。

### Simpler official-rating scale

測試移除現役 top-3 cutoff bonus／race-class temper，改用純 field z-score或 rank
percentile；所有候選至少一個 development time fold 倒退，未開 holdout promotion。

## Why the third placed horse is still missed

805 場入面有 **373 場**屬於「actual Top 3 已有兩匹落入 model Top 4，但漏一匹」。
漏馬排名：第 5 位 108 場、第 6 位 89、第 7 位 60、第 8 位 50，其餘多數更深。

將漏馬同 Top 4 入面最易被取代嘅 false contender 比較，漏馬喺所有現役主要訊號平均
都更低：form -5.31、consistency -6.67、pace -9.02、jockey -3.90、trainer -2.74、
rating -1.52。新 raw signal 亦未能可靠分開：

| Signal | 漏馬比 false contender 高 |
|---|---:|
| rating | 37.0% |
| trainer | 37.8% |
| whole-race speed | 40.4% |
| L200 average | 42.0% |

因此目前瓶頸唔係第 3／4 slot 排法，而係呢批漏馬喺現有 pre-race evidence 上本身未展示
足夠能力優勢。要再提高 Gold，下一個可行方向係新增真正獨立、point-in-time evidence：
完整 running-position-adjusted sectionals、歷史 class-strength normalization、以及可重播嘅
trip／excuse evidence；唔應再喺現有六維做微型 threshold 搜尋。

## Verification

- current baseline identity：Gold 16.15%、Good 24.35%、Pass 45.71%、Top-5 AUC 0.6842；
- AU auto + shared tests：345 passed；
- AU daily workflow：66 passed；
- total：**411 passed**；
- full runtime materialization：1,027 Logic files／805 aligned races 完成。
