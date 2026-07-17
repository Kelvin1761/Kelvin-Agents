# HKJC Dimension重建 Step 2 — 統一賽前Primitive Replay層

## Replay邊界

- Archive原始Logic已不存在，因此不能聲稱用現行RacingEngine完整重跑245場。
- 本層採用archive snapshot與近期Logic共同可重建嘅結構化賽前primitive；舊feature／matrix分數不作新dimension輸入。
- 賽果label及原模型rank獨立存放，永不進入primitive白名單。
- 排除going、draw、barrier、track bias、pace、run style、odds、市場、ROI、edge及敘事式hidden-form flags。
- 2024/25 historical priors只保留賽前sample count、win rate、place rate；ROI完全排除。
- 每列保留source mode；JSON另列archive snapshot、Logic direct field、last6／season／trackwork parser及固定prior嘅provenance group。

## Coverage

- 25個賽日／245場／3054匹完成馬。
- Split horse rows：{'archive_development': 1093, 'archive_temporal_holdout': 487, 'independent_recent': 1367, 'external_2026_07_15': 107}。
- Source mode：{'archived_materialized_prerace_snapshot': 1580, 'current_logic_reconstructed_primitives': 1474}。
- Build errors：0；schema errors：0。

## 關鍵primitive可用率

| Primitive | Development | Temporal | 近期獨立 | 07-15 |
|---|---:|---:|---:|---:|
| last6_runs | 100.0% | 100.0% | 100.0% | 100.0% |
| raw_last_margin | 19.6% | 87.7% | 81.4% | 87.9% |
| raw_l400 | 64.7% | 96.3% | 95.8% | 99.1% |
| raw_finish_time_adj | 19.6% | 91.4% | 83.0% | 97.2% |
| card_rating | 97.6% | 99.6% | 98.8% | 100.0% |
| weight_carried | 100.0% | 100.0% | 100.0% | 100.0% |
| same_distance_starts | 87.8% | 96.5% | 96.0% | 99.1% |
| same_venue_distance_starts | 85.3% | 96.5% | 96.0% | 99.1% |
| tw_entries_count | 35.8% | 100.0% | 100.0% | 100.0% |
| raw_formline_higher_win_count | 84.8% | 67.8% | 80.5% | 95.3% |
| prior_combo_starts | 83.4% | 84.4% | 84.9% | 92.5% |
| prior_jockey_cd_starts | 78.8% | 87.1% | 83.8% | 88.8% |
| prior_trainer_cd_starts | 82.5% | 93.8% | 89.4% | 97.2% |

## Evidence coverage欄

| Family | 只計存在性嘅primitive | 用途 |
|---|---|---|
| form | last6_runs, raw_last_finish, raw_last_margin, season_starts | Step 3只用作向中性60收縮，唔直接當能力edge |
| speed | raw_l400, raw_finish_time_adj | Step 3只用作向中性60收縮，唔直接當能力edge |
| class_weight | card_rating, weight_carried, starts | Step 3只用作向中性60收縮，唔直接當能力edge |
| distance | same_distance_starts, same_venue_distance_starts, prior_class_distance_starts | Step 3只用作向中性60收縮，唔直接當能力edge |
| trainer | prior_combo_starts, prior_jockey_cd_starts, prior_trainer_cd_starts | Step 3只用作向中性60收縮，唔直接當能力edge |
| readiness | days_since_last, tw_entries_count, tw_gallop_count, raw_weight_trend_span | Step 3只用作向中性60收縮，唔直接當能力edge |
| formline | raw_formline_higher_win_count, raw_formline_same_win_count, raw_formline_lower_win_count | Step 3只用作向中性60收縮，唔直接當能力edge |

## Step 2判斷

- 245場已可放入同一outcome-free primitive schema，但archive係materialized snapshot，近期係Logic重建，source mode必須保留。
- Step 3只可使用跨development／temporal／近期均有合理覆蓋嘅primitive；版本專屬舊feature分正式淘汰。
- 第三選有效升格需要嘅原模型rank及實際前三label已隔離保存，供Step 6評估，唔會參與dimension建構。
- 本步未定義新分數、未以賽果揀欄位、未改正式Auto engine。
