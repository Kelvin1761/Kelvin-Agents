# EXP-20261021-05 NBA 擬合層喺「賽前可知 population」重做（修正賽後 MIN 過濾偏差）

- **日期**：2026-10-21
- **平台**：NBA
- **假設**：EXP-04 嘅「(B)(C) passes」係賽後 `MIN_g≥15` 過濾造成嘅偽影（bench 行 `y−p_c` +14pp；S1 下對 (c) 增益 ~0）。**假設：喺賽前可知、冇任何賽後過濾嘅 population 上，用 dev 擬合嘅 logistic 層（(A)(B)(C)）仍然（i）贏 live base (a)、（ii）過校準門檻、（iii）喺 (c) 之上有額外增益。** 可證偽：若 (A)(B)(C) 唔過下面六條件，或者過但 selection-bias 檢查失敗，結論就係「冇任何擬合層被採納；(c)＋重校準已經係全部可得資訊」。
- **搜索過嘅舊記錄**：EXP-20261021-02／03／04（base、ablation、refit；04 §6.5 偏差診斷同 §8 建議）。冇其他 NBA 記錄。
- **改到嘅檔案／組件**：**冇改 production code。** 新增 `docs/experiments/patches/nba_calibration_exp20261021_02/nba_pregame.py`（重用 `nba_calib`、`nba_refit`）。EXP-02～04 嘅檔案不變。
- **狀態**：✅ 已跑一次，結果喺 §6。協議 commit `c4f1d3e9`（計結果前）、harness commit `4b14b8e6`（跑真數據前）。
- **按預先登記規則**：(A)、(B)、(C) **六條全過**；selection-bias 檢查**冇觸發**（最大桶殘差 −0.018，CI 包 0）→ 字面 **`passes`**。(c) 同 (E) 係比較 arm，唔過；**(E)＝live 最終機率比 live base (a) 更差**。
- **要睇清楚嘅嘢**：(i) 增益主要來自 **(A)＝Poisson/NB＋per-stat 重校準**；加 7 個 live 項嘅 (B) 對 (A) 只再多 −0.0006 Brier（H2），係數大部分 CI 包 0；(ii) 全部都係 near-mean 線嘅離線度量，**冇利潤聲稱，冇對 live 模型改善嘅聲稱**。
- **決定**：**PASSES（離線，按規則）→ 只建議「shadow 設計」作下一步（§9），唔建議 production 切換；採納與否由用戶決定。**

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

環境：Python 3.9.6、numpy 2.0.2、pandas 2.3.3、scipy 1.13.1；`PYTHONDONTWRITEBYTECODE=1`。Harness commit `4b14b8e6d6c0c7be2098ab749b98ef22e6e26899`（`nba_pregame.py`、`test_pregame.py`；11/11 單元測試 pass，包括 EXP-02 嘅 5 個 point-in-time、EXP-04 嘅 3 個擬合、本實驗 3 個：MIN==0 唔入 prior／virtual 缺席 unit 只用更早資料且 y=0／feature 唔隨 outcome 改變）。Live code blob `generate_nba_reports.py` `82ee97cc…`（冇改）。
Scratchpad：`/private/tmp/claude-501/-Users-imac-Antigravity-repo--claude-worktrees-nba-calibration-exp-56dc4c/1fa02346-3347-461b-80cf-3be02bd426e1/scratchpad/`；raw 同 EXP-02（sha256 `43523d96…`／`320455e0…`）。
- `out5/rows.csv` sha256 `e8b25930c90c8ea5568524134200fbc6a1e192cd388c6b4918feb7c43d9e128e`（380,691 行）
- `out5/results5.json` sha256 `ddff920d3a157bfad4229a397e84cc4abd69ea52c143ad57845efd41f2601065`
```bash
export PYTHONDONTWRITEBYTECODE=1
H=docs/experiments/patches/nba_calibration_exp20261021_02; S=<scratchpad>
python3 -W ignore -m unittest discover -s $H -p "test_*.py"                          # 11/11 OK
python3 -W ignore $H/nba_pregame.py build --raw $S/raw --out $S/out5
python3 -W ignore $H/nba_pregame.py check --old $S/out3 --out $S/out5               # 同 EXP-03 對賬
python3 -W ignore $H/nba_pregame.py run   --out $S/out5                             # 只跑一次
```
`check` 通過：新 population 嘅 `MIN>0` 部分同 EXP-03 嘅 S1 行逐值一致（303,288 行）；舊 `MIN_g≥15` 行同 EXP-03 primary 一致（354,606 行）。

