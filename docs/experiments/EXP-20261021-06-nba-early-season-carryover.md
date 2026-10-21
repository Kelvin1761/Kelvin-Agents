# EXP-20261021-06 NBA 賽季初「上季 carryover」：fit layer A 可唔可以由第 1 場起出有效機率

- **日期**：2026-10-21
- **平台**：NBA
- **假設**：shadow fit layer A（`nba_fit_layer_A_v1`）要求同季 ≥10 場，所以每個球員要到約 11 月初先有機率。**假設：用上季（regular season）rate 做先驗（c0），或者上季 rate 同本季 rate 嘅 empirical-Bayes 混合（c1），再套用凍結嘅 layer-A 重校準，可以喺同季第 1–10 場（「early unit」）出有效而校準嘅機率。** 可證偽：若 c0／c1／A0／A1／X1 冇一個過下面條件，結論就係「layer A 唔可以喺賽季初用 carryover 擴展；賽季初 shadow 維持 null」。
- **搜索過嘅舊記錄**：EXP-20261021-02～05（base、ablation、refit、pre-game population、artefact §11）。冇賽季初／carryover 記錄。EXP-05 嘅 population 只收同季 ≥10 場，所以呢個係新 population。
- **改到嘅檔案／組件**：**冇改 production code。** 新增 `docs/experiments/patches/nba_calibration_exp20261021_02/nba_early.py`（重用 `nba_calib`、`nba_pregame`、`nba_refit`、同 `nba_fit_layer.py` 嘅凍結係數）。
- **狀態**：✅ 已跑一次，結果喺 §7。協議 commit `2e54e7a2`（計結果前）、harness commit `7f62715d`（跑真數據前）。
- **按預先登記規則**：A0、A1、X1 六條條件**全過**（c1 唔過：slope／桶），但 **selection-bias 預檢觸發否決**（上季平均 20–25 同 25–30 分鐘兩桶 `mean(y−p_c)` ＝ −4.2pp／−3.7pp，CI 排除 0，超過 0.03）→ **所有 `passes` 作廢**。
- **決定**：**冇任何 arm 被採納。NEEDS MORE TESTING。** 賽季初 carryover 令機率有用（大勝 live base），但**賽季頭幾場系統性高估**（第 1 場約 −7～−10pp），主因係「賽季初實際分鐘低過 prior-10 平均」；frozen layer A 原封不動套用到賽季初唔可靠，需要先修分鐘假設。**冇聲稱 live 模型有任何改善。**

> 限制同 EXP-02～05：線係「L10（含上季）平均附近 3 個整數」，唔係莊家開價母體 —— **只量機率引擎校準度，冇講利潤／EV**；只有 7 個可重現 live 項；只常規賽。**加多一條：賽季初 population 細、同質（有上季≥40 場、平均≥20 分鐘嘅 rotation 球員），唔代表新秀／交易／長傷復出球員。**

## 1. Population（primary，凍結；賽前可知）
- **Early unit**：球員 `p` 喺目標賽季 `S` 嘅 game `g`（日期 `D`），**同季、日期嚴格 `<D`、`MIN>0` 嘅出場數 `n_cur` 滿足 `0 ≤ n_cur ≤ 9`**（第 1–10 場），並且有可用上季歷史：**上季（`S−1`）regular season `MIN>0` 出場 ≥40 場，且上季平均 MIN ≥20**。上季資料由定義全部早過 `D`（不同賽季），冇同日洩漏可能（仍用單元測試核對）。
- **對 game `g` 自己嘅 `MIN`、有冇上場、有冇早退一概唔過濾**；`MIN==0` 行保留為 y=0（同 EXP-05）。完全冇上場嘅缺席球員冇行（DNP 缺失偏差，同 EXP-05 §1：未建 virtual units，只作限制）。
- 同季 ≥10 場嘅 unit 唔入（屬 EXP-05 population）。
- **線**：同前（`m` ＝下述 L10 平均，3 條最近整數 `N≥1`，`m≥1`）。Stat：PTS／REB／AST／3PM。
- **L10（同 live 一樣混合上季）**：將上季同本季 prior 出場按日期排序，取**最近 10 場**（newest-first）；R0、`prior10_mean_min`、`m` 全部用呢 10 場。
- **切分**（賽季初冇「holdout」，改為跨賽季）：
  - **dev**＝2025-26 early unit、日期 `<2026-01-01`（上季＝2024-25）；
  - **H1（只描述性）**＝2025-26 early unit、日期 `≥2026-02-01`——呢啲係「長傷復出」球員，唔代表開季，行數有限，**唔參與判決**；
  - **H2（判決用）**＝2024-25 全季 early unit（carryover 自 2023-24）；
  - **H3（第二個獨立判決用）**＝2023-24 全季 early unit（carryover 自 2022-23）。
  所有擬合（`k`、X1 重校準）只用 dev。H2、H3 各評估一次。H2、H3 在時間上早於 dev＝跨季穩健性，非前瞻驗證。

