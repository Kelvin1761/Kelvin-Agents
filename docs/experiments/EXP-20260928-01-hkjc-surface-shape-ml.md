# EXP-20260928-01 — HKJC 個別場地性能與 Race Shape ML 診斷

- 日期：2026-09-28；平台：HKJC。
- 狀態：**RESEARCH PASS / PRODUCTION HOLD**。證據支持重建方向，但沒有改 live formula、commit、push 或 deploy。
- 搜索過：EXP-20260902-03/08/10、EXP-20260904-05/07/08、EXP-20260910-01、EXP-20260927-04。
- Harness：`docs/experiments/patches/hkjc_surface_shape_ml.py`。

## 問題

1. 個別馬匹嘅沙田草地／跑馬地草地／沙田泥地表現可否成為正式訊號？
2. 「同場同程」直接 bonus 點解會跌？
3. 最高外權 27.37% 嘅 race-shape 應否重建？
4. 沙田同跑馬地應否拆成兩套完整公式？
5. ML test 有冇必要，以及佢應該扮演咩角色？

## 資料與時間安全

- 重建 archive：31 meeting、309 race、3,833 horse-row，2026-04-12 至 2026-09-23。
- 場地：沙田草地 186 場、跑馬地 115 場、沙田泥地 8 場。
- Expanding walk-forward：頭 12 meeting／最少 110 race 訓練，之後逐 meeting 評估；out-of-sample 189 場、19 folds。
- pairwise logistic 固定 `C=0.10`；每場內標準化。ML 只作訊號診斷，不直接生成 production formula。
- 個別場地性能只讀同一 horse ID、嚴格 `history_date < target_date`、目標路程 ±200m、最多 730 日、365 日半衰期。結果轉成 field-size normalized finish percentile，再用 4 個有效樣本向 0.5 收縮。
- 不用賠率、當場賽果、事後 incident、預測跑法或未來資料。
- 最初 metadata audit 發現 HKJC 結果用「全天候跑道」而非「泥地」；修正 surface normalizer 後重跑。初次結果作廢，以下全是修正後 final run。

呢輪係探索性 ML 診斷，唔係 untouched holdout。多個 feature family 已被比較，所以任何最好結果只可用來凍結下一輪候選，唔可直接宣稱 promotion。

## Coverage

| 訊號 | 非零／有歷史 coverage |
|---|---:|
| 目標場地、相近路程歷史表現 | **88.05%** |
| 同一匹馬同時有目標＋其他場地歷史 | 61.52% |
| 現有 Facts「同場同程」有出賽 | **16.54%** |

個別場地性能可以正式建，但資料來源應係完整 PIT result history，而唔係低覆蓋嘅一行「同場同程」。

## Race-shape component 結果

以下係加入相同 base-6 matrix 後嘅 walk-forward ML 係數；每項先場內標準化，所以只比較符號與相對穩定性，不可直接抄成 production 百分比。

| Component | 中位係數 | 正係數 folds | 判讀 |
|---|---:|---:|---|
| draw | +0.225 | 19/19 | 穩定有效，保留 |
| historical fit / PI mix | +0.004 | 11/19 | 幾乎零、符號不穩 |
| raw trip consumption | **−0.072** | **1/19** | 現行正向邏輯高度可疑 |

獨立 paired ablation：

- draw 相對 base-6：Champion +5.29pp，95% CI [+1.06,+10.05]；NDCG@5 +2.74pp [+0.67,+4.79]，但 Gold −2.12pp、CI 跨零。
- fit 加喺 draw 後：Gold/Champion 0、Good +0.53pp、NDCG +0.10pp，全部 CI 跨零。
- trip 加喺 draw 後：Gold +2.12pp，但 Good −0.53pp、NDCG近零，全部 CI 跨零。ML 要靠負係數先使用佢，唔支持現行固定「低消耗加、高消耗扣」。

結論：**race-shape 應重建，但唔係成個刪走。** 保留 draw；fit 降為低影響／shadow；舊 trip 退出正向能力分，另行重建「闊疊仍跑近」等 qualified evidence。呢個同舊實驗 trip AUC 0.47–0.49、race-shape 外權多次 fit 到 0.17–0.23 而非 0.2737 一致。

官方全 7D fitter 亦用更新後 32 meeting／320 race 重跑；為免每個細 slice fit 耗時失控，只跑 global expanding walk-forward（24 folds／240 OOS races）。結果再次指向：

- full-sample learned `race_shape = 0.2003`；
- walk-forward 平均 `race_shape = 0.2173`；
- 現役係 `0.2737`。

但 ML full-sample 排名嘅 Gold/Good 係 11/61，低過 current live 15/74，所以**唔抄 ML 權重上線**。佢只係第四個獨立證據話 race-shape 過重，而唔係一套已過閘 replacement。

## 個別場地性能

`surface_quality`（目標場地＋相近路程嘅 PIT 歷史表現）喺 19/19 folds 係正係數，中位 +0.262。相對同一 base-6：