## 6. 結果

### 6.1 Population 同 DNP 缺失偏差（量化）
- Primary（`pregame`，冇賽後過濾）行數：dev 46,422、H1 71,862、H2 150,876（unit：4,180／6,474／13,452 個球員場次）。
- **log 只列有上場球員**（只有極少 `MIN==0` 行）：primary 入面 `MIN==0` unit 只有 dev 0、H1 1、H2 1；早退比例 `MIN_g<15` 4.9%／4.5%／4.1%，`MIN_g<10` 1.4%／1.4%／1.2%。
- **缺席 rotation 球員（單場缺席：上一場同下一場同隊都有上場、今場冇行；多場缺席／交易／長傷唔計）**：dev 144 個（**3.3%**）、H1 352 個（**5.2%**）、H2 609 個（**4.3%**），佔 `（缺席＋出現）` unit。呢個係**下限**（多場缺席唔計），亦係**上界嘅分子**（大部分賽前已公布 OUT，莊家唔開盤，唔係腿）。
- **最壞情況 `S_dnp`**（將全部單場缺席當真腿、y=0）：每個 arm 嘅 citl 向正偏（H1：(a) +0.046、(c) +0.027、(A) +0.020、(B) +0.018），H1 slope：(a) 0.524、(c) 0.736、(A) **0.859**、(B) **0.889**；對 (a) 嘅 ΔBrier H1：(A) −0.0153、(B) −0.0162（H2 −0.0142／−0.0148），對 (c)：(B) −0.0030（H2 −0.0023）。**即係就算最壞情況，擬合 arm 仍然贏，slope 仍然 ≥0.85；DNP 偏差改變絕對校準（高估 ~2pp），唔改變排序。**（描述性，非判決。）
- 舊 population（`MIN_g≥15`）亦重算作描述性敏感度（§6.6）。

### 6.2 擬合細節（只用 dev）
- Tuned：`w`＝PTS .35／REB .15／AST .15／3PM .10；NB `α(PTS)`＝0.197。
- **(C) 嘅 λ**：train＝Nov（18,498 行）、validation＝Dec（27,924 行）；validation Brier：λ=0 **0.22138**、10 0.22139、100 0.22146、1,000 0.22208、10,000 0.22776、100,000 0.24368 → **揀 λ=0，(C)＝(B)**。
- **洩漏檢查**：shuffle test（dev）最大 `|標準化係數|`＝0.020、in-sample Brier 改善 3.5e-5 → **PASS**；point-in-time 單元測試 11/11。

### 6.3 Selection-bias 檢查（預先登記，dev primary，`mean(y − p_c)`）
| prior-10 平均 MIN 桶 | n | 平均殘差 | 95% CI（cluster bootstrap） |
|---|---|---|---|
| <20 | 0（按定義冇行） | — | — |
| 20–25 | 11,847 | −0.018 | [−0.035, +0.0003] |
| ≥25 | 34,575 | −0.005 | [−0.015, +0.005] |
**冇桶 |殘差|>0.03 → population 唔算有偏差，`passes` 有效。** 留意 20–25 桶 −1.8pp、CI 剛剛包 0，擬合模型喺呢批 bench-ish 球員可能略為高估（見 §8）。EXP-04 嗰個 +0.139 偏差已消失。

