# EXP-20261021-04 NBA 調整層 REFIT（用擬合代替逐項移除）

- **日期**：2026-10-21
- **平台**：NBA
- **假設**：EXP-02 冇候選過到 calibration slope ∈ [0.85,1.15]；EXP-03 發現 live 7 個可重現調整項大多帶負偏、單獨移走只係治標。**假設：一個細嘅、只喺 dev 擬合嘅 logistic 層（喺 Poisson/NB 底上面）可以同時 (i) 令 H1 Brier 顯著贏 live base (a)、(ii) slope 入 [0.85,1.15]、(iii) 高機率區冇系統性偏差。** 可證偽：若冇候選過下面嘅 `passes` 規則，結論就係「呢個 population／特徵集唔足以修好校準」。
- **搜索過嘅舊記錄**：EXP-20261021-02（base 同候選 (c)(f)、slope 失敗）、EXP-20261021-03（逐項效應、Σadj 負偏機制）。AU 嘅 `au-matrix-refit-consensus-not-argmax` 係方法論來源（full re-fit 先 work，逐對編輯唔 work）。冇其他 NBA refit 記錄。
- **改到嘅檔案／組件**：**冇改 production code。** 新增 `docs/experiments/patches/nba_calibration_exp20261021_02/nba_refit.py`（重用 EXP-02／03 harness 同 `out3/rows.csv`）。
- **狀態**：🔵 協議已寫（未跑結果）。

> ⚠️ 限制同 EXP-02／03，**先睇**：(1) 線係「L10 平均附近 3 個整數」，唔係莊家開價母體 —— **只量機率引擎校準度，完全冇講利潤／EV**；(2) 只有 7 個可重現 live 項（spread、對手 pace／防守、USG／傷兵、ML 都冇）；(3) 只常規賽，2025-26＋2024-25；(4) 擬合模型**冇 live 嘅 −20 cap 同 5–98 clamp**（只喺計分時 clip 到 [0.01,0.99]，同所有 arm 一樣）。

## 1. 數據同切分（同 EXP-02／03，凍結）
- Population：primary（MIN≥15 賽後過濾、≥10 prior、3 條最近 `m` 嘅整數線、`m≥1`，嚴格 `<` 日期）。Feature 已經 point-in-time（單元測試 5/5）。輸入：EXP-03 嘅 `out3/rows.csv`（366,972 行，sha256 `dc5cb311…`，含 `a`、`hit_sea`、`mu`、`t_*`）。
- **dev**：2025-26 `<2026-01-01`；**gap**：1 月；**H1**：2025-26 `≥2026-02-01`（只評估一次）；**H2**：2024-25 整季（只評估一次，用 dev 擬合嘅係數）。所有擬合、標準化、λ 揀選只用 dev。

## 2. 預先登記嘅 arm（5 個，固定，唔准加）
先由 dev 得出 EXP-02 嘅 tuned 參數（同 EXP-02 一樣嘅程序，結果應同 EXP-02 一樣：`w`＝PTS .40/REB .30/AST .30/3PM .15；NB `α(PTS)`≈0.205），然後：

| Arm | 定義 |
|---|---|
| **(a) REFERENCE** | live base `hit_L10`（未 clamp），同 EXP-02／03 |
| **(c)** | EXP-02 嘅 Poisson/NB（`μ＝season rate×prior-10 平均 MIN`）；比較 arm，唔擬合 |
| **(A)** | (c) 嘅 logistic recalibration，**每 stat 一組** `a_s + b_s·logit(p_c)`（8 參數），dev 擬合 |
| **(B)** | **Pooled logistic（4 stat 共用係數＋3 個 stat dummy，PTS 做基準）**，特徵＝ `[logit(p_c), logit(p_b), t_trend, t_cov, t_buffer, t_sip_n04, t_sip_n01, t_b2b, t_home_away]`，全部用 dev 平均／sd 標準化（dummy 同截距唔標準化），**無正則化（λ=0）**。`p_b`＝(b) 收縮（EXP-02，dev 擬合 `w`）。 |
| **(C)** | 同 (B) 特徵，**L2 正則化**（只罰 9 個標準化特徵嘅係數，唔罰截距同 dummy）；目標＝ NLL_sum + ½λ‖β‖²。 |

