# EXP-20261121-38 大爛地 overlay：同一套 leaf、今日 Heavy 先調權重（預先登記，2026-11-21，跑之前寫）

- 起因：Kelvin「I prefer not to be reverting to the old formula, it feels like using two system… see how we can do anything
  differently or overlays to make it work」。H2（EXP-20261105-06，大爛地轉用舊近績公式）forward 23/200，唔再當首選方向。
- 機制假設（EXP-20261105-06 量過）：大爛地名次 AUC 跌、獎金 AUC 升 —— 同一批 leaf 喺大爛地嘅資訊量唔同。
  所以做法係**今日掛牌 Heavy 先開嘅 overlay**：綜合分 + β_H ×（leaf − 場均 leaf）。唔換公式、唔加新來源，冇 Heavy 嘅日子零變化。
- 語料：`au-noise-20261113/BASE.json`（3,736 場；今日 Heavy 201 場、25 日）。
- β_H walk-forward：每場 Heavy 用**之前**嘅 Heavy 場次 logistic `入三甲 ~ a + b·(綜合分 − 場均) + c·(leaf − 場均)`，β = c/b，
  限 [−1.5, 1.5]（每 leaf 分）；之前少過 30 場 Heavy → β = 0。
- arm（每個 leaf 一個，21 個）：class, confidence, consistency, distance, form_quality, form, formline, health, jockey_horse_fit,
  jockey, pace_figure, pace_map, performance_quality, preparation, rating, sectional, track, trainer, trial, trial_speed, weight；
  加 3 個非 leaf：wet（濕地 overlay 值）、FRONT（跑法含 前置／前領／跟前 = 1）、BARRIER（檔位 ÷ 場大細）。共 24 個 arm。
- 判決：`au_logloss_ruler.evaluate`（log-loss CI 上界 < 0、Gold／Good 下界 > −1pp、好過 95% null），全語料（非 Heavy 場次 Δ = 0）；
  24 個 arm Holm（單邊 bootstrap p）。另報淨 Heavy 子集 Gold／Good。
- PASS 都唔直接上線：要 Kelvin 決定 + forward（固定 β）；同 H2 forward 並行比較。
- 唔准：改 leaf 列表、改 β 範圍、改最少樣本、換語料。

---

# 結果：**24 個 arm 全部 REJECT**（Holm 最細 0.64）

| arm | β 中位 | Δlog-loss [95% CI] | 單邊 p | 大爛地 Gold／Good Δpp |
|---|---:|---|---:|---|
| health | +1.50（撞上限） | −0.000052 [−0.000108, 0.000000] | 0.027 | +0.5／+0.5 |
| confidence | +0.63 | −0.000128 [−0.000300, +0.000024] | 0.053 | +0.5／−1.49 |
| formline | +0.05 | −0.000031 [−0.000105, +0.000034] | 0.19 | +0.5／0.0 |
| wet（濕地 overlay 加倍） | +0.96 | −0.000043 [−0.000178, +0.000060] | 0.25 | +0.5／−0.5 |
| form_quality | −0.23 | +0.000027 [−0.00021, +0.00028] | 0.57 | −1.49／+1.0 |
| **form**（加權） | +0.39 | **+0.000328 [+0.000159, +0.000535]** | 1.0 | 有害 |
| **consistency**（加權） | +0.48 | **+0.000581 [+0.000099, +0.001451]** | 1.0 | 有害 |
| 其餘 17 個 | | CI 跨零或者有害 | ≥ 0.66 | |

全部數字：`EXP-20261121-38-evidence/results.json`。

## 點讀

- 用同一批 leaf、喺大爛地調權重（overlay），以 201 場大爛地嘅樣本救唔到：好多 β 撞上下限（±1.5），即係 fit 緊噪音；
  加重近績／穩定性仲明顯令 log-loss 變差。
- 同 EXP-20261121-30（濕地 overlay 大爛地倍數 ≈1）一致：現有欄位喺大爛地冇「調錯權重」嘅問題，係**資訊本身唔夠**。
- 根據 EXP-20261105-06（大爛地名次 AUC 跌、獎金 AUC 升）同「好地往績唔轉移」：問題喺**往績點讀**，唔喺維度權重。
  下一個方向（未做）：近績質素分按每仗場地同今日場地嘅相似度加權（今日 Heavy → 軟／重地往績份量重啲；好地日反之）——
  同一條公式、每日都用，唔使兩套系統。要用引擎重新評分成個語料（往績場地喺 Facts，Logic 冇儲）。
- H2 forward（23/200）照跑做量度；Kelvin 唔想上兩套公式，所以就算 H2 PASS 都唔會照搬，會用嚟對照相似度加權。
