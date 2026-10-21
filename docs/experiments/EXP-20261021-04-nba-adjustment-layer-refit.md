# EXP-20261021-04 NBA 調整層 REFIT（用擬合代替逐項移除）

- **日期**：2026-10-21
- **平台**：NBA
- **假設**：EXP-02 冇候選過到 calibration slope ∈ [0.85,1.15]；EXP-03 發現 live 7 個可重現調整項大多帶負偏、單獨移走只係治標。**假設：一個細嘅、只喺 dev 擬合嘅 logistic 層（喺 Poisson/NB 底上面）可以同時 (i) 令 H1 Brier 顯著贏 live base (a)、(ii) slope 入 [0.85,1.15]、(iii) 高機率區冇系統性偏差。** 可證偽：若冇候選過下面嘅 `passes` 規則，結論就係「呢個 population／特徵集唔足以修好校準」。
- **搜索過嘅舊記錄**：EXP-20261021-02（base 同候選 (c)(f)、slope 失敗）、EXP-20261021-03（逐項效應、Σadj 負偏機制）。AU 嘅 `au-matrix-refit-consensus-not-argmax` 係方法論來源（full re-fit 先 work，逐對編輯唔 work）。冇其他 NBA refit 記錄。
- **改到嘅檔案／組件**：**冇改 production code。** 新增 `docs/experiments/patches/nba_calibration_exp20261021_02/nba_refit.py`（重用 EXP-02／03 harness 同 `out3/rows.csv`）。
- **狀態**：✅ 已跑一次，結果喺 §6。協議 commit `c7109fcb`（計結果前）、harness commit `db381001`（跑真數據前）。
- **按預先登記規則嘅字面判決**：(B)、(C) **passes**；(A)、(c) **not shown**。
- **⚠️ 但呢個「passes」唔可以當證據**：增益主要來自 primary population 嘅**賽後 `MIN_g≥15` 選擇偏差**（§6.5）。喺賽前可知嘅 S1 population，擬合層對 (c) 嘅增益幾乎消失（H2 −0.0002，CI 跨 0）。**決定：NEEDS MORE TESTING；唔建議 shadow 上線；下一步係用賽前可知 population 重做（新協議）。**

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

環境：Python 3.9.6、numpy 2.0.2、pandas 2.3.3、scipy 1.13.1；`PYTHONDONTWRITEBYTECODE=1`。Harness commit `db3810011514ea60c7bfd002f59cec5c94bd8cad`（`nba_refit.py`、`test_refit.py`；8/8 單元測試 pass，包括 point-in-time 5 個）。
Scratchpad：`/private/tmp/claude-501/-Users-imac-Antigravity-repo--claude-worktrees-nba-calibration-exp-56dc4c/1fa02346-3347-461b-80cf-3be02bd426e1/scratchpad/`
- 輸入 `out3/rows.csv` sha256 `dc5cb311a114869e4c51de628dffd4b61086252ec5402f9c9e06226aaacfcbb9`（EXP-03）
- 輸出 `out4/results4.json` sha256 `16dc6934207dbe1c90e261c698f67b056301335cb027ca8a9c22b67e5c95d9fa`
```bash
export PYTHONDONTWRITEBYTECODE=1
H=docs/experiments/patches/nba_calibration_exp20261021_02; S=<scratchpad>
python3 -W ignore -m unittest discover -s $H -p "test_*.py"       # 8/8 OK
python3 -W ignore $H/nba_refit.py run --rows $S/out3/rows.csv --out $S/out4    # 只跑一次
```
另有一個**事後描述性診斷**（唔入判決，唔用嚟調任何嘢）：`scratchpad/diag.py`（按 `t_sip_n01` 水平睇 dev 嘅 `mean(y − p_c)`、zone≥0.70、reliability 摘錄）。

## 6. 結果

### 6.1 擬合細節（只用 dev）
- Tuned（同 EXP-02）：`w`＝PTS .40／REB .30／AST .30／3PM .15；NB `α(PTS)`＝0.205。
- **(C) 嘅 λ**：dev 內部切分 train＝Nov（21,111 行）、validation＝Dec（32,211 行）；validation Brier：λ=0 **0.21650**、10 0.21651、100 0.21657、1,000 0.21742、10,000 0.22360、100,000 0.24005。**揀 λ=0 → (C) 同 (B) 係同一個模型**（正則化冇幫助；唔係實作錯，結果逐位一樣）。
- Shuffle test（dev，標籤置換後重擬合 (B)）：最大 `|標準化係數|`＝0.035（<0.05），in-sample Brier 相對每 stat 常數改善 3.4e-5（<5e-4）→ **PASS（冇發現洩漏）**。⚠️ 但呢個測試**捉唔到 §6.5 嘅選擇偏差**（標籤冇洩漏，係 population 定義本身有偏）。

