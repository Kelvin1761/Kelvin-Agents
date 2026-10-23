# EXP-20261021-07 NBA 賽季初「分鐘校正」：修正 μ = rate × prior-10 平均 MIN 嘅高估

- **日期**：2026-10-21
- **平台**：NBA
- **假設**：EXP-06 發現賽季頭 10 場 count model 系統性高估（第 1 場約 −8pp），而實際分鐘比 prior-10 平均 MIN 低 4–11%（第 1 場 0.89–0.93，第 6–10 場 ≈1.0）。**假設：只用 dev 擬合嘅「分鐘因子」`f`（`μ = rate × min10 × f`）可以移除水平偏差，之後 frozen layer-A 重校準（`a_s,b_s`）原封不動套用到賽季初 unit 就有效。** 可證偽：若冇任何 `f` 方案過下面條件（包括 selection-bias 否決、同第 1 場／第 2–5 場嘅水平偏差條件），結論就係「賽季初 shadow 維持 null，最平嘅誠實 policy 係 `n_cur ≥ 5` 先出機率」。
- **搜索過嘅舊記錄**：EXP-20261021-02～06（尤其 06：population、否決機制、§7.4 分鐘診斷）。冇賽季初分鐘校正記錄。
- **改到嘅檔案／組件**：**冇改 production code，冇改 frozen artefact `nba_fit_layer_A_v1.json`。** 新增 `docs/experiments/patches/nba_calibration_exp20261021_02/nba_early_minutes.py`（重用 `nba_early`、`nba_pregame`、`nba_refit`、`nba_fit_layer`）。
- **狀態**：✅ 已跑一次，結果喺 §6。協議 commit `001ffdc5`（計結果前）、harness commit `22c80336`（跑真數據前）。
- **按預先登記規則**：**只有 M3（policy：`n_cur ≥ 5` 先出機率）`passes`**（含否決通過，coverage 約 50% early unit）。**所有分鐘因子方案（M1f／M1x／M2f／M2x）`not shown`**：第 1 場喺 H2 仍然高估（−3.7～−4.5pp，CI 排除 0；不同賽季第 1 場分鐘比率 0.887–0.925 變動大，單一 dev 因子糾正唔到），而且對 M0 嘅 Brier 增益細到可以忽略（H2 −0.0009）。
- **要睇清楚**：(i) M3 喺 dev 否決檢查通過，但 H2／H3 嘅上季分鐘桶殘差（描述性）顯示低分鐘桶高估 1–4pp、≥30 分鐘桶低估 2.5–3.3pp（H2 兩桶 |殘差|>0.03 且 CI 排除 0），否決只按協議喺 dev 檢；(ii) M3 只比 EXP-05 嘅 `n_cur≥10` 提早大約 5 場（約一星期）開始出 shadow 機率；(iii) 冇利潤聲稱，**冇聲稱 live 模型有任何改善**。
- **決定**：**M3 policy 可作 shadow-extension 設計（§8），其餘不採納；賽季頭 4 場維持 null。NEEDS FORWARD EVIDENCE。**

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

環境：Python 3.9.6、numpy 2.0.2、pandas 2.3.3、scipy 1.13.1；`PYTHONDONTWRITEBYTECODE=1`。Harness commit `22c80336d3f61a34ecc8055f13d621419d22c39d`（`nba_early_minutes.py`、`test_early_minutes.py`；全部 20 個 harness 測試 pass）。Frozen artefact `nba_fit_layer_A_v1.json` sha256 `7e74022c…`（唯讀；**冇改**）。
Scratchpad：`/private/tmp/claude-501/-Users-imac-Antigravity-repo--claude-worktrees-nba-calibration-exp-56dc4c/1fa02346-3347-461b-80cf-3be02bd426e1/scratchpad/`
- 輸入 `out6/rows.csv` sha256 `a96b350ab74ffc440bd16fcd8376a6a9fa1a6ba5e097343dcb2cd909ce13c690`（EXP-06）
- 輸出 `out7/results7.json` sha256 `408df6b2e3b0b74e896963c3de43c20e991c51951df9528fd835915c8c1357d4`
```bash
export PYTHONDONTWRITEBYTECODE=1
H=docs/experiments/patches/nba_calibration_exp20261021_02; S=<scratchpad>
python3 -W ignore -m unittest discover -s $H -p "test_*.py"                      # 20/20 OK
python3 -W ignore $H/nba_early_minutes.py run --rows $S/out6/rows.csv --out $S/out7   # 只跑一次
```
（`run` 內 assert：`f≡1` 時 `μ` 同 EXP-06 c1 相同；frozen artefact 呼叫 `fit_prob_A(..., min10×f)` 同 harness 公式差 <1e-9；`k` 同 EXP-06 `results6.json` 一致。）