## 2. Arm（固定）
令 `rate_prior＝上季 Σstat/ΣMIN`（上季所有 `MIN>0` 場），`min10＝上述 L10 嘅平均 MIN`，`n_cur`、`S_cur`、`M_cur`＝本季 prior 出場數／stat 總和／分鐘總和。Count model 嘅 NB 離散度用 **layer-A 凍結值**（PTS NB `α=0.19714961…`，其餘 Poisson），唔重擬合。

| Arm | 定義 |
|---|---|
| **R0**（reference） | live base：`hit_rate(L10, N)/100`（直接調用 live 函數；早期 unit 嘅 L10 混合上季，同 live extractor 一樣） |
| **c0**（比較） | count model，`μ₀＝max(0.05, rate_prior × min10)` |
| **c1** | EB 混合：`rate₁ ＝ (n_cur·rate_cur + k·rate_prior)/(n_cur + k)`，`rate_cur＝S_cur/M_cur`（`n_cur=0` 時 `rate₁＝rate_prior`），`μ₁＝max(0.05, rate₁×min10)`。`k` **每個 stat 一個**，只喺 dev early unit 按「未重校準 count model 嘅 Brier」揀，網格 `{0,1,2,3,5,8,12,20,40,80}`（單位＝場），tie 取較大 `k` |
| **A0** | **凍結 layer-A 重校準**套用喺 c0（`a_s,b_s` 由 `nba_fit_layer_A_v1.json`，**不重擬合**）。實作＝直接調用 `nba_fit_layer.fit_prob_A(stat,line,上季 Σstat,上季 ΣMIN,min10)`（即 shadow 擴展嘅真實 runtime 呼叫） |
| **A1** | 凍結重校準套用喺 c1 |
| **X1**（探索，唔係凍結 artefact） | 喺 dev early unit 對 c1 重新擬合 per-stat `a_s + b_s·logit(p_c1)` |
| **E**（比較） | live 最終機率（base＋7 個可重現項，live clamp／cap）。本季 prior 出場 `<3` 場嘅主客分裂用 live fallback；`is_b2b` 用本季球隊賽程（本季頭一場＝非 B2B）；`min_avg＝min10` |

- Candidate（要過判決）：**c1、A0、A1、X1**；R0、c0、E 係比較 arm。機率 clip `[0.01,0.99]` 先計分。
- 比較：對 R0 同對 c0（paired GAME_ID cluster bootstrap，2000 次，seed 20261021）；Holm 只作資訊。

## 3. 預先登記判決規則（全部成立先叫 `passes`）
對每個 candidate：
1. **H2** pooled `ΔBrier vs R0` 95% CI 全部 <0；
2. **dev** pooled `ΔBrier vs R0` 點估計 <0；
3. **H3** pooled `ΔBrier vs R0` 95% CI 全部 <0；
4. calibration slope ∈ [0.85,1.15]，**H2 同 H3 兩個都要**（點估計）；
5. H2 pooled 10 桶 reliability：所有 n≥500 嘅桶 `|mean p − mean y| ≤0.05`；
6. **H2** pooled `ΔBrier vs c0` 95% CI 全部 <0（要贏過「只用上季 rate」嘅 count model）。
- **Selection-bias 預檢（否決權）**：喺 dev early unit，按上季平均 MIN 分桶 `20–25`／`25–30`／`≥30`，報 `mean(y − p_c0)` 同 `mean(y − p_c1)` 加 GAME_ID cluster bootstrap 95% CI；若任何桶 `|平均殘差|>0.03` 且 CI 唔包 0 → population 仍有偏差，任何 `passes` 作廢。另報按 `n_cur` 分桶（0／1–4／5–9）作描述。
- 不准用 H2／H3 重擬合、換 `k` 網格、換特徵、換指標或窗口去救候選。
- **「frozen layer A 可否原封不動重用」** 判斷＝A0／A1 嘅條件 4（slope）：若 A0／A1 slope 喺 H2 同 H3 都入 [0.85,1.15] 就視為 transfer 成功；若只有 X1 過，就要獨立 early-season artefact。呢個結論單獨寫明。