### 6.2 判決（primary，預先登記 5 條）
| Arm | 1 H1 CI<0 | 2 dev<0 | 3 H2 CI<0 | 4 H1 slope∈[.85,1.15] | 5 冇桶 \|p−y\|>.05（n≥500） | **判決** |
|---|---|---|---|---|---|---|
| (c) Poisson/NB（比較，未擬合） | ✅ | ✅ | ✅ | ❌ 0.769 | ❌（0–.5 桶低估 0.05–0.11） | not shown |
| (A) per-stat 重校準 | ✅ | ✅ | ✅ | ✅ 0.904 | ❌（0–.3 桶低估：預測 .07／.16／.26 對實際 .165／.214／.309） | **not shown** |
| (B) pooled logistic＋7 項（λ=0） | ✅ | ✅ | ✅ | ✅ **0.962** [0.94, 0.99] | ✅ | **passes** |
| (C) 同 (B)＋L2（揀到 λ=0） | ✅ | ✅ | ✅ | ✅ 0.962 | ✅ | **passes**（＝(B)） |

H1 pooled 數字（ΔBrier vs (a)；括號＝對 (c)）：(A) −0.0167 [−0.0179, −0.0154]（−0.0040）；(B)＝(C) **−0.0209** [−0.0223, −0.0194]（對 (c) **−0.0082** [−0.0094, −0.0072]）。H2：(A) −0.0160、(B)＝(C) −0.0192 [−0.0202, −0.0182]，slope 0.962。Brier：(a) 0.2348、(c) 0.2222、(A) 0.2182、(B) 0.2139（H1）。
- Holm（4 個比較）：全部 p＝0.0005 地板 → 調整後 0.002，結論唔變。
- 逐 stat（H1，ΔBrier vs (a)，(B)）：PTS −0.0275（slope 1.02）、REB −0.0233（0.98）、AST −0.0152（0.93）、3PM −0.0145（0.99）；PTS 嘅 (a) slope 只有 0.16，(B) 變 1.02，係最大改善。
- H1 reliability，(B) 所有桶 `|mean p−mean y|` ≤0.02（n≥500），只有最低桶（n=291）預測 .075 對實際 .144。（(a) 最高桶 .92 對 .82。）

### 6.3 係數（(B)＝(C)，dev 全樣本；cluster bootstrap 300 次 95% CI）
標準化係數（單位：logit／1 sd）、原始係數（logit／live 1pp）、**保留比例**＝原始／0.04（1.0＝同 live 設計一樣大；負＝方向同 live 相反）：
| 特徵 | 標準化 β [CI] | 原始 β／pp | **保留比例 [CI]** |
|---|---|---|---|
| logit(p_c) | 0.665 [0.589, 0.726] | 0.724 | — |
| logit(p_b) | 0.089 [0.038, 0.143] | 0.088 | — |
| t_trend | +0.028 [−0.000, +0.058] | +0.006 | 0.15 [0.00, 0.32] |
| t_cov | −0.052 [−0.086, −0.015] | −0.021 | **−0.52** [−0.85, −0.15] |
| t_buffer | +0.055 [+0.014, +0.095] | +0.013 | 0.33 [0.08, 0.56] |
| t_sip_n04 | +0.032 [+0.002, +0.063] | +0.016 | 0.40 [0.02, 0.80] |
| t_sip_n01 | **−0.190** [−0.228, −0.152] | −0.096 | **−2.39** [−2.87, −1.92] |
| t_b2b | +0.004 [−0.032, +0.042] | +0.003 | 0.08 [−0.65, 0.86] |
| t_home_away | +0.021 [−0.012, +0.055] | +0.010 | 0.26 [−0.15, 0.67] |
Stat dummy（相對 PTS）：REB −0.09、AST −0.19、3PM −0.27（CI 全部排除 0）；截距 0.385。
(A) 每 stat `(a, b)`：PTS (0.30, 0.92)、REB (0.19, 0.83)、AST (0.07, 0.85)、3PM (−0.02, 0.87)（斜率全部 <1＝(c) 過度自信，截距正＝(c) 低估）。

