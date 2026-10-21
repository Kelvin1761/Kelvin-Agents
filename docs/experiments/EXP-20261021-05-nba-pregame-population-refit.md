# EXP-20261021-05 NBA 擬合層喺「賽前可知 population」重做（修正賽後 MIN 過濾偏差）

- **日期**：2026-10-21
- **平台**：NBA
- **假設**：EXP-04 嘅「(B)(C) passes」係賽後 `MIN_g≥15` 過濾造成嘅偽影（bench 行 `y−p_c` +14pp；S1 下對 (c) 增益 ~0）。**假設：喺賽前可知、冇任何賽後過濾嘅 population 上，用 dev 擬合嘅 logistic 層（(A)(B)(C)）仍然（i）贏 live base (a)、（ii）過校準門檻、（iii）喺 (c) 之上有額外增益。** 可證偽：若 (A)(B)(C) 唔過下面六條件，或者過但 selection-bias 檢查失敗，結論就係「冇任何擬合層被採納；(c)＋重校準已經係全部可得資訊」。
- **搜索過嘅舊記錄**：EXP-20261021-02／03／04（base、ablation、refit；04 §6.5 偏差診斷同 §8 建議）。冇其他 NBA 記錄。
- **改到嘅檔案／組件**：**冇改 production code。** 新增 `docs/experiments/patches/nba_calibration_exp20261021_02/nba_pregame.py`（重用 `nba_calib`、`nba_refit`）。EXP-02～04 嘅檔案不變。
- **狀態**：🔵 協議已寫（未跑結果）。

> 限制同 EXP-02～04，**先睇**：線係「L10 平均附近 3 個整數」，唔係莊家開價母體 —— **只量機率引擎校準度，完全冇講利潤／EV**；只有 7 個可重現 live 項；只常規賽（2025-26＋2024-25）；擬合模型冇 −20 cap／5–98 clamp。

## 1. Population（primary，凍結）
- **Unit**：球員 `p` 喺 game `g`（日期 `D`，季 `S`），**只用同季、日期嚴格 `<D`** 嘅出場（`MIN>0`）計：(i) prior 出場數 ≥10；(ii) prior-10 平均 MIN ≥20。**對 game `g` 自己嘅 `MIN`、有冇上場、有冇早退 一概唔過濾。**
- **MIN==0 嘅行**：data 有列出（2025-26 共 83 行、2024-25 共 100 行）。如果該球員滿足 (i)(ii)，保留為 unit，所有 stat＝0（`stat≥N` 對 `N≥1` 恆為 0）＝真實 miss。呢啲行**唔計入**其他日子嘅 prior（live 嘅 game log 亦唔列 DNP；prior 一律只用 `MIN>0` 出場，同 EXP-02～04 一致）。
- **⚠️ DNP 缺失偏差（鏡像偏差，要量化，唔准忽略）**：`LeagueGameLog` **只列有上場嘅球員**（只有少量 `MIN==0` 行）；「完全冇上場」（inactive／DNP／scratch）嘅球員冇行。所以 primary population 嘅 y 係**偏樂觀**（缺咗真 miss）。因為賽前已公布嘅 OUT 球員莊家唔會開盤，所以缺失嘅大部分係**唔係腿**；真正會變成 y=0 嘅只有「賽前冇公布、臨場 scratch／早退」嗰類，從 game log 識別唔到。協議如下：
  1. **量化缺失率**：對每隊每場，數出「單場缺席」球員：喺**該隊上一場同下一場都有上場**（同隊）而今場冇行，並且滿足 (i)(ii) 嘅 rotation 球員（多場缺席／交易／長期傷病唔計，避免誤判）。報 `缺席 unit 數／（缺席＋出現嘅 pregame unit）` 兩季、dev／H1／H2。
  2. **最壞情況敏感度 `S_dnp`**（描述性，非判決）：將上述缺席 unit 當成真腿，所有 stat＝0（y=0），同 primary 一齊評估，量 Brier／slope／citl 嘅變動。呢個係 DNP 偏差嘅**上界**（因為其中大部分賽前已知 OUT）。
  3. 報告 primary 內 `MIN_g<15`（早退／garbage）比例同 `MIN==0` 行數。