### 6.4 判決（primary，六條，預先登記）
| Arm | ①H1 CI<0 | ②dev<0 | ③H2 CI<0 | ④H1 slope∈[.85,1.15] | ⑤冇壞桶 | ⑥H2 對 (c) CI<0 | **判決** |
|---|---|---|---|---|---|---|---|
| (c) Poisson/NB（比較） | ✅ | ✅ | ✅ | ❌ 0.789 | ❌（最低兩桶低估 .07／.05） | n/a | 比較 arm，唔過 |
| (E) live 最終機率（比較） | ❌（+0.0085） | ❌ | ❌ | ❌ **0.446** | ❌（8 個桶） | n/a | 比較 arm，唔過 |
| **(A)** per-stat 重校準 | ✅ | ✅ | ✅ | ✅ 0.920 | ✅ | ✅ | **passes** |
| **(B)** pooled logistic＋7 項 | ✅ | ✅ | ✅ | ✅ 0.950 | ✅ | ✅ | **passes** |
| **(C)** (B)＋L2（λ=0） | ✅ | ✅ | ✅ | ✅ 0.950 | ✅ | ✅ | **passes**（＝(B)） |

pooled ΔBrier vs (a) [95% CI]（括號＝vs (c)）：
| Arm | dev | H1 | H2 | H1 slope [CI] | H2 slope |
|---|---|---|---|---|---|
| (c) | −0.0108 | −0.0127 [−0.0140, −0.0112] | −0.0122 [−0.0131, −0.0112] | 0.789 [0.77, 0.81] | 0.811 |
| (A) | −0.0115 (−0.0007) | −0.0141 [−0.0153, −0.0127] (−0.0014 [−0.0016, −0.0012]) | −0.0132 [−0.0141, −0.0123] (−0.0010 [−0.0011, −0.0008]) | 0.920 [0.90, 0.95] | 0.943 |
| (B)＝(C) | −0.0121 (−0.0012) | −0.0147 [−0.0160, −0.0134] (−0.0020 [−0.0024, −0.0017]) | −0.0138 [−0.0146, −0.0129] (−0.0016 [−0.0018, −0.0014]) | 0.950 [0.93, 0.98] | 0.963 |
| (E) live final | +0.0078 | **+0.0085** [+0.0073, +0.0097] | +0.0088 [+0.0080, +0.0097] | **0.446** [0.43, 0.46] | 0.446 |
Brier（H1）：(a) 0.2348、(c) 0.2222、(A) 0.2208、(B) 0.2201、(E) 0.2434。Holm（5 個比較 vs (a)）：全部 p＝0.0005 地板，調整後 0.0025，結論唔變。
**幅度解讀**：(c) 已經佔大部分改善（vs (a) −0.0127）；(A) 再多 −0.0014；加 7 項（(B) vs (A)）只再多約 −0.0006（H1／H2）。擬合層嘅額外增益「統計上確實、實質上細」。
逐 stat（H1，ΔBrier vs (a)；(B) slope）：PTS −0.0131（0.882）、REB −0.0162（0.974）、AST −0.0149（0.954）、3PM −0.0147（0.987）。PTS 嘅 (B) slope 0.882 較低；(A) PTS slope 0.881。(B) 對 (c) 逐 stat H2：PTS −0.0020、REB −0.0021、AST −0.0015、3PM −0.0004（CI 包 0）。