## 4. 其他報告（描述性）
- 每個 arm：Brier、log-loss、slope／intercept、calibration-in-the-large、10 桶 reliability；逐 stat；逐 `n_cur` 層（0／1–4／5–9）嘅 Brier 同 slope（只描述，睇 carryover 幾時追貼 same-season）。
- 選注視角：`p≥0.70`、`p≥0.80`，R0、c0、c1、A0、A1、X1、E：n、佔比、平均 p、實際命中率（H2、H3、dev）。
- 洩漏檢查：point-in-time 單元測試（每個 unit 用到嘅每一場日期 `<D`，上季場次全部屬 `S−1`，同日場次不入）；shuffle test（dev：每 stat 置換 `y`，重擬合 X1；PASS＝所有 per-stat 斜率 `|b|<0.10`）。
- Parity：A0 同 harness 內自己算嘅 (c0＋凍結重校準) 差 <1e-9（證明 artefact 呼叫等價）。
- 若有 candidate `passes`：寫 shadow-extension 設計（extractor 額外輸入、status 值、forward 證據）；若冇：直接寫「冇任何 arm 被採納」。
- **「what could still be wrong」** 一節。

## 5. 數據
- raw：`nba_api LeagueGameLog`（regular season）2022-23、2023-24、2024-25、2025-26。新抓 2023-24、2022-23：
  - 2023-24：26,401 行、2023-10-24→2024-04-14、1,230 場、重複 0、MIN 缺失 0、MIN==0 118、每場非 2 隊 0；sha256 `6e88b0b4766cd8ac3f83e1175d3920bc276d4fea25f578612ae46168d844291b`
  - 2022-23：25,894 行、2022-10-18→2023-04-09、1,230 場、重複 0、MIN 缺失 0、MIN==0 76、每場非 2 隊 0；sha256 `c705ab14e7729f73f6816428f46eb1e353e19f1aa4402a925ec7e8fcaddc6f9e`
  - 2024-25／2025-26 同 EXP-02（sha256 `320455e0…`／`43523d96…`）。

## 6. 重跑

環境：Python 3.9.6、numpy 2.0.2、pandas 2.3.3、scipy 1.13.1（只供 harness 其他模組；`nba_fit_layer` 本身純標準庫）；`PYTHONDONTWRITEBYTECODE=1`。Harness commit `7f62715d807066969350a9f51104e294408bcc4c`（`nba_early.py`、`test_early.py`；全部 15 個 harness 測試 pass，另 `nba_fit_layer` 11 個測試 pass）。Frozen artefact：`nba_fit_layer_A_v1.json` sha256 `7e74022c…`（commit `ee517011`，唯讀載入）。
Scratchpad：`/private/tmp/claude-501/-Users-imac-Antigravity-repo--claude-worktrees-nba-calibration-exp-56dc4c/1fa02346-3347-461b-80cf-3be02bd426e1/scratchpad/`；raw 見 §5。
- `out6/rows.csv` sha256 `a96b350ab74ffc440bd16fcd8376a6a9fa1a6ba5e097343dcb2cd909ce13c690`（71,259 行：2025-26 23,760／2024-25 23,796／2023-24 23,703）
- `out6/results6.json` sha256 `43e492ccf648320fdac353040a391a0742af608d87a6449b830d1fbb00ac159d`
```bash
export PYTHONDONTWRITEBYTECODE=1
H=docs/experiments/patches/nba_calibration_exp20261021_02; S=<scratchpad>
python3 -W ignore -m unittest discover -s $H -p "test_*.py"
python3 -W ignore $H/nba_early.py build --raw $S/raw --out $S/out6
python3 -W ignore $H/nba_early.py run   --out $S/out6          # 只跑一次
```
（另有事後描述性診斷 `scratchpad/diag6.py`：按 `n_cur`／上季分鐘分桶睇各 arm 殘差同 `min_g/min10`，**唔入判決**。）