## 6. 結果

### 6.1 分鐘因子（只由 dev 計：ratio-of-sums）
- **M1**：S0（第 1 場）0.9224、S1（第 2–5 場）0.9444、S2（第 6–10 場）0.9897。
- **M2**（9 格，向 M1 收縮，100 unit）：
| | S0 | S1 | S2 |
|---|---|---|---|
| B1（上季 20–25 分鐘） | 0.884 | 0.913 | 1.002 |
| B2（25–30） | 0.907 | 0.924 | 0.979 |
| B3（≥30） | 0.958 | 0.975 | 0.990 |
- 探索重校準（M1x／M2x，dev 擬合）：M1x `(a,b)` PTS (0.159, 0.920)、REB (−0.155, 0.846)、AST (0.014, 0.814)、3PM (−0.017, 0.889)；M2x PTS (0.171, 0.957)、REB (−0.157, 0.852)、AST (0.010, 0.818)、3PM (−0.019, 0.889)。
- Shuffle test（dev）per-stat 斜率 0.022／0.019／0.023／0.024（<0.10）→ **PASS**。Units：dev 2,076、H2 2,157、H3 2,200（同 EXP-06）。

### 6.2 分鐘預測質素（機制；unit 層面，含 `MIN==0`）
`mean(actual/min10)`；預測誤差 `actual − predicted`（分鐘；負＝預測過高）：偏差 bias／MAE／RMSE，`f=1`（原 min10）對 M1 對 M2：
| 窗 | 層 | n | 實際/min10 | bias f=1 → M1 → M2 | MAE f=1 → M2 | RMSE f=1 → M2 |
|---|---|---|---|---|---|---|
| dev | 第 1 場 | 212 | 0.922 | −2.22 → 0.00 → −0.09 | 6.14 → 5.63 | 8.18 → 7.65 |
| dev | 第 2–5 場 | 839 | 0.944 | −1.56 → 0.00 → −0.03 | 5.41 → 5.32 | 7.23 → 6.98 |
| dev | 第 6–10 場 | 1,025 | 0.990 | −0.28 → 0.00 → 0.00 | 4.32 → 4.34 | 5.58 → 5.57 |
| H2 | 第 1 場 | 217 | **0.887** | −3.36 → **−1.05** → −1.19 | 5.97 → 5.54 | 7.91 → 7.11 |
| H2 | 第 2–5 場 | 866 | 0.953 | −1.36 → +0.26 → +0.20 | 5.19 → 5.13 | 6.70 → 6.49 |
| H2 | 第 6–10 場 | 1,074 | 0.995 | −0.14 → +0.15 → +0.19 | 4.61 → 4.67 | 6.05 → 6.06 |
| H3 | 第 1 場 | 220 | 0.925 | −2.14 → +0.07 → −0.10 | 5.01 → 4.60 | 6.57 → 6.06 |
| H3 | 第 2–5 場 | 881 | 0.965 | −0.99 → +0.57 → +0.47 | 5.05 → 4.97 | 6.48 → 6.36 |
| H3 | 第 6–10 場 | 1,099 | 1.001 | +0.01 → +0.29 → +0.30 | 4.75 → 4.77 | 6.11 → 6.12 |
- **機制確認**：實際分鐘比 prior-10 低（第 1 場 0.89–0.93）；`f` 將 bias 由 −2～−3.4 分鐘拉到接近 0，但 **第 1 場個別賽季比率變動大（0.887／0.922／0.925），H2 嘅 −1.05 分鐘 bias 糾唔到**；單場分鐘本身好嘈（RMSE 6–8 分鐘），f 只輕微改善 MAE／RMSE（2–10%）。上季分鐘 B1／B2 桶偏差較大（B1 比率 0.92–0.96，B3 0.985–0.997）。

