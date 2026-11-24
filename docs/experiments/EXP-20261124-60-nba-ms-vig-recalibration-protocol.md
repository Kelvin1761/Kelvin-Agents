# EXP-20261124-60 協議：NBA MS 層市場抽水曲線重校準 —— 預先登記（睇結果之前寫）

- **日期**：2026-11-24
- **平台**：NBA
- **起因**：Kelvin 2026-11-24 叫 Claude 同 Codex 一齊覆核 NBA Wong Choi 有冇得改善模型表現。
- **性質**：研究候選；未接入引擎。冇過判決就唔改 `config.json`。

## 假設
`p_final`（MS）= `sigmoid(a_stat + β·logit(1/價) + γ·logit(S))`。市場輸入係**包抽水**嘅單邊 milestone 價，抽水只靠每個 stat 一個常數截距同一個斜率去扣。
但 milestone 梯級嘅抽水唔係常數：EXP-20261120-60 嘅 `bias_check` 見到喺 O/U 主線，milestone 1/價 = 0.517、去水兩邊價 = 0.487、實際 0.489、`p_final` 只得 0.452
—— 即係主線附近扣多咗抽水，而線越高越嚴重（10+ 線模型 42.4% 對實際 55.0%）。
**假設：MS 嘅錯誤係「抽水隨 1/價 變」冇被模型捕捉；加一個彈性嘅市場項（logit(1/價) 嘅二次項／分段）可以改善全部 milestone 腿嘅 log-loss。**

## 數據
- `docs/experiments/patches/nba_ms_recal/build_dataset.py`（Codex Terra 寫，Claude 核對）→ 每條已結算 milestone 腿一行：最早一個開波前 `production` `model_obs` 嘅 `p_market`、`p_s`、`p_final` 等，加結算 `y`。
- target_date 2026-10-29 … 2026-11-24（void／冇結算唔計）。

## 切法（固定）
- **dev** = target_date ≤ 2026-11-11；dev 入面 leave-one-day-out 揀模型形式。
- **holdout** = 2026-11-12 … 2026-11-24，只開一次。
- 注意：MS 原本係數擬合喺 10-22…10-28，唔喺呢兩段入面；S2 forward（EXP-20261111-05）嘅判決規則已凍結，呢度用同一段日子做 holdout 唔會改佢嘅判決。

## 候選（全部喺 dev 擬合，全部特徵賽前已知）
- **R1**：同一形式重擬合（a_stat、β、γ）—— 量「純粹重擬合」有幾多。
- **R2**：R1 ＋ β2·logit(m)²（每個 stat 共用）。
- **R3**：R1 ＋ 每個 stat 自己嘅 β（市場斜率逐 stat）。
- dev LODO 揀 R2／R3 其中一個（或者 R1，如果冇一個好過 R1 嘅 dev LODO 而且 CI 下界 <0）。**只揀一個入 holdout。**

## 判決（只開一次）
- 主指標：holdout Δ = 平均 log-loss(候選) − 平均 log-loss(`p_final`)，按日 cluster bootstrap 2,000 次，seed 20261124。
- **KEEP 候選**（交 Kelvin 決定上唔上線）：Δ 95% CI 上限 < 0，**而且**揀咗嘅候選對 R1 嘅 Δ CI 上限都 < 0（否則只係重擬合嘅功勞，記錄為「重擬合」唔係「抽水曲線」）。
- 次要（只報告）：逐 stat Δ；穩膽 B2 合資格腿（p ≥ 0.7）嘅 Δ；O/U 主線腿嘅平均 P(大) 對實際。
- 唔准喺 holdout 之後換形式、換切法、換 clip。

## 洩漏
`p_market`／`p_s` 都係 21:00 run 寫低嘅賽前值；`y` 只做標籤。冇用今仗以後嘅任何嘢。
