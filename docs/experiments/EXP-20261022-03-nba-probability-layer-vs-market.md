# EXP-20261022-03 NBA 機率層修正：引擎 vs 莊家價 vs 校準／混合（協議，喺計結果前 commit）

- **日期**：2026-10-22
- **平台**：NBA
- **問題**：live 引擎機率 `p = clamp(L10 命中率 + Σ調整, 5, 98)` 過度自信（實盤預測 ~88%／實際 ~60%）。**假設**：一個只用 dev 擬合、並把莊家價當輸入嘅小型 logistic 層，可以喺 holdout 同時 (i) 嘅 Brier 優於 live 式引擎 E、(ii) calibration slope 入 [0.85, 1.15]、(iii) 高機率區（p ≥ 0.8，即穩膽區）冇系統性偏差、(iv) 唔差過純莊家價 M。**可證偽**：任何一條唔過就唔採納。
- **搜索過嘅舊記錄**：EXP-20261021-02～05（無賠率、near-mean 線；EXP-05 嘅 (A) Poisson/NB＋逐 stat 重校準離線通過，但冇用莊家價）；EXP-20261022-01／02（上季梯級語料 baseline）。呢個實驗係 EXP-05 嘅補充：**第一次用真實莊家梯級同賠率**，並且用莊家價做輸入。
- **改到嘅檔案**：**本記錄階段冇改 production code。** 新增 `docs/experiments/patches/nba_banker_phase1/prob_layer.py`。若通過，production 改動係**下一個獨立改動**，要再過 `model-regression-gate`。
- **語料／切分**：同 EXP-20261022-02（`corpus_2025_26.csv`，剔 04-09；**dev＝首 19 日、gap＝05-07、holdout＝最後 11 日**）。每行＝（球員、stat、milestone 線、賠率）；所有梯級行都計（唔只係穩膽區），另報告穩膽區子集。
- **⚠️ 限制**：只有季後賽／附加賽（Apr–Jun 2026）；冇轉隊；`E` 只可重現 live 調整項入面可由 game log 重現嘅（trend、cov、buffer、sip_n04、sip_n01、playoff_guard），pace、對手防守、spread、USG、主客 PPG、b2b 缺值＝同 live 缺值一樣取 0。**所以 `E` 係「live 式引擎」，唔係 live 完整輸出**；實盤引擎仲有 ML shadow 同 usage guard。regime 由季後賽轉去季初係風險，見 §6。

## 1. Arm（固定，唔准加）
| Arm | 定義 | 擬合 |
|---|---|---|
| **M** | 莊家隱含 `1/price`（含抽水）。**基準，唔係候選** | 無 |
| **E** | live 式引擎：`calc_adjusted_winprob`（live 函數，base＝L10 命中率），`season_phase`＝PLAYOFFS（04-18 起）否則 MID_SEASON；clamp 到 [1,98]（同 live 最後一步） | 無 |
| **B** | 只用 L10：`logit p = a_s + b_s·logit(clip(hit_l10, .05, .95))`，每 stat 一組（8 參數） | dev |
| **C** | 莊家價＋L10：`logit p = a_s + β·logit(clip(M, .02, .98)) + γ·logit(clip(hit_l10, .05, .95))`，a_s 每 stat 一個，β、γ 共用（6 參數） | dev |
| **D** | C＋`buffer_ratio=(avg−line)/avg`、`cov`、`min_avg/48`、`hit_l5`（共 10 參數）。容量測試 | dev |

擬合：無正則 IRLS（sklearn `LogisticRegression(penalty=None)`），**只用 dev**。特徵 clip 範圍固定如上。

## 2. 度量（holdout，只評估一次）
- Brier、log-loss；**ΔBrier vs E** 同 **ΔBrier vs M**（arm − 基準），按比賽日 cluster bootstrap（2,000 次，同一批 resample 日）。
- calibration：`logit(P(y=1)) = a + b·logit(p)` 嘅 slope b、intercept a；穩膽區（p ≥ 0.8）嘅 `mean(p) − mean(y)` 加日 cluster CI。
- 分 stat（PTS／REB／AST／3PM）報 Brier 同 slope（描述性）。
- **洩漏檢查**：(1) 抽取時間早過 19:00 ET（同 EXP-01）；(2) **shuffle test**：喺 dev 內按（日期、stat）置換 `y`，重擬合 C，holdout 嘅 slope 必須 ≈ 0（|b|<0.15）、Brier ≈ 基準率 Brier，否則整個實驗作廢。
- 單元檢查：每行 L10 只用 `GAME_DATE <` 比賽日（build_corpus 構造）。

## 3. 判決（預先登記）
候選（B、C、D）`passes` 需要**全部**：
1. `ΔBrier vs E` 嘅 95% CI 上限 < 0；
2. holdout slope 嘅點估計喺 [0.85, 1.15]；
3. 穩膽區 `mean(p) − mean(y)` 嘅 95% CI 包 0；
4. `ΔBrier vs M` 嘅 95% CI 上限 ≤ +0.001（唔差過市場）。
`passes` 唔等於上線：只代表「值得做 production 候選」。`improves-on-market`（ΔBrier vs M 上限 < 0）另外標記。唔准因結果加 arm、換指標、換窗、換切分。

## 4. 功效
holdout 預計約 6–7k 行（但同一場嘅梯級行高度相關，有效樣本細好多，所以用日 cluster bootstrap）。預期 ΔBrier vs E 嘅 CI 窄（引擎差距 ≈ 0.012）；ΔBrier vs M 嘅 MDE 細，好可能得出「C ≈ M」。

## 5. 狀態
協議已凍結，**未跑**。結果見 §7（跑完先加）。

## 6. 風險（跑之前先寫低）
- regime 轉移：用季後賽擬合，用喺季初。C／D 以莊家價為主，莊家價會自己適應 regime，所以預期比 B 穩；但**要用 2025-10/11 窗做後續驗證**（Phase 3 季初語料）。
- 如果 C ≈ M，意思係 L10 對莊家價冇增量資訊；穩膽 edge 會縮到接近 0，組合選擇主要靠 combo EV 閘，而唔係靠高 L10。
