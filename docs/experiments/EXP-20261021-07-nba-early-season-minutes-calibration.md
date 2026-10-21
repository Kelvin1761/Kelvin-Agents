# EXP-20261021-07 NBA 賽季初「分鐘校正」：修正 μ = rate × prior-10 平均 MIN 嘅高估

- **日期**：2026-10-21
- **平台**：NBA
- **假設**：EXP-06 發現賽季頭 10 場 count model 系統性高估（第 1 場約 −8pp），而實際分鐘比 prior-10 平均 MIN 低 4–11%（第 1 場 0.89–0.93，第 6–10 場 ≈1.0）。**假設：只用 dev 擬合嘅「分鐘因子」`f`（`μ = rate × min10 × f`）可以移除水平偏差，之後 frozen layer-A 重校準（`a_s,b_s`）原封不動套用到賽季初 unit 就有效。** 可證偽：若冇任何 `f` 方案過下面條件（包括 selection-bias 否決、同第 1 場／第 2–5 場嘅水平偏差條件），結論就係「賽季初 shadow 維持 null，最平嘅誠實 policy 係 `n_cur ≥ 5` 先出機率」。
- **搜索過嘅舊記錄**：EXP-20261021-02～06（尤其 06：population、否決機制、§7.4 分鐘診斷）。冇賽季初分鐘校正記錄。
- **改到嘅檔案／組件**：**冇改 production code，冇改 frozen artefact `nba_fit_layer_A_v1.json`。** 新增 `docs/experiments/patches/nba_calibration_exp20261021_02/nba_early_minutes.py`（重用 `nba_early`、`nba_pregame`、`nba_refit`、`nba_fit_layer`）。
- **狀態**：🔵 協議已寫（未跑結果）。

> 限制同 EXP-02～06：線係「L10（含上季）平均附近 3 個整數」，唔係莊家開價母體 —— **只量機率引擎校準度，冇講利潤／EV**；只有 7 個可重現 live 項；只常規賽；population 只係上季 ≥40 場且平均 ≥20 分鐘嘅 rotation 球員（唔包新秀、交易、長傷復出）；H2／H3 早過 dev＝跨季穩健性，唔係前瞻。

## 1. Population、切分、輸入（同 EXP-06，凍結）
- **Early unit**：同季第 1–10 場（`n_cur∈[0,9]`，同季、日期嚴格 `<D`、`MIN>0` 出場數），上季 ≥40 場且上季平均 MIN ≥20；對本場 MIN／有冇上場／早退 一概唔過濾（`MIN==0` 行保留 y=0）。L10 混合上季（同 live）。線／stat／clip／bootstrap 同 EXP-06。
- **dev**＝2025-26 early、日期 `<2026-01-01`；**H1**（描述性，57 units，不入判決）；**H2**＝2024-25（carryover 自 2023-24）；**H3**＝2023-24（carryover 自 2022-23）。輸入檔 `out6/rows.csv`（sha256 `a96b350a…`，EXP-06 產生，71,259 行；含 `min_g`、`min10`、`n_cur`、`prior_min_mean`、`prior_total`、`prior_min_total`、`S_cur`、`M_cur`）。**所有擬合只用 dev，H2、H3 各評估一次。**
- Count model 固定沿用 EXP-06：EB 混合 c1，`k`＝PTS 5／REB 40／AST 5／3PM 8（EXP-06 dev 擬合，**不重新擬合**），NB 離散度＝layer-A 凍結值（PTS `α=0.19715`，其餘 Poisson）。

## 2. Arm（固定，唔准加）
令 `μ_f = max(0.05, rate_blend × min10 × f)`（`rate_blend` 同 EXP-06 c1）；分鐘因子 `f` 對所有 stat 一樣。階層（`n_cur`）：**S0＝第 1 場（n_cur=0）、S1＝第 2–5 場（1–4）、S2＝第 6–10 場（5–9）**。上季平均 MIN 桶：**B1＝20–25、B2＝25–30、B3＝≥30**。

| Arm | 定義 |
|---|---|
| **R0** | live base（`hit_L10`，reference） |
| **M0** | EXP-06 A1：凍結 layer-A 重校準套用喺 c1（`f≡1`）。比較 arm |
| **M1f** | `f = f_M1(stratum)`：3 個乘數；frozen 重校準 as-is |
| **M1x**（探索） | 同 M1，但 per-stat 重校準 `a_s + b_s·logit(p)` 喺 dev early 重擬合 |
| **M2f** | `f = f_M2(B×S)`：9 個乘數（含收縮，下述）；frozen 重校準 as-is |
| **M2x**（探索） | 同 M2，重校準喺 dev 重擬合 |
| **M3**（policy） | 同 M0 嘅機率，**只喺 `n_cur ≥ 5`（S2）出**，之前 null。報 coverage ＝ 保留 unit 比例；喺保留子集同 R0／E 比較 |
| **E** | live 最終機率（比較 arm；同 EXP-06） |
- Candidate（要過判決）：**M1f、M1x、M2f、M2x、M3**。R0、M0、E 係比較 arm。