**表面讀法**（⚠️ 見 §6.5，唔可信）：數據「保留」buffer／sip_n04／trend／home_away 嘅方向，但只有 live 設計大小嘅 1/4–2/5；**cov 同 sip_n01 方向反轉**（sip_n01 −2.4 倍）；b2b 冇資訊。

### 6.4 選注相關視角（`p ≥ 0.70` 區，描述性，唔係利潤）
| arm | H1 n（佔比） | 平均 p | 實際命中率 | H2 n | H2 平均 p | H2 命中率 |
|---|---|---|---|---|---|---|
| (a) live base | 23,087（27.2%） | 0.781 | **0.727** | 47,681 | 0.781 | 0.731 |
| (c) | 18,186（21.5%） | 0.807 | 0.797 | 37,331 | 0.804 | 0.797 |
| (A) | 18,741（22.1%） | 0.791 | 0.797 | 38,295 | 0.789 | 0.796 |
| (B)＝(C) | 20,550（24.2%） | 0.796 | 0.801 | 41,303 | 0.794 | 0.799 |
(a) 喺高機率區高估 5pp（0.781 對 0.727）；(c)／(A)／(B) 高機率區基本校準（差 ≤0.01，略保守）。S1（H1）：(a) 0.782 對 **0.694**（高估 9pp）；(c) 0.808 對 0.764；(B) 0.794 對 0.766（n 15,318）。即係 **live base 喺 `p≥0.70` 嘅「腿」系統性高估，兩個 population 都係。**

### 6.5 ⚠️ 選擇偏差：點解 (B)(C) 嘅「passes」唔可信
- Primary population 以**賽後** `MIN_g ≥ 15` 過濾（EXP-02 已標明係用戶規格嘅已知偏差，當時 S1 核對過「結論方向冇變」）。呢個偏差而家被**擬合層主動利用**：`t_sip_n01`（prior-10 平均 MIN <20 → −5、<25 → −3）嘅係數係 −0.096／pp（保留 −2.4 倍，方向反轉）。
- **事後描述性診斷（dev）**：喺 primary，`t_sip_n01=−5`（prior-10 平均 <20 分鐘）嘅 9,057 行，`mean(y − p_c)` ＝ **+0.139**；−3：+0.033；0：+0.003。即係「平均出場少但今場又打夠 15 分鐘」嘅 bench 球員實際命中率比模型高 14pp——因為**只保留今場真係打夠分鐘嗰啲**（打得少嘅今場已經被剔走）。喺 S1（賽前可知，冇賽後過濾）：−3：**−0.017**，0：−0.005，冇呢個效應。
- 所以 (B)(C) 嘅 sip_n01 係數係 population 偽影；其他係數（cov 等）同 bench 球員相關，亦被污染。**係數表唔可以當成「資料保留邊啲 live 項」嘅答案。**
- **S1 敏感度**（用 primary 擬合嘅同一組係數，唔重擬合；非判決）：(B) 對 (a) H1 −0.0136 [−0.0149, −0.0123]，但對 (c) 只有 −0.0010 [−0.0017, −0.0002]（H2：−0.0002 [−0.0006, +0.0002] ＝ 冇增益）；(A) 對 (c) H1 −0.0001（跨 0）；H1 slope (B) 0.913、(A) 0.923、(c) 0.790、(a) 0.569；PTS (B) slope 0.805／citl +0.014，REB (B) citl **+0.051**（高估）。S1 嘅 (c) 已經 slope 0.79、citl≈0；擬合層喺 S1 冇明顯額外價值，而且因為用咗偏差擬合嘅係數，S1 嘅 citl 全部偏正（過高估）。
- 結論：**預先登記規則字面上 (B)(C) passes，但呢個結果係由 population 選擇偏差產生，唔可作為 production 或 shadow 嘅證據。** 呢個同 `statistical-gates-do-not-catch-leakage`（shuffle test、dev sign、H2 全部 pass 都唔代表冇偏差）一致。