## 7. 結果

### 7.1 Population 同擬合
| 窗 | 行數 | unit（球員場次） | 球員數 |
|---|---|---|---|
| dev（2025-26，<2026-01-01） | 22,902 | 2,076 | 211 |
| H1（2025-26，≥2026-02-01；長傷復出，**只描述，唔入判決**） | 681 | 57 | 8 |
| H2（2024-25，carryover 自 2023-24） | 23,796 | 2,157 | 217 |
| H3（2023-24，carryover 自 2022-23） | 23,703 | 2,200 | 220 |
H1 唔係空但只有 57 個 unit、8 個球員（全部係開季後先復出嘅球員），所以改用 H2、H3 兩個跨季窗做判決（均早於 dev，係跨季穩健性，唔係前瞻）。
- **dev 擬合**：`k`（EB 混合，單位＝場）PTS 5、REB 40、AST 5、3PM 8（REB 揀到近乎只用上季 rate）；X1 重校準 `(a,b)`：PTS (0.060, 0.933)、REB (−0.269, 0.853)、AST (−0.073, 0.810)、3PM (−0.092, 0.887)；frozen layer-A `(a,b)`：PTS (0.053, 0.807)、REB (−0.040, 0.875)、AST (−0.058, 0.864)、3PM (−0.113, 0.889)。
- **Parity**：A0 經 artefact 呼叫（`fit_prob_A(stat,line,上季總和,上季分鐘,min10)`）同 harness 公式 (c0＋凍結重校準) 最大差 <1e-9（`run` 內 assert 通過）。
- **洩漏檢查**：shuffle test（dev，置換 `y` 後重擬合 X1）per-stat 斜率 0.034／0.023／0.023／0.022（<0.10）→ PASS；point-in-time 單元測試 4 個（只收第 1–10 場；L10 跨季；資格規則；feature 唔隨 outcome 改變；blend 極限）pass，運行時 assert 日期 `<D`。

### 7.2 Selection-bias 預檢（否決權）——**觸發**
dev early unit，`mean(y − p)`（正＝低估、負＝高估），95% CI（GAME_ID cluster bootstrap）：
| 上季平均 MIN 桶 | n | c0 | c1 |
|---|---|---|---|
| 20–25 | 6,303 | **−0.042** [−0.065, −0.021] | **−0.043** [−0.066, −0.022] |
| 25–30 | 6,717 | **−0.037** [−0.059, −0.016] | **−0.038** [−0.059, −0.017] |
| ≥30 | 9,882 | +0.007 [−0.013, +0.025] | +0.003 [−0.016, +0.020] |
按 `n_cur`（描述）：第 1 場（n=2,349）**−0.076** [−0.110, −0.044]；第 2–5 場 −0.034／−0.032（CI 排除 0）；第 6–10 場 +0.004／−0.002（CI 包 0）。
**兩個上季分鐘桶 |殘差|>0.03 且 CI 排除 0 → population／count model 仍然有偏差 → 任何 `passes` 作廢。** 呢個唔係「選擇偏差」式偽影（冇用賽後過濾）：係**真實嘅賽季初系統性高估**。