### 6.3 判決（pooled，預先登記；`ΔBrier` vs R0（live base）[95% CI]，括號＝vs M0）
| Arm | dev | H2 | H3 | slope H2／H3 | 條件 6（H2 贏 M0） | 條件 7（S0＆S1 水平，H2／H3） | 否決（dev） | **判決** |
|---|---|---|---|---|---|---|---|---|
| M0（參照） | −0.0158 | −0.0158 [−0.0180, −0.0134] | −0.0179 | 0.964／1.007 | — | S0 H2 −0.084 ❌ | — | 比較 arm |
| M1f | −0.0165 (−0.0007) | −0.0166 [−0.0192, −0.0140] (−0.0009 [−0.0015, −0.0002]) | −0.0179 (0.0000) | 0.972／1.003 | ✅ | ❌（H2 S0 −0.037 CI [−0.076, −0.005]）／✅ | **觸發**（dev B3 +0.033 [0.015, 0.051]） | not shown |
| M1x | −0.0170 | −0.0160 (−0.0002 [−0.0008, +0.0004]) | −0.0177 | 0.978／1.018 | ❌ | ❌（S0 −0.043 [−0.081, −0.011]）／✅ | 冇 | not shown |
| M2f | −0.0170 (−0.0013) | −0.0167 [−0.0192, −0.0141] (−0.0009 [−0.0015, −0.0002]) | −0.0183 (−0.0003) | 0.969／1.003 | ✅ | ❌（S0 −0.040 [−0.077, −0.008]）／✅ | 冇 | not shown |
| M2x | −0.0176 | −0.0160 (−0.0003 [−0.0009, +0.0003]) | −0.0180 | 0.967／1.009 | ❌ | ❌（S0 −0.045 [−0.082, −0.013]）／✅ | 冇 | not shown |
| E（live 最終） | +0.0036 | +0.0047 [+0.0025, +0.0068] | +0.0051 | 0.464／0.458 | — | — | — | 比較 arm（比 R0 差） |
| **M3**（`n_cur≥5`，子集） | −0.0125 | **−0.0124** [−0.0152, −0.0096] | −0.0154 [−0.0183, −0.0124] | **0.984／1.001** | n/a | S2 ✅／✅ | **冇** | **passes** |
- 其餘條件（1–5）全部 candidate 都過：H2、H3 CI <0、dev <0、slope 入 [0.85,1.15]、H2 冇壞桶。M1f／M1x／M2f／M2x 嘅失敗點＝**條件 7**（第 1 場水平偏差喺 H2 仍然 CI 排除 0）；M1x／M2x 另外輸喺條件 6（對 M0 嘅 H2 增益 CI 包 0）。M1f 亦觸發否決（dev ≥30 分鐘桶 +3.3pp，低估）。
- Holm（5 個 candidate vs R0，H2）：全部 p＝0.0005 地板；M3 子集同樣。
- **M1／M2 對 M0 嘅整體增益**：H2 −0.0009（M1f／M2f），H3 ≈0（−0.0000／−0.0003，CI 包 0）；dev（in-sample）−0.0007～−0.0018。即係即使 `f` 把水平偏差拉近，**Brier 增益細到可以忽略**。

### 6.4 水平偏差（H2、H3 的 `mean(y − p)`；負＝高估）
| 階層 | M0 H2／H3 | M1f H2／H3 | M2f H2／H3 | M2x H2／H3 |
|---|---|---|---|---|
| 第 1 場 | **−0.084**／−0.038 | −0.037／+0.008 | −0.040／+0.005 | −0.045／+0.001 |
| 第 2–5 場 | −0.025／−0.014 | +0.007／+0.018 | +0.006／+0.017 | +0.001／+0.012 |
| 第 6–10 場 | +0.010／+0.010 | +0.016／+0.015 | +0.017／+0.015 | +0.010／+0.009 |
（M0 對應 EXP-06 A1。f 版本喺第 6–10 場仍低估 1–1.7pp，因為凍結重校準本身喺 S2 帶 +1pp。）
**上季分鐘桶**（M3 子集，`n_cur≥5`；dev／H2／H3）：B1 −0.003／**−0.038**［−0.076, −0.002］／−0.012；B2 −0.004／+0.008／+0.003；B3 +0.017／**+0.033**［+0.009, +0.058］／**+0.025**［+0.001, +0.049］。dev 冇桶超標，所以否決冇觸發；但 **H2 兩個桶超標（低分鐘桶高估、≥30 分鐘桶低估）係描述性警號**：frozen layer A 喺賽季初對分鐘層級唔夠平坦。M1f／M2f 對 B 桶亦未清（M2f H3 B3 +0.027）。

### 6.5 M3 coverage
`n_cur ≥ 5`（第 6–10 場）保留 early unit：dev 49.4%、H2 49.8%、H3 50.0%（行數 49.3%／49.7%／49.8%）。即係 **賽季頭 5 場（約一半 early unit）維持 null**。對比 EXP-05 嘅 `n_cur≥10` 要求，M3 大約提早 5 場開始出機率（約一星期，視乎球隊賽程）。
M3 子集統計（c＝M0＝M3 機率，R0／E 同一子集）：dev Brier 0.2204（R0 0.2329、E 0.2412）；H2 0.2199（R0 0.2322、E 0.2392）、slope 0.984、citl −0.010；H3 0.2194（R0 0.2347、E 0.2417）、slope 1.001、citl −0.010。