## 7. 呢個實驗講到乜、講唔到乜
**講到**
1. **(c)（Poisson/NB）已經大幅贏 live base**，而簡單 per-stat 重校準 (A) 再改善（slope 0.77→0.90；對 (a) H1 −0.0167）。呢個結論喺兩個 population 都成立（S1：(c) 對 (a) −0.0127、(A) 對 (a) −0.0128）。
2. live base 喺高機率區（≥0.70）高估 5–9pp，(c)／(A) 該區近乎校準。
3. 擬合層「加 7 項」對 (c)／(A) 嘅**額外**增益，喺 primary 係 −0.004（(A)→(B)），喺賽前可知 S1 約 0（H2 −0.0002，跨 0）→ **冇可靠證據顯示 live 7 項經過擬合後仍然有用**。
4. λ 揀到 0：正則化冇改善 validation（Dec）Brier，擬合 13 參數喺 53k 行唔過擬合。

**講唔到**
- **(B)(C) 嘅「passes」冇證據價值**（§6.5）。冇任何證據支持 production 切換。
- 冇用賠率、線唔係莊家開價母體；**完全冇講利潤／EV**；只有 7 項可重現 live 項（冇 spread／對手 pace／防守／USG／傷兵／ML）；只常規賽；擬合模型冇 −20 cap／5–98 clamp。
- 擬合喺 dev 只有 ~Nov–Dec（53k 行／351 場），季節性（如 Jan 之後）只由 H1／H2 檢驗。
- S1 評估用 primary 擬合係數（按協議），所以 S1 結果偏悲觀；**未做**「喺 S1 擬合、喺 S1 評估」——呢個係新設計，要開新協議（§8）。

## 8. 下一個實驗（建議，唔喺本實驗內做）
**EXP-20261021-05：用賽前可知嘅 population 重做擬合。** Population 定義＝prior-10 平均 MIN≥20（甚至唔加過濾），**唔用賽後 `MIN_g`**，DNP／低分鐘場次保留（需要確認 game log 有冇 0 分鐘場次；本次已丟棄 MIN==0）；其餘照用同一個 dev／H1／H2、同一套判決規則同 bootstrap；cluster＝GAME_ID。要預先登記：S1 為唯一 primary；「增益對 (c)」同「對 (a)」兩個比較都要有 CI；H2 要有獨立 CI。若 B 對 (c) 嘅增益仍然 ~0，結論就係「(A) per-stat 重校準 + Poisson/NB 已經足夠，live 項可以唔要」——呢個先係值得做 release experiment 嘅 candidate。

## 9. Shadow deployment design（僅有條件；因 §6.5，唯一合適嘅第一步係上面 EXP-05；以下係若果 EXP-05 `passes` 先會用）
- **形式**：喺 live 機率旁邊計算擬合層 `p_fit`，**只寫入 shadow 欄位**（例如 `.market_legs.json` 同 snapshot 內 `shadow_fit_prob`、`shadow_fit_version`、輸入 `base_c`／`p_b`／7 項 `t_*`），**唔參與** EV／Kelly／排名／SGM 選腿。用同 ML hybrid shadow 一樣嘅開關風格（例如 `NBA_FIT_LAYER_SHADOW_ENABLED`，**預設關**），係數檔由離線擬合產出、有版本同 hash，運行時唔擬合。
- **證據門檻（升格前）**：由 forward snapshot 累積已結算嘅腿（含真實莊家 line 同價格），要求 (i) 達到預先登記嘅最少結算腿數（按目標 MDE 同 cluster 結構喺新協議計，唔係拍腦袋）；(ii) 喺 `p≥0.70` 區同整體 calibration slope／reliability 達標；(iii) 對 live 嘅配對 bootstrap 優勢；(iv) 實際定價 line 上嘅表現（本實驗完全冇量）。任何 production 切換都係獨立、用戶批准嘅改動，並要有可退回 baseline。
- **缺失 live 輸入（spread／對手 pace／防守／USG／傷兵）**：日後只作為**額外特徵**加入同一個 logistic 層，並且要在新協議逐項擬合、逐項報告係數 CI 同 ablation（吸取 EXP-03：加性手調項會造成系統性負偏）；喺 game log 重現唔到，所以要用 forward snapshot 嘅真實輸入先可以評估。

## 10. 決定
**NEEDS MORE TESTING。** 預先登記規則：(B)(C) passes、(A)(c) not shown；但 passes 由 primary 嘅賽後分鐘過濾偏差產生，S1 下增益消失，故**不作為證據**，亦**唔建議 shadow／production**。已確認嘅係：(c) 同 (A) 比 live base 好，live base 喺高機率區高估。