### 7.3 判決（六條，預先登記；**但被 §7.2 否決**）
| Arm | ①H2 CI<0 vs R0 | ②dev<0 | ③H3 CI<0 | ④slope H2／H3 | ⑤H2 冇壞桶 | ⑥H2 贏 c0 | 條件 | **最終** |
|---|---|---|---|---|---|---|---|---|
| c1（EB 混合，未校準） | ✅ | ✅ | ✅ | ❌ 0.833／✅ 0.872 | ❌（.75／.84／.93 三桶高估 0.06／0.05／0.06） | ✅ | 唔過 | not shown |
| **A0**（凍結重校準＋c0） | ✅ | ✅ | ✅ | ✅ 0.851／✅ 0.898 | ✅ | ✅ | 六條全過 | **否決 → 不可用** |
| **A1**（凍結重校準＋c1） | ✅ | ✅ | ✅ | ✅ 0.964／✅ 1.007 | ✅ | ✅ | 六條全過 | **否決 → 不可用** |
| **X1**（探索，dev 重擬合） | ✅ | ✅ | ✅ | ✅ 0.969／✅ 1.022 | ✅ | ✅ | 六條全過 | **否決 → 不可用** |

pooled ΔBrier vs R0（括號＝vs c0；95% CI）：
| Arm | dev | H2 | H3 | H2 slope [CI] | H3 slope [CI] |
|---|---|---|---|---|---|
| c0 | −0.0101 | −0.0113 [−0.0143, −0.0085] | −0.0146 [−0.0175, −0.0116] | 0.735 [0.70, 0.77] | 0.780 [0.75, 0.82] |
| c1 | −0.0146 (−0.0045) | −0.0149 [−0.0172, −0.0125] (−0.0036 [−0.0049, −0.0022]) | −0.0176 [−0.0200, −0.0152] (−0.0030) | 0.833 [0.80, 0.87] | 0.872 [0.83, 0.91] |
| A0 | −0.0122 (−0.0021) | −0.0130 [−0.0157, −0.0103] (−0.0017 [−0.0021, −0.0013]) | −0.0156 [−0.0183, −0.0128] (−0.0010) | 0.851 [0.81, 0.89] | 0.898 [0.86, 0.94] |
| A1 | −0.0158 (−0.0057) | −0.0158 [−0.0180, −0.0134] (−0.0045 [−0.0059, −0.0031]) | −0.0179 [−0.0202, −0.0156] (−0.0033) | 0.964 [0.92, 1.00] | 1.007 [0.97, 1.05] |
| X1 | −0.0166 (−0.0065) | −0.0153 [−0.0176, −0.0128] (−0.0040 [−0.0054, −0.0025]) | −0.0175 [−0.0200, −0.0149] (−0.0029) | 0.969 [0.93, 1.01] | 1.022 [0.98, 1.07] |
| E（live 最終） | +0.0036 | **+0.0047** [+0.0025, +0.0068] | **+0.0051** [+0.0029, +0.0072] | **0.464** | **0.458** |
Brier（H2）：R0 0.2360、c0 0.2248、c1 0.2211、A0 0.2230、A1 0.2203、X1 0.2208、E 0.2407。Holm（6 個比較 vs R0）：全部 p=0.0005 地板（H2、H3），結論不變。

**Frozen layer A 是否原封不動 transfer？** 按 slope（條件 4）係：A0 pooled slope 0.85／0.90（H2／H3，貼近下限），A1 0.96／1.01；逐 `n_cur` 層 A0 slope：第 1 場 1.00／1.02、第 2–5 場 0.87／0.93、第 6–10 場 0.82／0.85。**但 level 唔 transfer**：citl（mean p − mean y）H2 A0 +0.014、A1 +0.014（X1 −0.001，因為 X1 重新擬合咗截距）；per-stat 3PM／REB 嘅 A0 citl 接近 0，PTS／AST +0.025／+0.032。即係 slope 轉移到，截距偏差（高估）轉移唔到；要靠 X1 式重校準先清到 pooled citl，但 X1 嘅分桶殘差仍然（§7.4）未清。