### 6.5 係數（(B)＝(C)；dev；cluster bootstrap 300 次）——selection-bias 檢查已通過，所以有意義
| 特徵 | 標準化 β [CI] | 原始 β／pp | **保留比例 [CI]**（1＝同 live 設計一樣大） |
|---|---|---|---|
| logit(p_c) | 0.587 [0.518, 0.665] | 0.656 | — |
| logit(p_b) | 0.150 [0.076, 0.216] | 0.149 | — |
| t_trend | +0.032 [−0.003, +0.066] | +0.007 | 0.18 [−0.02, 0.37] |
| t_cov | −0.034 [−0.070, +0.004] | −0.013 | −0.33 [−0.67, 0.04] |
| t_buffer | +0.047 [+0.006, +0.092] | +0.011 | **0.28** [0.04, 0.56] |
| t_sip_n04 | +0.041 [+0.009, +0.078] | +0.021 | **0.52** [0.11, 0.98] |
| t_sip_n01 | +0.030 [−0.011, +0.068] | +0.023 | 0.58 [−0.22, 1.29] |
| t_b2b | +0.008 [−0.032, +0.047] | +0.007 | 0.18 [−0.67, 0.99] |
| t_home_away | +0.007 [−0.033, +0.043] | +0.004 | 0.09 [−0.40, 0.52] |
Stat dummy（相對 PTS）：REB −0.06 [−0.12, +0.01]、AST −0.09 [−0.17, −0.02]、3PM −0.16 [−0.23, −0.09]；截距 0.168。
(A) per-stat `(a, b)`：PTS (0.05, 0.81)、REB (−0.04, 0.87)、AST (−0.06, 0.86)、3PM (−0.11, 0.89)；斜率 CI 全部 <1（上限 0.93–0.94）→ (c) 過度自信、約 0.81–0.89 倍縮減。
**答「fit instead of remove」**：數據保留嘅只有 **buffer（0.28 倍）、sip_n04（0.52 倍）** 兩項（CI 排除 0，正向，細過 live 設計）；trend、cov、sip_n01、b2b、home_away 嘅 CI 全包 0（cov 方向反 −0.33 但包 0）。同 EXP-03（add-one 令 base 更差）一致嘅係：live 設計大小（保留比例 =1）全部落喺 CI 之外。

### 6.6 描述性敏感度：舊 population（`MIN_g≥15`，只作對照）
pooled，H2：(A) −0.0138 vs (a)、(B) −0.0130；**(B) 對 (c) 嘅增益 −0.0001 [−0.0003, +0.0001]（＝冇增益）**，H1 −0.0005；(B) 嘅 citl −0.052（低估）。即係舊 population 下擬合層冇額外價值並且帶偏，同 EXP-04 §6.5 診斷一致；賽前 population 先睇到 (B) 對 (c) 嘅小而穩定嘅增益。

### 6.7 選注相關視角（`p≥0.70`／`p≥0.80`；描述性，唔係利潤）
H1（n＝71,862 行）：
| arm | ≥0.70：n（佔比）／平均 p／實際命中 | ≥0.80：n（佔比）／平均 p／實際命中 |
|---|---|---|
| (a) live base | 20,399（28.4%）／0.782／**0.694** | 11,055（15.4%）／0.852／**0.750** |
| (c) | 15,576（21.7%）／0.808／0.764 | 8,073（11.2%）／0.864／0.821 |
| (E) live final | 14,955（20.8%）／0.822／**0.723** | 7,759（10.8%）／0.897／**0.767** |
| (A) | 12,572（17.5%）／0.791／0.786 | 5,124（7.1%）／0.853／0.845 |
| (B)＝(C) | 12,311（17.1%）／0.788／0.790 | 4,776（6.6%）／0.851／0.855 |
H2（n＝150,876）：(a) ≥0.70 42,388（28.1%）0.784／0.701；≥0.80 23,228（15.4%）0.853／0.755。(c) 32,083／0.805／0.766；16,034／0.861／0.823。(E) 31,709（21.0%）0.825／**0.726**；16,673（11.1%）0.898／**0.768**。(A) 25,761（17.1%）0.788／0.787；10,120（6.7%）0.849／0.845。(B) 25,577（17.0%）0.786／0.790；9,837（6.5%）0.847／0.849。
**讀法**：live 最終機率 (E) 喺高機率區**高估 10–13pp**（≥0.80：預測 0.897 對實際 0.767），比 live base (a)（高估 ~10pp）更差；(c) 輕微高估（~4pp）；(A)(B) 兩區都近乎完美校準（差 ≤0.01）。但 (A)(B) 令「達標腿」數目由 28% 降到 17%（≥0.80 由 15% 到 6.5–7%）——真係高機率嘅腿少咗，唔係可以拿來當「更多腿」。H1 reliability，(B) 所有 n≥500 桶 `|差|≤0.005`，最低桶（n=326）預測 .074 對 .120。

