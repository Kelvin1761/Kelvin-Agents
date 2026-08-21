# HKJC Wong Choi 候選影子測試（2026-07-17）

> 預先登記 gate（同 AU）：Good（positional）**≥ +1.5pp** OOS、meeting-grouped 擴張式
> walk-forward；Gold/Top1/W-in-T3 損失 **≤ 0.5pp**；Miss 不倒退；Top3 fold 穩定度 **≥ 4/5**；
> 每 fold 只喺 train meeting 揀參數。預期大部分候選被 kill——呢個係系統運作正常。

## 候選來源（因果觸發 + 已量化支持）

2026-07-17 cohort 歸因（`hkjc_failure_cohorts.py`，全 243 場、in-sample perturbation）之中，
**只有一個**候選有因果故事＋可量化支持：

- **`trainer_signal` 減權**：trainer_signal 係第二大權重（0.221）。In-sample perturbation
  顯示 −20% 令全 archive Good-pos +1.6pp（21.0% → 22.6%），且 ShaTin/HappyValley 同向。
  其餘維度：race_shape（0.256，最大）drop 傷 −5.8pp，係主力，不動；stability/form_line/
  class_advantage 擾動只得雜訊級變化；sectional 見 §重新評分報告（淨中性至有害，不加權）。

其餘 in-flight 已測並否決嘅候選（見 `hkjc-dimension-rebuild.md`）：readiness_health_slot、
三個完整矩陣候選、兩個 trainer 收縮案（Top2-hit 尺）——本次唔重複。

## Gate 結果 — `trainer_signal` 減權：FAIL

`scratch/hkjc_candidate_walkforward.py`，5 folds，每 fold 於 train 揀 {0.7, 0.8, 0.9} 最佳倍率。
純 re-weighting stored `matrix_scores`（重建對 stored ability_score 精確：51=51 good-pos）。
分「全 archive」同「faithful cohort（`HKJC_LOGIC_V4_2`，段速可見，171 場）」兩組報，
避免 4月 sectional-blind 假象美化 go-forward 權重決定。

| 組別 | Good Δ | Gold Δ | Top1 Δ | W-in-T3 Δ | Miss Δ | Top3 穩定 | 裁決 |
|---|---:|---:|---:|---:|---:|---:|---|
| 全 archive（243） | **+1.53pp** | +0.95 | **−1.48pp** | **−0.99pp** | 0 | 4/5 | **FAIL** |
| faithful（171） | **+0.73pp** | +1.88 | −0.61pp | −0.08pp | −0.2 | 4/5 | **FAIL** |

- 全 archive：Good 剛好過 +1.5pp 門檻，但 **Top1 −1.48pp、W-in-T3 −0.99pp** 遠超 ≤0.5pp
  損失上限。即係減 trainer_signal 為咗砌多啲 good-positional 對，但**同時將實際頭馬踢出頭一/二位**。
- Faithful cohort：Good 只 +0.73pp，未達門檻；Top1 仍然 −0.61pp。

呢個正正印證 in-flight 記錄：「兩個 trainer 收縮案均傷害總 hits 及頭馬而否決」。頭馬捕捉係
trainer_signal 減權嘅硬成本。**現行權重保留。**

## Zero-hit 歸因 — misses 係缺證據，非權重問題（同 AU 一致）

45 場 zero-hit（模型 top-2 全部跌出前三）之中，實際頭馬 vs 模型 top-2 嘅 matrix 分差：

| 維度 | 頭馬 − top2 平均 |
|---|---:|
| horse_health | +0.49 |
| form_line | −0.35 |
| class_advantage | −1.52 |
| sectional | −2.86 |
| trainer_signal | −4.95 |
| stability | −8.02 |
| race_shape | −8.57 |

除 horse_health 幾乎持平外，冷門頭馬喺**每一個維度都輸蝕**俾模型 top-2。即係冷門贏馬喺矩陣上
樣樣都唔起眼——係爆冷/缺證據，唔係「訊號存在但被權重蓋過」。**重新配權救唔到呢啲場**，同 AU
（zero-hit 係 missing-evidence 問題）結論一致。

## HKJC 專屬 confidence-tiered radar（已實作）

Cohort 顯示 **tight score-gap（top1−top3 < 2）佔 98/243 = 40% 場次**，係弱 cohort
（Good-pos 16.3%、W-in-T3 46.9%，皆低於 archive 平均）。已喺 HKJC 自身 archive 校準並實作
（`ensure_verdict` 加 `confidence_tier`/`radar`；顯示層加「信心分層投注雷達」；純顧問性，
**不改排名、分數或 model_pick_status**）。

校準（`scratch/hkjc_radar_calibration.py`，逐 tier 統計 radar 命中率）：

| Tier（頭三分差） | n | Top-2 捉≥2冷門 | Top-4 | Top-5 | 頭馬 win@2 | win@5 | radar |
|---|---:|---:|---:|---:|---:|---:|---:|
| tight (<2) | 98 | 16.3% | 60.2% | 70.4% | 28.6% | 59.2% | **5** |
| medium (2-5) | 125 | 24.0% | 56.8% | 69.6% | 43.2% | 70.4% | **4** |
| clear (>=5) | 20 | 25.0% | 60.0% | 75.0% | 45.0% | 80.0% | **4** |

tight tier 之下 Top-2 只捉到 16.3% 嘅「≥2冷門入前三」場，擴到 Top-5 升到 70.4%，所以 radar 開到 5；
medium/clear 維持 4（Top-4 已捉到約 57-60%）。HKJC 專屬事實：tight 佔 40% 場次（遠高於 AU），
所以雷達會經常觸發。實作見 `renderer.py` `_confidence_tier`/`_radar_lines`；測試
`test_confidence_radar_tiers_from_score_gap_and_leaves_ranking_unchanged`、
`test_confidence_radar_renders_without_banned_terms`。

## 可重跑輸出

- `scratch/hkjc_candidate_walkforward.py` → `scratch/hkjc_candidate_walkforward.json`
- `scratch/hkjc_failure_cohorts.py` → `scratch/hkjc_failure_cohorts.json`