### 7.4 賽季初高估嘅診斷（事後描述性，唔入判決，唔用嚟擬合）
`mean(y − p)`：
| 層 | n（dev／H2／H3） | R0 | c0 | A0 | A1 | X1 |
|---|---|---|---|---|---|---|
| 第 1 場 | 2,349／2,403／2,376 | −0.100／−0.105／−0.072 | −0.076／−0.091／−0.043 | −0.070／−0.084／−0.038 | 同 A0 | −0.055／−0.069／−0.022 |
| 第 2–5 場 | 9,267／9,573／9,534 | −0.050／−0.049／−0.049 | −0.034／−0.036／−0.023 | −0.027／−0.028／−0.017 | −0.026／−0.025／−0.014 | −0.011／−0.011／+0.001 |
| 第 6–10 場 | 11,286／11,820／11,793 | −0.014／−0.011／−0.019 | +0.004／+0.003／+0.003 | +0.010／+0.011／+0.010 | +0.005／+0.010／+0.010 | +0.020／+0.024／+0.025 |
- **實際分鐘 / prior-10 平均 MIN**（unit 平均）：第 1 場 0.923／0.893／0.929；第 2–5 場 0.943／0.956／0.964；第 6–10 場 0.989／0.993／1.003（三個賽季一致）。即係**賽季初球員實際上場分鐘比 prior-10（上季末 10 場）低 4–11%**，所以用 prior-10 平均 MIN 做 `μ` 嘅分鐘假設令全部 stat 高估；呢個到第 6 場先消失。上季分鐘 <30 嘅球員（20–30 分鐘 rotation）高估更大（−4pp 級），≥30 分鐘嘅冇高估。
- 即係 carryover 嘅 rate 部分有用（c0／c1 贏 R0），問題係**分鐘投影**。呢個係假設，要新實驗預先登記先可以處理（見 §9）。
- R0（live base）喺賽季初亦系統性高估 −5pp（第 2–5 場）至 −10pp（第 1 場）。

### 7.5 選注相關視角（`p≥0.70`／`p≥0.80`；描述性，唔係利潤）
| 窗 | arm | ≥0.70：n（佔比）／平均 p／實際命中 | ≥0.80：n（佔比）／平均 p／實際命中 |
|---|---|---|---|
| H2 | R0 | 6,376（26.8%）／0.783／**0.682** | 3,442（14.5%）／0.854／**0.741** |
| H2 | c0 | 5,285（22.2%）／0.809／0.738 | 2,699（11.3%）／0.866／0.800 |
| H2 | c1 | 4,944（20.8%）／0.806／0.749 | 2,495（10.5%）／0.862／0.810 |
| H2 | A0 | 4,297（18.1%）／0.791／0.758 | 1,736（7.3%）／0.857／0.828 |
| H2 | A1 | 3,996（16.8%）／0.788／0.776 | 1,534（6.4%）／0.852／0.842 |
| H2 | X1 | 3,401（14.3%）／0.785／0.785 | 1,239（5.2%）／0.850／0.841 |
| H2 | E（live 最終） | 4,647（19.5%）／0.822／**0.719** | 2,400（10.1%）／0.897／**0.765** |
H3：R0 ≥0.70 0.782／0.680、≥0.80 0.852／0.736；c1 0.803／0.760、0.862／0.834；A1 0.788／0.789、0.850／0.856；X1 0.783／0.800、0.845／0.867；E 0.821／0.715、0.900／0.752。dev 同方向。
**讀法**：賽季初 live 最終機率 (E) 喺高機率區高估 10–14pp（≥0.80：預測 0.897 對實際 0.765）；R0 高估 9–11pp；A1／X1 兩個區基本校準（A1 H2 ≥0.70 差 −0.012；X1 ≈0），但達標腿數目少咗（26.8%→14–17%）。

## 8. 呢個實驗講到乜、講唔到乜
**講到**
1. **按預先登記規則，A0／A1／X1 六條全過，但 selection-bias 預檢否決** —— 因為 count model 喺賽季頭幾場（尤其第 1 場）同 20–30 分鐘 rotation 球員系統性高估。所以**冇任何 arm 被採納**；「frozen layer A 可以由第 1 場起出有效機率」**未被證實**。
2. **Carryover 對 rate 有真價值**：c0／c1（上季 rate）喺 H2、H3 對 live base R0 大幅降 Brier（−0.011～−0.018），EB 混合 c1 再贏 c0（H2 −0.0036；REB 近乎只用上季，3PM 喺 H3 冇增益）。呢個結論喺三個賽季一致。
3. Frozen layer A 嘅**斜率**可以 transfer 到賽季初（A0 slope 0.85–0.90，A1 0.96–1.01，pooled），但**水平**（高估 1–2pp，第 1 場 7–8pp）唔 transfer。X1（dev 重擬合）清到 pooled citl，但第 1 場仍高估 2–7pp、第 6–10 場低估 2–2.5pp（過度校正），所以早期 artefact 唔係單靠重擬合截距就行。
4. live 最終機率 (E) 喺賽季初同賽季中一樣比 base 更差（H2 +0.0047，slope 0.46）。

