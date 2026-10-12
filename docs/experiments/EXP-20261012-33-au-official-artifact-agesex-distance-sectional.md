# EXP-20261012-33 AU 正式 artifact 路徑：馬齡 × 性別、distance 重建、sectional 重建

- **日期**：2026-10-12
- **平台**：AU
- **判決尺**：Stage 4 v3 `walk_forward_oos`，經 Codex 正式路徑
  `au_oos_predictions.produce_walk_forward` → `au_prediction_evaluation.evaluate_family`
  - 包括 provenance、功效記錄、馬匹數 cohort guardrail、Holm（arm × metric）
  - 按合約，歷史 WIN 一律 `PENDING_FORWARD`，`release_authorized=False`
- **⚠️ 披露**：
  - 呢個家族係**喺 EXP-20261012-32 診斷之後先登記**，即係確認性重跑，唔係真正預先登記。
  - 功效記錄嘅部件預算同 MDE 係同一批 walk-forward 預測入面量嘅，屬 in-sample 代理。
- **語料**：最終 code（`c28db618` 等價）重建語料，2026-08-05 → 10-11。
  - **provenance 規則**：一場只會入 manifest，如果 production Racecard 同 Formguide 嘅檔案時間 ≤ 開跑日 12:00 +10:00。
  - 結果 2,295 場入 manifest，約 141 場因為來源係中午後先寫入而被剔走。
  - 賽果視為當日 23:59 先可用。
- **Walk-forward**：
  - 每個賽日只用之前已出賽果嘅場次 fit 殘差表（分層收縮 m=40），c ∈ {0, 10, 20, 40}。
  - 暖身期係 300 場、14 個賽日，暖身期內用 baseline。
- **Harness**：scratchpad `harness/official_family.py`。輸出 `out2/official_agesex_dist_sect.json`。

## 候選

| arm | 內容 |
|---|---|
| `agesex` | 馬齡（2..7+）× 性別（雄／閹／雌），分層到距離段 |
| `dist` | **重建 distance**：distance_score 分箱，加「冇證據」缺失指示，分層到距離段 |
| `sect` | **重建 sectional**：冇 PI 嘅馬自成一組（唔再同「跑得慢」坐同一個 60 地板），分箱，分層到距離段 |

distance 嘅洩漏審計：Facts 由 `inject_fact_anchors` 用 as-of 截斷生成，賽日或之後嘅往績唔入。
重建語料係用場次日期做 `_AS_OF` 重新生成 → **PASS**。

## 結果

| arm | 判決 | Gold | Good | 最強 ranking | Holm 後 | cohort |
|---|---|---:|---:|---|---:|---|
| agesex | **REJECT** cohort_regression | +0.04 [−0.48,+0.62] | **+0.65 [+0.13,+1.18]** | ndcg@5 +0.21 [+0.03,+0.39] | Good 0.195 | **細場（4–8 匹，716 場）Gold −0.98 [−1.91,−0.13] = HARM** |
| dist | **REJECT** ranking_evidence_too_weak | +0.04 | +0.09 | top3_capture +0.19 [+0.01,+0.37] | 0.546 | 冇傷害 |
| sect | **REJECT** primary_regression | +0.09 | 0.00 | 全部近零或者負 | — | 冇傷害 |

### 讀法

- **馬齡 × 性別**：
  - 整體 Good 升，但細場 Gold 顯著跌。
  - 細場入面同時 Good +1.26pp，即係佢將「頭兩揀」推向年輕馬、雄馬，但犧牲咗第 3–4 位嘅覆蓋。
  - EXP-32 個診斷冇 cohort guardrail，所以睇唔到呢點。正式尺捉到。
  - 「按馬匹數縮放嘅馬齡 × 性別」係**睇完先諗到**嘅假設，唔准喺同一批數據救返。
    已經登記做前瞻假設：2026-10-13 起嘅新賽日、一次開盤。
- **distance 重建**：
  - 有輕微排序訊號（top3_capture p=0.042），但 Holm 之後唔顯著，primary 冇郁。
  - 同 2026-10-10 用舊 leaf 硬加嘅結果一致。
- **sectional 重建**：
  - 將「冇 PI」同「跑得慢」分開之後，仍然冇訊號。
  - 48.8% 冇 PI 數據嘅問題係**來源問題**：Sportsbet 只有上名場先計到 PI。改評分解決唔到。

## 附：Platinum Card 個 pace_figure（試閘）係咪 bug？

pace_figure 全靠試閘嘅 681 匹馬（有賽果），按分數分組計入位超額：

| pace_figure | 匹數 | 入位超額 |
|---|---:|---:|
| ≥70 | 210 | **+10.5pp** |
| 50–70 | 207 | −0.2pp |
| <50 | 263 | **−12.3pp** |

試閘 PF 同正式賽 PF 一樣單調而且有預測力。Platinum Card 84.1 分係一個平均嚟講有用嘅訊號，佢跑尾屬個別結果。
所以 F2（剔走試閘）撤回係啱嘅，唔係漏修。

## 決定

- agesex、dist、sect：**REJECT**，唔改 production code。
- 馬齡性別 shadow code 留喺 Claude worktree `claude-au-trial-leak-20261012`，**唔發佈**。
- 新登記前瞻假設 `age_sex_field_scaled_forward`：馬齡性別效應 × clip((n−5)/7, 0, 1)。
  - 只用 2026-10-13 起嘅賽日，≥600 場先開。
  - 經正式路徑判。