**`f` 嘅擬合方法（預先揀定，只一種）**：**ratio-of-sums**＝ `f_cell = Σ min_g / Σ min10`，喺 dev early 嘅 unit（每個 player-game 計一次，`MIN==0` 亦計）。理由：`μ = rate × expected minutes`，所以 `f` 應該係「期望實際分鐘／預測分鐘」，閉式解、直接針對機制，唔係針對 Brier 調（避免對機率層過擬合）；唔用 mean-of-ratios（會被低分鐘極端比放大）。
- **M1**：3 個 `f_M1(S0,S1,S2)`。
- **M2**：9 格 `raw_cell`（同上方法），**向 M1 收縮**：`f_M2 = (n_cell·raw_cell + 100·f_M1(stratum)) / (n_cell + 100)`，`n_cell`＝該格 dev unit 數（收縮強度 100 unit 預先登記，唔 tune）。
- 之後 M1f／M2f 嘅機率＝ `sigmoid(a_s + b_s·logit(clip(p_count(μ_f))))`，`(a_s,b_s)` 取自 `nba_fit_layer_A_v1.json`（唯讀）。M1x／M2x 嘅 `(a_s,b_s)` 另外用 dev early 對 `logit(p_count(μ_f))` per-stat 擬合。
- **Parity**：對 c0 型（`μ=rate_prior×min10×f`）用 `fit_prob_A(stat,line,prior_total,prior_min_total,min10×f)` 同 harness 公式比較，差 <1e-9。

## 3. 預先登記判決規則（全部成立先叫 `passes`）
對每個 candidate（M3 用 `n_cur≥5` 子集）：
1. **H2** pooled `ΔBrier vs R0` 95% CI 全部 <0；
2. **dev** pooled `ΔBrier vs R0` 點估計 <0；
3. **H3** pooled `ΔBrier vs R0` 95% CI 全部 <0；
4. calibration slope ∈ [0.85,1.15]，**H2 同 H3 都要**（點估計）；
5. H2 pooled 10 桶 reliability：所有 n≥500 桶 `|mean p − mean y| ≤0.05`；
6. （M1／M2 系）**H2** pooled `ΔBrier vs M0` 95% CI 全部 <0（`f` 要有額外增益；M3 同 M0 機率相同，此條不適用）；
7. **水平偏差（新）**：`citl ＝ mean(p − y)` 喺 **S0（第 1 場）同 S1（第 2–5 場）** 兩個 stratum，喺 **H2 同 H3**，必須 **|citl| ≤0.03 且 95% CI（GAME_ID cluster bootstrap）包 0**。M3 唔含 S0／S1，改為 S2（第 6–10 場）同一要求。
- **Selection-bias 否決（不變）**：喺 **dev**，用該 candidate **自己嘅最終機率**，按 (a) 上季平均 MIN 桶 B1／B2／B3、(b) `n_cur` 階層 S0／S1／S2 計 `mean(y − p)` 同 cluster bootstrap 95% CI；任何桶 `|平均殘差|>0.03` 且 CI 排除 0 → **否決，任何 `passes` 作廢**（M3 只看保留子集內嘅 B 桶同 S2）。同一表亦喺 H2、H3 報告（描述性；水平要求由條件 7 把關）。
- 不准用 H2／H3 重擬合、換 `f` 方法／收縮強度／`k`、換階層或桶、換指標或窗口去救候選。想換設計就開新實驗。
- Holm 只作資訊（5 個 candidate vs R0）。
- 「frozen layer A 可否原封不動重用」＝ M1f／M2f（frozen 重校準）喺條件 4、7 同否決下嘅結果；若只有 M1x／M2x 過，結論＝需要新版本 artefact（**絕不改 `nba_fit_layer_A_v1.json`**）。

## 4. 其他報告（描述性）
- **分鐘預測質素（機制）**：unit 層面（含 `MIN==0`）按 S0／S1／S2 同 B1／B2／B3（dev、H2、H3）：`mean(actual MIN / min10)`、預測 `min10×f` 嘅 bias（`mean(actual − pred)`）、MAE、RMSE，`f=1` 對 M1／M2。
- 每個 arm：Brier、log-loss、slope／intercept、citl、10 桶 reliability、逐 stat、逐 stratum Brier／slope／citl。
- 選注視角：`p≥0.70`、`p≥0.80`，R0、M0、M1f、M1x、M2f、M2x、M3（子集）、E：n、佔比、平均 p、實際命中率；H2、H3、dev。M3 另報 coverage（保留 unit 佔 early unit 比例）。
- 洩漏檢查：point-in-time 單元測試（重用 EXP-06＋新增：`f` 只由 dev unit 計出，唔含 H2／H3；`f` 套用後 feature 唔隨 outcome 改變）；shuffle test（dev：置換 `y`，重擬合 M1x 重校準，per-stat 斜率 `|b|<0.10` 為 PASS）。
- 若有 candidate `passes`（含否決通過）：寫 shadow-extension 設計（extractor 額外輸入：上季 Σstat、ΣMIN、上季平均 MIN、同季已賽場數 `n_cur`、`S_cur`、`M_cur`；新 status 值例如 `ok_early_season`；**新版本 artefact 檔，唔改 v1**；forward 證據要求）。若冇：直接寫「賽季初 shadow 維持 null（`insufficient_games`）」同最平嘅誠實 policy。
- **「what could still be wrong」** 一節。

## 5. 重跑
（跑完後填）

## 6. 結果
（跑完後填）