## 7. 呢個實驗講到乜、講唔到乜
**講到（賽前可知 population、dev 擬合、H1／H2 各一次）**
1. **按預先登記六條規則，(A)(B)(C) 全部 passes，selection-bias 檢查冇觸發。** 擬合層能夠令 slope 入 [0.85,1.15]，高機率區校準，兩個獨立窗口（2025-26 H1、2024-25 H2）一致。
2. **絕大部分價值喺 Poisson/NB (c)＋簡單重校準 (A)**；7 個 live 項經擬合後只剩 buffer、sip_n04 兩項有（細幅）正向資訊，對 (A) 只再多 ~0.0006 Brier。簡單 > 複雜：(A) 只有 8 個參數並且六條全過。
3. **live 最終機率 (E) 比 live base 更差、slope 0.446、高機率區高估 10–13pp**——呢個確認咗 EXP-03 嘅發現（加性手調項令校準惡化）喺賽前 population 上亦成立。
4. DNP 缺失偏差（單場缺席 3–5%）改變絕對校準（最壞高估約 2pp）但唔改變排序／結論。

**講唔到**
- **完全冇講利潤／EV；冇用賠率。** 線係「prior-10 平均附近 3 個整數」，唔係莊家開價母體（莊家 shade、範圍更廣）。「達標腿」數目少咗唔等於選注更好。
- 只有 7 個可重現 live 項；spread／對手 pace／防守／USG／傷兵／ML 冇數據。擬合模型冇 −20 cap／5–98 clamp。只常規賽，2025-26＋2024-25。
- 係數／增益用嘅係 dev（~Nov–Dec，46k 行／351 場）擬合，季節性只靠 H1／H2 驗證。
- 20–25 分鐘桶嘅殘差 −1.8pp（CI 邊緣）：擬合模型喺 bench-ish 球員可能輕微高估。
- **冇聲稱 live 模型有任何改善。** 本實驗只係離線度量同候選比較。

## 8. 「what could still be wrong」
- **DNP／scratch 偏差**：log 唔列未上場球員；真正臨場 scratch 唔識別。最壞情況敏感度顯示絕對校準偏約 2pp，但真實比例未知（只可由 forward snapshot＋傷病名單量度）。
- **傷病／輪休／交易**：賽前已知 OUT 嘅球員實務上唔開盤；log 識別唔到「賽前已知」。mid-season 交易令 prior 混合兩隊（只用球員自己嘅 game log，影響 minutes／role 預測）；呢啲 role 變化冇建模。
- **分鐘預測質素**：`μ＝season rate × prior-10 平均 MIN`，冇用傷病／blowout／對手資訊；賽前真實預計分鐘（首發名單）更準。
- **Population 代表性**：預測圍繞 prior-10 平均嘅線，同莊家真正掛出嘅線（偏離平均得多、長尾）唔同；高機率腿（p≥0.80）喺本 population 通常係「線低於平均」嗰啲。
- **多重／相關**：每個 unit 有 3 條線、同場球員相關——bootstrap 以 GAME_ID cluster 處理，但同日多場嘅共同因素（例如 league-wide 趨勢）冇處理。
- **擬合穩定性**：只有一個 dev 窗；H2 在時間上早於 dev。若 2026-27 賽季規則／節奏改變，係數可能漂移。
- **規則門檻**：「slope∈[0.85,1.15]」「|桶差|≤0.05」係預先登記嘅門檻，唔係經驗證嘅決策閾值。

