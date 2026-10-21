# EXP-20261021-06 NBA 賽季初「上季 carryover」：fit layer A 可唔可以由第 1 場起出有效機率

- **日期**：2026-10-21
- **平台**：NBA
- **假設**：shadow fit layer A（`nba_fit_layer_A_v1`）要求同季 ≥10 場，所以每個球員要到約 11 月初先有機率。**假設：用上季（regular season）rate 做先驗（c0），或者上季 rate 同本季 rate 嘅 empirical-Bayes 混合（c1），再套用凍結嘅 layer-A 重校準，可以喺同季第 1–10 場（「early unit」）出有效而校準嘅機率。** 可證偽：若 c0／c1／A0／A1／X1 冇一個過下面條件，結論就係「layer A 唔可以喺賽季初用 carryover 擴展；賽季初 shadow 維持 null」。
- **搜索過嘅舊記錄**：EXP-20261021-02～05（base、ablation、refit、pre-game population、artefact §11）。冇賽季初／carryover 記錄。EXP-05 嘅 population 只收同季 ≥10 場，所以呢個係新 population。
- **改到嘅檔案／組件**：**冇改 production code。** 新增 `docs/experiments/patches/nba_calibration_exp20261021_02/nba_early.py`（重用 `nba_calib`、`nba_pregame`、`nba_refit`、同 `nba_fit_layer.py` 嘅凍結係數）。
- **狀態**：🔵 協議已寫（未跑結果）。

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
（跑完後填）

## 7. 結果
（跑完後填）