**講唔到**
- 冇用賠率，**冇利潤／EV 聲稱**；線係「L10（含上季）平均附近 3 個整數」；只有 7 個可重現 live 項；只常規賽。
- Population 只係「上季≥40 場且平均≥20 分鐘」嘅 rotation 球員（dev 211 人、H2 217、H3 220）：**唔包新秀、交易後角色改變、長傷復出球員**（H1 嘅 8 個復出球員 57 個 unit 太少，不可判斷）。
- 賽季初高估嘅「分鐘解釋」係事後描述性（§7.4），未有預先登記檢定。
- H2／H3 早過 dev，所以係跨季穩健性；2026-27 賽季如規則／節奏／輪休政策改變，結果可能唔同。
- DNP 缺失偏差（未建 virtual units）：賽季初缺席率未量。
- **冇聲稱 live 模型有任何改善。**

## 9. 零結果教咗乜／建議下一個實驗
- **唔建議**用 carryover 擴展 `nba_fit_layer_A_v1` 去賽季頭 10 場出 shadow 機率（會系統性高估，第 1 場約 7–8pp）。賽季初 shadow 暫維持 null（status 照舊 `insufficient_games`）。
- **EXP-07（新協議）：賽季初分鐘校正。** 假設：高估主要來自 `prior-10 平均 MIN` 過高。預先登記一個只由 dev 擬合嘅分鐘因子 `f(n_cur)`（例如 `n_cur=0, 1–4, 5–9` 三個乘數，或按上季分鐘分層），`μ＝rate×(min10×f)`，其餘沿用本實驗 population／判決（H2、H3 跨季）；同時比較「只喺 `n_cur≥5` 先出 shadow」呢個更簡單嘅 policy（本實驗描述性顯示該層 pooled 殘差 ≈ +0.01）。若通過，才寫 shadow-extension 設計：extractor 額外提供上季 `Σstat`、`ΣMIN`、上季平均 MIN、本季 `n_cur`／`S_cur`／`M_cur`，status 值 `ok_early_season_carryover`（區別於 `ok`），並累積 forward 已結算腿作證據。
- **本實驗所用 runtime 輸入（供日後參考，現時唔實作）**：`fit_prob_A(stat, line, 上季 stat 總和, 上季 MIN 總和, min10)`（A0）；c1 另需本季 `S_cur`、`M_cur`、`n_cur` 同 `k`（PTS 5／REB 40／AST 5／3PM 8）。

## 10. 「what could still be wrong」
- 上季資料「有 ≥40 場且平均 ≥20 分鐘」過濾本身可能引入倖存者偏差（上季未打夠嘅球員被剔走）。
- 輪休／負荷管理政策逐季改變；賽季初首發名單、傷病名單賽前已知但 game log 睇唔到；實際可得嘅預計分鐘（賽前報導）應該比 prior-10 平均準。
- 交易／換隊後 role 改變：L10 混合上季（另一隊）嘅場次。
- 季前賽、NBA Cup、play-in 等冇納入；上季季後賽表現亦冇納入（只常規賽）。
- dev 得 ~3 周（2025-26 賽季頭 10 場），`k`／X1 係數只係單一窗口擬合。
- 條件 4 嘅 slope 帶 [0.85,1.15] 係預先登記門檻，A0 pooled H2 0.851 只係剛剛過線。

## 11. 決定
**冇任何 arm 被採納（A0／A1／X1 六條全過但被預檢否決；c1 唔過）。NEEDS MORE TESTING。** 確認咗嘅嘢：carryover 令 count model 贏 live base；frozen layer A 嘅 slope 可轉移但水平唔可靠；賽季初分鐘假設係問題所在。**冇利潤、冇 production 聲稱。**