## 9. Shadow deployment design（因為六條全過＋bias 檢查通過先寫；**唔等於建議 production 切換**）
- **推薦 shadow 嘅模型**：**(A)**（Poisson/NB＋per-stat 重校準，8 個參數）為首選，因為 (B) 對 (A) 增益只 ~0.0006、係數大部分 CI 包 0，按「簡單而穩健 > 複雜而邊際」唔值得多 9 個參數；(B) 可作第二個 shadow 欄位比較。最終採納與否由用戶決定。
- **形式**：喺 live 機率旁邊計算 `p_fit`，**只寫入 shadow 欄位**（`.market_legs.json` 同 snapshot 內，例如 `shadow_fit_prob_A`、`shadow_fit_prob_B`、`shadow_fit_version`、輸入 `mu`／`base_c`／`t_*`），**唔參與** EV／Kelly／排名／SGM 選腿。用同 ML hybrid shadow 一樣風格嘅開關（例如 `NBA_FIT_LAYER_SHADOW_ENABLED`，**預設關**）。係數檔（`a_s, b_s`；`μ` 參數 `w`、`α`）由離線擬合產出，帶版本同 hash，運行時**唔擬合**。
- **缺失 live 輸入（spread／對手 pace／防守／USG／傷兵）**：日後只作額外特徵加入同一個 logistic 層，逐項擬合、逐項報告係數 CI 同 ablation（EXP-03 教訓：加性手調項造成系統性負偏）；因為 game log 重現唔到，只可用 forward snapshot 嘅真實輸入評估。
- **升格前嘅 forward 證據門檻**：(i) 累積已結算、有真實莊家 line 同價格嘅腿，數量由新協議按目標 MDE 同 cluster 結構預先計算；(ii) 真 line 母體上 `p≥0.70`／`p≥0.80` 區同整體 slope／reliability 達標，唔係只喺 near-mean 線；(iii) 對 live 最終機率 (E) 同 base 嘅配對 bootstrap 優勢；(iv) 實際定價 line 上嘅表現（本實驗完全冇量）；(v) 量度真實 DNP／scratch 比例，重新校準；(vi) 要有可退回 baseline。任何 production 切換係獨立、用戶批准嘅改動。

## 10. 決定
**PASSES（離線、按預先登記規則）：(A)(B)(C)。** 但：(1) 實質貢獻主要係 Poisson/NB＋重校準，7 個 live 項經擬合後貢獻細；(2) 冇利潤聲稱、冇 production 聲稱；(3) 建議只進行 §9 嘅 shadow（若用戶批准）。(E)（live 最終機率）係本實驗中最差嘅 arm。

## 11. §9 addendum（2026-10-21）：shadow artefact for candidate (A)——已建、未接入 live

按用戶決定建好 (A) 嘅**凍結係數檔**同**參考實作**；**冇改任何 production scoring code**，接入（default-off shadow 欄位）由 NBA session 負責。

**檔案（全部喺 repo）**
| 項 | 路徑 | sha256 |
|---|---|---|
| 凍結係數 | `.agents/skills/nba/nba_wong_choi/resources/nba_fit_layer_A_v1.json` | `7e74022cc7dfa37938dc3046b665d17af4c6279ab64f720fc5ae5af65227e56f` |
| 參考實作（純標準庫，無 scipy／numpy） | `.agents/skills/nba/nba_wong_choi/scripts/nba_fit_layer.py` | — |
| parity fixture（400 個真 unit） | `.agents/skills/nba/nba_wong_choi/tests/fixtures/nba_fit_layer_A_parity.json` | `46889d3217ddbb740829a301d6f01d01e4c07c0755840ab16bd22e490346aaa6` |
| 測試 | `.agents/skills/nba/nba_wong_choi/tests/test_nba_fit_layer.py`（11 個） | — |
| 產生腳本 | `docs/experiments/patches/nba_calibration_exp20261021_02/make_fit_layer_artifact.py` | — |