### 6.6 選注視角（`p≥0.70`／`p≥0.80`；描述性，唔係利潤）
全 early unit（H2）：
| arm | ≥0.70：n（佔比）／平均 p／實際命中 | ≥0.80：n（佔比）／平均 p／實際命中 |
|---|---|---|
| R0 | 6,376（26.8%）／0.783／**0.682** | 3,442（14.5%）／0.854／**0.741** |
| M0 | 3,996（16.8%）／0.788／0.776 | 1,534（6.4%）／0.852／0.842 |
| M1f | 3,513（14.8%）／0.785／0.785 | 1,291（5.4%）／0.850／0.850 |
| M2f | 3,513（14.8%）／0.785／0.787 | 1,267（5.3%）／0.851／0.852 |
| M1x／M2x | 3,468／3,464（14.6%）／0.784／0.787、0.785／0.788 | 1,256／1,270（5.3%）／0.849／0.842、0.849／0.841 |
| E（live 最終） | 4,647（19.5%）／0.822／**0.719** | 2,400（10.1%）／0.897／**0.765** |
**M3（子集 `n_cur≥5`）H2**：≥0.70 1,978 行（佔子集 16.7%）平均 0.785／實際 0.795；≥0.80 720（6.1%）0.850／0.864；同子集 R0：3,169 行 0.782／**0.713**、≥0.80 1,728 行 0.850／**0.762**；E：2,363 行 0.821／**0.744**、≥0.80 1,218 行 0.895／**0.789**。H3 同方向（M3 ≥0.70：1,799 行 0.787／0.792；R0 0.782／0.697；E 0.823／0.730）。
**讀法**：高機率區 live base／live 最終機率喺賽季初高估 8–13pp；M0／M1f／M2f／M3 校準（差 ≤0.015，略保守）。達標腿數目由 R0 嘅 26.8% 降到 15–17%。

## 7. 呢個實驗講到乜、講唔到乜
**講到**
1. **分鐘假設確實係賽季初高估嘅主因**：實際／預測分鐘喺第 1 場 0.89–0.93、第 2–5 場 0.94–0.97、第 6–10 場 ≈1.0；用 dev 擬合嘅 `f` 可以消除大部分分鐘 bias。
2. **但分鐘因子冇令校準合格**：第 1 場個別賽季比率變動大（H2 0.887），H2 第 1 場高估（−3.7～−4.5pp，CI 排除 0）仍然超標；對 M0 嘅 Brier 增益 ≤0.0009（H3 ≈0）。所以 **M1／M2（含探索重校準）冇一個過關**。
3. **最平嘅誠實 policy（M3：`n_cur≥5` 先出機率）按預先登記規則 passes**：H2／H3 對 live base 顯著降 Brier（−0.0124／−0.0154），slope 0.98／1.00，第 6–10 場水平偏差在 ±0.03 內且 CI 包 0，dev 否決冇觸發。Coverage ≈ 50% early unit。
4. frozen layer A（v1 係數，原封不動）喺第 6–10 場 transfer 得到；喺第 1–5 場唔得（即使有分鐘因子）。
5. live 最終機率 E 喺賽季初亦比 live base 差（+0.0047～+0.0069，slope 0.46–0.49）。

**講唔到**
- 冇利潤／EV 聲稱；線唔係莊家開價母體；只有 7 個可重現 live 項；只常規賽；population 只係 rotation 球員（上季 ≥40 場、平均 ≥20 分鐘），唔包新秀／交易／長傷復出。
- M3 嘅否決只按協議喺 dev 檢；**H2 上季分鐘桶殘差顯示 B1 高估 3.8pp、B3 低估 3.3pp（CI 排除 0），H3 B3 低估 2.5pp**（描述性，未判決）：frozen layer A 喺賽季初對上季分鐘層級有殘餘系統偏差，forward 要監察。
- M3 只比 `n_cur≥10`（EXP-05）提早約 5 場出機率；賽季頭 5 場仍然 null。
- H2／H3 早過 dev＝跨季穩健性；2026-27 賽季輪休／規則改變可能令分鐘比率唔同（第 1 場比率逐季變動 0.887–0.925）。
- DNP 缺失偏差（未建 virtual units）、`MIN==0` 行只保留於 unit；賽季初缺席率未量。
- **冇聲稱 live 模型有任何改善。**