- Population 定義**唔准**事後改。**舊 population（`MIN_g≥15`，EXP-02～04 嘅 primary）只作描述性敏感度，唔參與任何判決。**
- 線：同 EXP-02（3 個最近 prior-10 平均 `m` 嘅整數 `N≥1`，`m≥1`）。Stat：PTS／REB／AST／3PM。
- 切分：**dev**＝2025-26 `<2026-01-01`；gap＝1 月；**H1**＝2025-26 `≥2026-02-01`（只評估一次）；**H2**＝2024-25 整季（只評估一次，用 dev 擬合係數）。

## 2. Arm（6 個，固定）
| Arm | 定義 |
|---|---|
| **(a)** | live base `hit_L10`（reference） |
| **(c)** | Poisson/NB（`μ＝season rate×prior-10 平均 MIN`），參數 dev 擬合（同 EXP-02） |
| **(A)** | (c) 嘅 per-stat logistic 重校準 `a_s+b_s·logit(p_c)` |
| **(B)** | pooled logistic（stat dummy，PTS 做基準），特徵 `[logit(p_c), logit(p_b), t_trend, t_cov, t_buffer, t_sip_n04, t_sip_n01, t_b2b, t_home_away]`，用 dev 平均／sd 標準化，λ=0 |
| **(C)** | (B)＋L2，λ ∈ {0,10,100,1000,10000,100000}，dev 內部時間切分（train＝dev 內 `<2025-12-01`，validation＝2025-12-01…12-31）按 Brier 揀（tie 取大 λ），再用全 dev 重擬合 |
| **(E)** | live 最終機率（base＋7 個可重現項，live 5–98 clamp 同 −20 cap；＝EXP-03 `ALL` arm，即 live 實際排腿用嘅機率）。比較 arm，唔擬合 |

- 擬合細節、IRLS、標準化、stat dummy 同 EXP-04 一樣。擬合只用 dev。H1、H2 各評估一次。機率 clip `[0.01,0.99]` 先計分。
- 比較：每個 arm 對 (a) 同對 (c)（paired GAME_ID cluster bootstrap，2000 次，seed 20261021）。Holm 只作資訊。係數 CI：cluster bootstrap 300 次（(A)(B)(C)），報標準化／原始／保留比例（原始係數／0.04）。

## 3. 預先登記判決規則（六條，全部成立先叫 `passes`）
對 (A)(B)(C)（同時報 (c)(E) 嘅各條成立狀況，但佢哋係比較 arm）：
1. H1 pooled `ΔBrier vs (a)` 95% CI 全部 <0；
2. dev pooled `ΔBrier vs (a)` 點估計 <0；
3. H2 pooled `ΔBrier vs (a)` 95% CI 全部 <0；
4. H1 pooled calibration slope ∈ [0.85,1.15]；
5. H1 pooled 10 桶 reliability：所有 n≥500 嘅桶 `|mean p − mean y| ≤0.05`；
6. **H2 pooled `ΔBrier vs (c)` 95% CI 全部 <0**（擬合層要有 (c) 以外嘅額外增益）。
- **Selection-bias 檢查（預先登記）**：喺 dev primary，按 prior-10 平均 MIN 分桶 `<20`（按定義冇行）／`20–25`／`≥25`，報 `mean(y − p_c)` 同 GAME_ID cluster bootstrap 95% CI。若任何有行嘅桶 `|平均殘差|>0.03` 且 CI 唔包 0 → **population 仍有偏差，任何 `passes` 作廢（NOT usable）**。
- 不准用 H1／H2 重擬合、換特徵、λ 網格、指標或窗口去救候選；想換設計就開新實驗。

## 4. 其他報告（描述性）
- **選注相關視角（唔係利潤）**：(a)(c)(E) 同所有擬合 arm，喺 `p≥0.70` 同 `p≥0.80`：n、佔全部行比例、平均預測 p、實際命中率；H1、H2。
- 逐 stat（H1／H2 ΔBrier、slope）；舊 population 描述性敏感度；`S_dnp` 最壞情況；DNP 缺失率。
- **洩漏檢查**：point-in-time 單元測試（5/5＋新增「MIN==0 唔入 prior」「virtual unit 只用嚴格更早」測試）；shuffle test（dev，同 EXP-04：標籤置換後重擬合 (B)，PASS＝`|標準化係數|<0.05` 且 in-sample Brier 改善 <0.0005）。
- 係數警告：只喺 selection-bias 檢查通過先有意義。
- §「what could still be wrong」、若全過（六條＋bias 檢查）先寫 shadow deployment design；否則明確寫「冇任何 arm 被採納」同零結果教咗乜。

## 5. 重跑
（跑完後填）

## 6. 結果
（跑完後填）
