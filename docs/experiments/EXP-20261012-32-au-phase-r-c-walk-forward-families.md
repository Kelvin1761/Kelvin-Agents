# EXP-20261012-32 AU Phase R／C／H6 walk-forward 家族 —— 檔位、步速形勢、馬場 × 跑法、pace_figure 收縮、馬齡 × 性別

- **日期**：2026-10-12
- **平台**：AU
- **判決尺**：Stage 4 v3 `walk_forward_oos`。⚠️ 呢度係**診斷**：直接叫 `evaluate_full_record`，
  未經 Codex 嘅 prediction-artifact 正式路徑（`au_prediction_intake` / `evaluate_family`），所以**唔授權發佈**。
- **語料**：2026-08-05 → 10-11，358 個場次由 Racecard／Formguide 用現行 code 重新生成 Facts／Logic
  （EXP-20261012-31 嘅 `base` arm，四個試閘／Last10 修正全關），2,436 場 / 23,490 匹 / 68 個賽日。
- **搜索過嘅舊記錄**：au-draw-signal-loses-to-neutral、au-draw-matrix-leaks-into-backtests、
  au-race-shape-removed-from-ranking、au-run-style-single-source-and-rejected、au-pace-figure-is-the-only-orthogonal-leaf、
  au-pace-perf-weight-is-optimal、au-track-geometry-is-data-not-a-signal、HKJC EXP-0928-04（同日偏差，唔重做）

## 方法（量之前固定）

- **殘差**：`入位 − P(入位 | 模型名次桶, 馬匹數)`，P 只用**之前**賽日估 —— 量模型未知道嘅嘢，避免重複計算。
- **效應表**：分組鍵嘅平均殘差，分層收縮 `n/(n+40)`（全國 → 賽道幾何類／距離段 → 馬場），m=40 固定唔 fit。
- **形勢類**乘 `clip((n−5)/7, 0, 1)` —— 細場縮向零（Phase F 要求）；馬齡性別唔乘。
- **候選**：`ability + c·效應`，c ∈ {0, 10, 20, 40}，每個賽日用之前賽日嘅 Gold+Good 揀，頭 14 日 c=0。
- **R3**：`pace_figure = 60 + (pf−60)·n/(n+k)`，k ∈ {0,0.5,1,2,3,5,8} walk-forward。
- **多重比較**：今日 6 個家族，Holm。

## 結果

| 家族 | 覆蓋 | v3 判決 | Gold | Good | 最強 ranking 指標 | Holm 後 |
|---|---:|---|---:|---:|---|---|
| R3 pace_figure 收縮 | 97% | **REJECT** primary_regression | +0.00 | −0.08 | — | — |
| R1 檔位（距離段 × 檔位三分位，分層到馬場） | 88% | **REJECT** primary_regression | +0.04 | −0.12 | — | — |
| R2 步速形勢（跑法 × 前置壓力） | 63% | **REJECT** primary_regression | −0.12 | −0.16 | — | — |
| 檔位 × 跑法 | 63% | **REJECT** primary_regression | +0.08 | −0.04 | top3_capture p=0.01 | — |
| **C 馬場 × 跑法** | 63% | RANKING_WIN | +0.12 | +0.21 | top5_auc p=0.010 | **0.05 → 唔顯著** |
| **H6 馬齡 × 性別** | 89% | **RANKING_WIN** | +0.12 | **+0.62** [−0.16,+1.39] | **ndcg@5 p=0.002** | **0.012 ✅** |

### 點解 R1／R2 都唔得

同舊記錄一致：檔位同步速喺 AU 冇淨剩訊號（[[au-draw-signal-loses-to-neutral]]），就算用 point-in-time
效應表、馬匹數縮放、按馬場分層都一樣。「HKJC race_shape 27% 而 AU 係 0」**唔係遺漏**：HKJC 場地少（2 個）、
馬匹數穩定（~12）、檔位效應大；AU 129 個馬場、19 個有 ≥40 場，分層收縮之後大部分 cell 接近全國平均，
而全國平均嘅檔位效應模型（form／rating）已經吸收咗。

### R3 pace_figure

全距單調（≤30 −13.4pp … ≥90 +11.9pp），單場樣本嘅高分超額較細（+7.6pp vs 3–4 場 +16pp），
但 walk-forward 只揀 k=0.5，Good −0.08pp。**pace_figure 冇壞**，2026-10-12 幾匹高 pf 首選落空係正常波動。

### H6 馬齡 × 性別（今日唯一過 Holm 嘅家族）

控制模型名次後嘅殘差（23,490 匹，賽日 bootstrap）：
3 歲 +3.21pp [+2.10,+4.39]、4 歲 +0.50、5 歲 +0.04、6 歲 −0.07、**7 歲以上 −3.31pp [−4.55,−2.14]**；
雌馬（M）−1.72pp [−2.33,−1.05]、雄馬（C）+6.65pp [+2.54,+11.05]、閹馬 +0.47。
來源係賽前 Racecard `Age: 5yoM` —— leakage audit **PASS**（賽前已知、唔會變）。
模型由來冇用：`RACECARD_META_RE` 對到 `Age:` 但冇存。

固定 c 全部正：c=10 +18、c=20 +26、c=40 +30 場 Gold+Good（in-sample，只作方向參考）。

## 決定

- R1、R2、R3、檔位 × 跑法：**REJECT**，唔改 code。
- C 馬場 × 跑法：**PROMISING / NEEDS MORE TESTING**（Holm 後唔顯著），唔上線、唔做 shadow。
- **H6 馬齡 × 性別：SHADOW**。實作喺 worktree：
  - `source_alignment.RACECARD_META_RE` 加 `age` group；`engine_core` 將 `age_sex` 寫入 Logic（抽取層 §7）
  - `au_racing_engine/age_sex_overlay.py` + `resources/au_age_sex_overlay_v1.json`（凍結 2026-08-05→10-11 表，c=40）
  - 預設 **唔入 ability**，每匹馬寫 `age_sex_shadow_delta`；`WC_AU_AGE_SEX_LIVE=1` 先生效
  - **Forward holdout**：2026-10-13 起嘅賽日，一個家族只開一次；≥600 場再經正式 artifact 路徑判。
- 記錄寫明：**唔係已證實嘅 primary 改善**（Good CI 跨零）。

## 2026-10-12 更新：正式 artifact 路徑判決（EXP-20261012-33）

上面係**診斷**（冇 cohort guardrail，冇 provenance，未經 Holm 全家族）。經正式路徑重跑：

- **馬齡 × 性別 → REJECT（cohort_regression）**：細場（4–8 匹，716 場）Gold −0.98pp [−1.91, −0.13]，屬顯著傷害；整體 Good +0.65pp，Holm 後 p=0.195。
- shadow code **唔發佈**。「按馬匹數縮放」嘅版本登記做前瞻假設（2026-10-13 起）。