- 係數檔嘅值**原封不動**取自 EXP-05 `results5.json`（sha256 `ddff920d…`）嘅 dev 擬合：NB `α(PTS)`＝0.19714961024606556（REB／AST／3PM＝Poisson）；per-stat 重校準 `(a,b)`：PTS (0.05311, 0.80714)、REB (−0.04003, 0.87462)、AST (−0.05775, 0.86413)、3PM (−0.11288, 0.88895)。**冇用 H1／H2 或更新數據重擬合。** 檔內帶 `model_id=nba_fit_layer_A_v1`、`created_at`、`source_experiment`、harness commit `4b14b8e6…`、dev 窗、兩季 raw game-log sha256、擬合命令。
- Loader 用 `nba_fit_layer.py` 內釘死嘅 `EXPECTED_SHA256` 驗證；檔案缺失／hash 唔符／格式壞 → 回 `(None, reason)`，**唔會 raise，亦唔會出機率**（呼叫方要將 shadow 欄位留空）。改係數檔必須同時改釘死嘅 hash（即係一個有紀錄嘅改動）。
- **Runtime 只需標準庫**（`math`、`json`、`hashlib`、`os`）；Poisson／NegBin 存活函數用 pmf 遞推實作，同 scipy 比對 ≤1e-10。喺 scheduler 用嘅 `/usr/bin/python3`（3.9.6）驗證過；測試包含 `python3 -I` 子程序確認 import 後 `scipy`／`numpy` 不在 `sys.modules`。
- **Parity**：400 個 unit（seed 20261021，覆蓋 4 個 stat，兩季）；輸入由 raw game log 重算（並 assert 同 harness 嘅 `mu` 一致到 1e-12），`p_fit_A` 同 harness (A)（`nba_refit.recal_pred`，clip [0.01,0.99]）最大差 <1e-9（測試通過）。

**Live pipeline 必須提供嘅輸入（每個 stat、每條線）**
```
p_fit_A(stat, line, season_stat_total, season_minutes_total, prior10_mean_min)
```
- `stat`：`PTS`／`REB`／`AST`／`FG3M`（亦接受 `3PM` 等別名）。
- `line`：整數 milestone `N≥1`（結果＝ `stat ≥ N`）；非整數／<1 → `None`。
- `season_stat_total`：該球員**同一賽季**、**日期嚴格早於今場日期**、`MIN>0` 嘅所有場次，該 stat 嘅總和。
- `season_minutes_total`：同一批場次嘅 MIN 總和（必須 >0）。
- `prior10_mean_min`：同一批場次入面最近 10 場嘅 MIN 平均（必須 >0；已驗證 population 係 ≥10 場 prior 且平均 ≥20）。
- **Point-in-time 規則**：只可用**今場日期之前**（嚴格 `<`，同日唔計）嘅場次；DNP／`MIN==0` 唔計入；唔跨季（季初未夠 10 場 prior → 唔出 shadow 機率）。
- 輸出：`[0.01, 0.99]` 內機率，或 `None`（輸入無效／模型檔驗證失敗）；`fit_prob_A(...)` 另回 reason 字串方便寫入 shadow 欄位。
- **接入建議（NBA session 負責，shadow only）**：`NBA_FIT_LAYER_SHADOW_ENABLED`（預設關）；只寫 `shadow_fit_prob_A`／`shadow_fit_model_id`／必要輸入快照，**唔參與** EV／Kelly／排名／SGM；線落喺 prior-10 平均附近以外嘅 milestone 超出已驗證範圍，要標記（`line` 與 `prior10 mean` 偏離）。升格前 forward 證據門檻見 §9。