- (B) 選 pooled＋dummy（而唔係 per-stat）原因：dev 得 ~53k 行，4 stat 擬合 4×13 參數、每 stat 嘅 3 條線高度相關（同一 unit），pooled 較穩；stat 差異只由 dummy 同 (A)（per-stat）覆蓋。呢個決定喺睇結果前凍結，唔再轉 per-stat。
- **(C) 嘅 λ 揀選（只喺 dev 內部時間切分）**：train＝dev 內日期 `<2025-12-01`，validation＝`2025-12-01…2025-12-31`；λ ∈ **{0, 10, 100, 1000, 10000, 100000}**，按 validation Brier 最低揀（tie 取較大 λ）；揀完用**全 dev** 重新擬合。H1／H2 永不參與。
- 擬合方法：加權 IRLS／Newton（自寫，numpy），收斂 `|Δβ|<1e-8`。
- 5 個 arm、4 個對 (a) 嘅比較；Holm 只作額外資訊。

## 3. 評估
- 窗口：dev（in-sample，只作符號檢查）、H1、H2（各一次）；pooled、逐 stat；slope／intercept（`logit P(y)=a+b·logit p`）、Brier、log-loss、10 桶 reliability。
- 配對 bootstrap：cluster＝GAME_ID，**2000 次，seed 20261021**；`ΔBrier`、`Δlog-loss` vs (a)，另報 vs (c)（描述性，睇「擬合層有冇贏過 base」）。Slope CI：bootstrap 300 次（H1／H2 pooled）。
- **係數 CI**：對 (A)(B)(C)（(C) 用已揀好嘅 λ，唔重揀）喺 dev 用 GAME_ID cluster bootstrap **300 次**重擬合，報標準化係數、原始單位係數（每 live 1pp）、95% CI，同「**保留比例**＝ 原始係數／0.04」（因 p≈0.5 時 1pp＝0.04 logit；1.0＝同 live 設計一樣大，0＝冇用，負＝方向反）。（描述性，用嚟答「fit instead of remove」。）
- **選注相關視角（描述性，唔係利潤）**：H1／H2 pooled，每 arm 喺 `p ≥ 0.70` 區：n、佔全部行嘅比例、平均 p、實際命中率、差；同 (a) 比較區內 n。
- 洩漏檢查：(i) point-in-time 單元測試（重跑 5/5）；(ii) **shuffle test（dev）**：每 stat 內全局置換 `y`（固定 seed），重新擬合 (B)（λ=0）；PASS 條件：所有標準化特徵係數 `|β|<0.05` 且擬合後 in-sample Brier 比「每 stat 常數」改善 `<0.0005`；否則報 LEAK。
- **S1 敏感度（唔參與判決）**：prior-10 平均 MIN≥20 population，用 **primary dev 擬合嘅同一組係數**（唔重擬合）評 dev／H1／H2 pooled。

## 4. 預先登記判決規則（唔准事後改）
一個候選（(A)(B)(C)）只有**全部**滿足先叫 **`passes`**，否則 **`not shown`**：
1. H1 pooled `ΔBrier vs (a)` 95% CI **全部 < 0**；
2. dev pooled `ΔBrier vs (a)` 點估計 **< 0**；
3. H2 pooled `ΔBrier vs (a)` 95% CI **全部 < 0**；
4. H1 pooled calibration slope ∈ **[0.85, 1.15]**（點估計）；
5. H1 pooled 10 桶 reliability：**所有 n≥500 嘅桶 `|mean p − mean y| ≤ 0.05`**。
- 不准用 H1／H2 重擬合、換特徵、換 λ 網格、換指標或窗口去救候選；想換設計就開新實驗。
- 就算 `passes`：**唔建議切換 production**；只寫 §「shadow deployment design」（只作 shadow 欄位，預設關）。若全部 `not shown`，亦照記，唔掩飾。
- 同時報 (c) 本身按 1–5 條嘅結果（它係未擬合嘅比較 arm）。

## 5. 重跑
（跑完後填）

## 6. 結果
（跑完後填）