## 8. Shadow-extension 設計（因 M3 全過先寫；**唔等於建議 production 切換**）
- **範圍**：只喺同季出場 `5 ≤ n_cur ≤ 9`（即第 6–10 場）且上季有 ≥40 場、上季平均 MIN ≥20 嘅球員出 shadow 機率；`n_cur ≤ 4` 維持 null（status 照舊 `insufficient_games`，可加 reason `early_season_minutes_unreliable`）；`n_cur ≥ 10` 走原本 v1 路徑（`ok`）。
- **Extractor 需額外提供（每球員每 stat）**：上季 `Σstat`、上季 `ΣMIN`、上季出場數、上季平均 MIN、同季已賽場數 `n_cur`、同季 `S_cur`（stat 總和）、`M_cur`（分鐘總和），同「最近 10 場（跨賽季，newest-first）」嘅 `prior10_mean_min`（= `min10`）。全部只可用今場日期之前（嚴格 `<`）、`MIN>0` 嘅場次；上季只用 regular season。
- **新 status 值**：`ok_early_season`（`5 ≤ n_cur ≤ 9`）；其餘 `insufficient_games`／`ineligible_prior_season`（上季 <40 場或平均 <20 分鐘）。
- **Artefact**：**新增**版本化檔案（建議 `nba_fit_layer_A_early_v1.json`），內容＝EB 混合 `k`（PTS 5／REB 40／AST 5／3PM 8，EXP-06 dev 擬合）、對 `nba_fit_layer_A_v1.json` 嘅 sha256 引用（沿用其 NB `α` 同重校準 `(a_s,b_s)`，**不另行擬合**）、`n_cur` 適用範圍、來源實驗 EXP-06／07 同 commit、數據 sha256；機率公式＝ `μ = max(0.05, ((n_cur·S_cur/M_cur + k·rate_prior)/(n_cur+k)) × min10)`（`M_cur>0`；`n_cur=0` 唔會出現因 policy 要求 `n_cur≥5`），再經 v1 重校準。**絕不修改 `nba_fit_layer_A_v1.json`。**同樣要 sha-pinned loader、parity 測試（對 harness `M0` 機率 <1e-9）。
- **Forward 證據門檻（升格前）**：(i) 累積第 6–10 場嘅已結算腿（含真實莊家 line 同價格），數量由新協議按目標 MDE 預先計算；(ii) 該段 `p≥0.70`／`≥0.80` 區、整體 slope／reliability 達標，並**按上季分鐘桶（20–25／25–30／≥30）分層**監察（本實驗 H2 顯示 B1 高估、B3 低估）；(iii) 對 live 最終機率 (E) 同 base 嘅配對 bootstrap 優勢；(iv) 真 line 母體上表現；(v) 量度賽季初真實 DNP／scratch 比例；(vi) 可退回 baseline。任何 production 切換係獨立、用戶批准嘅改動。
- **未納入嘅選項**：分鐘因子 `f`（M1／M2）——Brier 增益 ≤0.0009 而且第 1 場仍高估，**唔建議實作**。

## 9. 「what could still be wrong」
- 賽季初真實可得嘅預計分鐘（首發名單、傷病名單、賽前報導）應該遠勝 prior-10 平均，但 game log 睇唔到。
- 分鐘比率逐季變動（第 1 場 0.887／0.922／0.925）：單一 dev 因子唔穩；3 個賽季樣本細。
- 上季「≥40 場且平均 ≥20 分鐘」過濾有倖存者偏差；新秀、交易、長傷復出唔涵蓋。
- 上季季後賽、季前賽、NBA Cup 未納入。
- M3 靠嘅係 A1（c1＋v1 重校準）嘅 S2 層表現；`k`、v1 係數都係單一 dev 窗口擬合。
- 條件 7（±0.03 且 CI 包 0）同 slope 帶 [0.85,1.15] 係預先登記門檻，唔係經驗證嘅決策閾值；H2 上季分鐘桶殘差顯示仍有殘餘偏差。

## 10. 決定
**M3 policy（`n_cur≥5`）按預先登記規則 passes；M1f／M1x／M2f／M2x 全部 not shown。** 賽季頭 4 場 shadow 維持 null；第 6–10 場可以按 §8 設計做 shadow-extension（新版本 artefact，不改 v1），升格需要 forward 證據。**冇利潤、冇 production 聲稱。**
