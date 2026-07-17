# HKJC Dimension重建 Step 1 — 來源契約與污染盤點

## 方法

- 使用既有strict manifest相同245場；賽果只用嚟鎖定完成馬population，完全無參與本步公式或閾值判斷。
- 公開12-feature schema保持不變；盤點另包括5項derived signal及7個matrix dimension。
- going、draw、賠率、市場、pace及micro tie-break列為重建排除輸入。

## Coverage

- 25個賽日／245場／3054匹完成馬；初出馬99匹。
- Dataset horse rows：{'archive': 1580, 'independent_recent': 1367, 'external_2026_07_15': 107}。
- 資料錯誤：0。

## 現行dimension來源契約

| Dimension | 現行公式 | Mapping後調整 | 污染／重疊 | Step 3方向 |
|---|---|---|---|---|
| stability | form_score 50% + consistency_score 40% + trackwork_trend_score 10% | feature context may replace consistency_score before mapping | form與consistency同樣大量源自近期賽績，可能重複計分 | REBUILD_DISTINCT |
| sectional | speed_score 65% + track_going_score 35% | finish-time trend nudge after matrix mapping | track_going_score屬已排除going；同時有post-matrix時間修正 | REBUILD_SPEED_ONLY_WITH_RELIABILITY |
| race_shape | race_shape_context_score 100% | Sha Tin: draw 55% + draw-position fit 25% + trip consumption 20%; other venue: draw + context delta | draw係主要基底，屬重建排除項；位置訊號亦同draw文字混合 | REPLACE_WITH_DRAW_FREE_CONTEXT |
| trainer_signal | jockey_score 55% + trainer_score 45% | trainer-signal V3 priors after matrix mapping | prior樣本量未直接成為統一可靠度收縮 | KEEP_CORE_ADD_RELIABILITY |
| horse_health | risk_score 55% + weight_score 35% + confidence_score 10% | health-only V2 after matrix mapping | weight同class重複；confidence係資料覆蓋卻被當正向能力分 | REBUILD_READINESS_RISK_ONLY |
| form_line | formline_strength_score 100% | none after mapping | 離散bucket且對手後續樣本量未做統一收縮；margin trend已排除避免同stability重複 | KEEP_MEANING_ADD_RELIABILITY |
| class_advantage | class_score 75% + weight_score 25% | none after mapping | weight同horse_health重複；distance_score及same-distance signal仍在矩陣外 | REBUILD_CLASS_WEIGHT_AND_SEPARATE_DISTANCE |

## 全體中性60與分布

| Signal | Mean | SD | 中性60 | Min–Max |
|---|---:|---:|---:|---:|
| form_score | 55.13 | 13.01 | 7.8% | 40.0–100.0 |
| speed_score | 61.25 | 7.87 | 30.5% | 38.6–84.6 |
| class_score | 65.48 | 7.22 | 9.7% | 52.5–77.5 |
| jockey_score | 69.91 | 9.92 | 10.5% | 49.9–94.2 |
| trainer_score | 69.66 | 8.24 | 16.1% | 56.4–87.0 |
| draw_score | 63.88 | 8.29 | 0.0% | 49.1–77.5 |
| distance_score | 63.60 | 6.75 | 24.3% | 54.0–72.0 |
| track_going_score | 60.18 | 1.49 | 87.2% | 58.0–66.0 |
| weight_score | 63.61 | 5.43 | 4.3% | 50.0–74.0 |
| consistency_score | 58.36 | 12.04 | 6.8% | 27.0–100.0 |
| risk_score | 68.23 | 4.46 | 1.1% | 50.0–76.5 |
| confidence_score | 77.19 | 8.98 | 0.1% | 46.2–83.0 |
| formline_strength_score | 76.29 | 12.89 | 28.1% | 58.0–96.0 |
| margin_trend_score | 60.39 | 7.84 | 68.7% | 48.0–76.0 |
| same_distance_signal_score | 61.76 | 6.97 | 35.3% | 54.0–72.0 |
| trackwork_trend_score | 61.35 | 7.60 | 46.8% | 48.1–76.8 |
| race_shape_context_score | 63.50 | 7.88 | 0.1% | 39.1–82.0 |
| matrix_stability | 57.13 | 10.69 | 3.8% | 35.9–96.0 |
| matrix_sectional | 60.43 | 6.20 | 29.7% | 33.6–81.5 |
| matrix_race_shape | 63.50 | 7.88 | 0.1% | 39.1–82.0 |
| matrix_trainer_signal | 69.79 | 7.73 | 4.1% | 51.9–89.5 |
| matrix_horse_health | 67.38 | 3.61 | 0.0% | 55.7–74.9 |
| matrix_form_line | 75.63 | 9.01 | 10.3% | 58.6–96.0 |
| matrix_class_advantage | 65.01 | 5.43 | 0.2% | 52.8–76.6 |

## Dataset版本漂移警報

| Signal | Archive中性60 | 近期獨立中性60 | 07-15中性60 |
|---|---:|---:|---:|
| speed_score | 55.4% | 4.0% | 0.9% |
| distance_score | 31.1% | 16.8% | 19.6% |
| track_going_score | 86.6% | 86.8% | 100.0% |
| confidence_score | 0.2% | 0.0% | 0.0% |
| formline_strength_score | 7.8% | 52.2% | 19.6% |
| race_shape_context_score | 0.0% | 0.1% | 0.9% |

## 高重疊訊號

以下列出絕對相關最高15組；相關只係重疊警報，唔等同因果或自動刪除。

| Signal A | Signal B | Correlation |
|---|---|---:|
| draw_score | race_shape_context_score | +0.956 |
| form_score | consistency_score | +0.766 |
| risk_score | confidence_score | +0.584 |
| class_score | same_distance_signal_score | +0.558 |
| class_score | distance_score | +0.533 |
| form_score | class_score | +0.524 |
| speed_score | consistency_score | +0.501 |
| distance_score | same_distance_signal_score | +0.500 |
| class_score | consistency_score | +0.460 |
| form_score | speed_score | +0.410 |
| jockey_score | trainer_score | +0.391 |
| class_score | confidence_score | +0.373 |
| form_score | same_distance_signal_score | +0.364 |
| consistency_score | same_distance_signal_score | +0.355 |
| speed_score | margin_trend_score | +0.350 |

## Step 1判斷

- 必須移除：sectional內track-going；race-shape內draw基底。
- 必須拆重：weight不可同時在horse-health及class重複當能力；confidence只可控制可靠度，唔應作正向能力edge。
- 必須補可靠度：speed、distance、form-line、騎練及冷門馬上限需由evidence count向中性60收縮。
- 必須統一replay：speed中性率由archive 55.4%跌至近期4.0%，form-line則由7.8%升至52.2%，證明現存跨時段分數混有engine版本漂移；Step 2要用同一版賽前資料重算先可公平驗證新dimension。
- 可保留語義但重算：stability、trainer signal、form-line、class/weight；distance維持獨立context，避免偷塞入form-line。
- 本步只完成來源契約，尚未定義新公式、跑賽果性能或改正式Auto engine。