| 指標 | Δ | 95% paired CI |
|---|---:|---:|
| Gold | −1.06pp | [−4.76,+2.12] |
| Good | **+4.23pp** | **[0.00,+8.47]** |
| Champion | −0.53pp | [−4.23,+3.17] |
| NDCG@5 | +1.87pp | [約0.00,+3.81] |

單純 `surface_specialism = 本場地 − 其他場地` 邊際弱；加入 surface quality 後更因共線而轉負。即係現階段支持「喺目標表面實際跑成點」，未支持「一定偏愛某表面」呢個較強敘述。

探索性 full candidate（base-6 + draw + fit + trip + surface quality + specialism）相對 current live：Gold 0.00pp、Good 0.00pp、Champion −1.06pp [−6.88,+4.76]、NDCG@5 **+4.27pp [+1.63,+7.10]**。呢個係值得凍結下一輪 deterministic shadow 嘅訊號，但 primary 無提升、且候選經過探索，**不足以換 live**。

## 點解「同場同程」直接加分會跌

`same_venue_distance_eb` 只有 16.54% coverage；係數中位 −0.013，只有 3/19 folds 為正。相對 base-6：Gold +1.06pp [0,+2.65]，但 Good −0.53pp [−1.59,0]、Champion −0.53pp [−1.59,0]、NDCG近零。

原因唔係「同場同程完全冇用」，而係原始 bonus 同時有四個問題：

1. coverage 太低，少數有紀錄馬先獲得額外幅度；
2. raw place-rate 混合馬匹本身能力、班次、field size、年代與場地；
3. 同現有 stability／form／distance evidence 重複計分；
4. 「相同場地＋相同路程」過窄，無法使用大量相近路程而同表面嘅有效歷史。

因此保留 **REJECT direct bonus**；下一輪用高覆蓋、recency + field-size normalized、向中性收縮嘅 surface quality。

## 沙田／跑馬地是否拆完整公式

同一組特徵比較 pooled vs 每場地獨立 fit（181 場 turf OOS）：

| 模型 | Gold | Good | Champion | NDCG@5 |
|---|---:|---:|---:|---:|
| pooled | 13.26% | 19.89% | 25.41% | 59.89% |
| ST/HV separate | 12.71% | 18.78% | 24.86% | 59.39% |
| separate − pooled | −0.55pp | −1.10pp | −0.55pp | −0.50pp |

四項 95% CI 均跨零，但點估計全部較差。**不拆完整 7D。** 共用骨架，保留 venue/surface-specific feature 同 cohort guardrail。AWT 只有 8 場，完全不足獨立 formula。

## 決定與下一步

1. **REBUILD DIRECTION PASS**：race-shape v2 應保留 draw，移除舊 trip 嘅固定正向解讀，fit 降權，加入獨立 PIT surface-quality shadow。
2. **SURFACE FEATURE PASS TO SHADOW**：可以修復「每匹馬場地性能冇入 7D」，但先作 shadow，凍結 deterministic mapping 後再跑同一判決合約。
3. **REJECT**：「同場同程」直接 bonus。
4. **NO FULL SPLIT**：沙田／跑馬地暫不拆完整公式。
5. **ML YES, NOT ML-ONLY**：ML 用來識別穩定方向／交互；正式上線仍需 deterministic ablation、paired bootstrap、venue cohorts、golden/data-contract 同 prospective confirmation。

## 已落地但不入分嘅資料管線

- `inject_hkjc_fact_anchors.py` 新增嚴格 PIT surface-performance shadow：沙田草地／跑馬地草地／沙田 AWT 分開，field-size normalized、相近路程 ±200m、365 日半衰、4 場中性收縮。
- Facts 明確印 `個別場地性能 (Shadow)` 同「暫不入分」。
- `create_hkjc_logic_skeleton.py` 將原始 shadow evidence 鎖入 horse top-level 同 `_data`，下一輪可直接做 deterministic A/B，唔使重新爬數據。
- 測試覆蓋 AWT 正規化、嚴格日期 cutoff、路程匹配、無資料中性、Facts→Logic round-trip；6 focused tests passed。
- `./檢查.sh --quick` 通過；完整 `WC_HKJC_SCHED_LOG_DIR=/tmp/hkjc-daily-test-logs ./檢查.sh` 所有 suite 通過。第一次無指定 test log dir 嘅 full run 只因 sandbox 無權寫 scheduler log 而令 HKJC daily-auto 12 tests 失敗；同一 code 用可寫 log dir 重跑 66/66 通過。

## Reproduction

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  .agents/skills/hkjc_racing/hkjc_reflector/scripts/build_hkjc_ranking_dataset.py \
  --output /tmp/hkjc_ranking_dataset_20260928.csv \
  --summary-output /tmp/hkjc_ranking_dataset_20260928_summary.json

PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 \
  docs/experiments/patches/hkjc_surface_shape_ml.py \
  --dataset /tmp/hkjc_ranking_dataset_20260928.csv \
  --output /tmp/hkjc_surface_shape_ml_20260928.json
```
