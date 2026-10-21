# EXP-20261021-03 NBA live 調整項逐項 ablation（邊項令機率更差？）

- **日期**：2026-10-21
- **平台**：NBA
- **假設**：EXP-20261021-02 發現「可由 game log 重現嘅 live 調整項合起嚟令 Brier 更差（+0.019，slope 0.41）」。本實驗問：**係邊幾項令佢更差？係單項本身有害，定係幾項由同一組 L10 數值導出、重疊計數（互動）？** 可證偽：若冇任何單項過預先登記嘅 `harmful` 條件，且單項效應總和 ≈ 聯合效應，就唔存在「某項有害」嘅證據。
- **搜索過嘅舊記錄**：EXP-20261021-02（本實驗前置；同 population／切分／bootstrap）。`grep -il nba docs/experiments/` 冇其他 NBA ablation。
- **改到嘅檔案／組件**：**冇改 production code。** 只喺 `docs/experiments/patches/nba_calibration_exp20261021_02/` 加 `nba_ablation.py`（同目錄，重用 EXP-02 harness），並喺 `nba_calib.py` 加（純增量）欄位 `t_*`＝live `calc_adjusted_winprob` 回傳嘅逐項 breakdown。
- **狀態**：🔵 協議已寫（未跑結果）。

> ⚠️ 限制同 EXP-02 一樣，**先睇**：(1) 線係「L10 平均附近嘅 3 個整數」，唔係莊家開價母體，只量機率引擎校準度，**完全冇講利潤／EV**；(2) 只可重現 7 項（spread、對手 pace／防守、USG／傷兵、ML 都冇）；(3) 只常規賽，兩季。本記錄**唔建議改 production**；任何移除 live 項都係日後獨立、用戶批准嘅改動，呢度嘅「harmful」最多係「值得做後續 release experiment 嘅候選」。

## 1. 被量嘅項（讀 live code，同 EXP-02 §1 一致）
`calc_adjusted_winprob` 喺缺 spread／對手／USG／ML 時，下列 7 項可由 game log 重現；其餘項喺本實驗恆為 0（同 live 缺值行為一致）。

| 代號 | live breakdown key | 內容（pp） | 輸入來源 |
|---|---|---|---|
| trend | `trend` | `hit_L5 − hit_L10` 階梯（+8…−8） | L10 值 |
| cov | `cov` | L10 sd/avg 階梯（+6…−6） | L10 值 |
| buffer | `buffer` | `(avg−N)/avg` 階梯（+6…−6，clamp ±7） | L10 值 |
| sip_n04 | `sip_n04_trend_protect` | L1／L3 低於線（−5／−3） | L10 值 |
| sip_n01 | `sip_n01_bench_risk` | prior-10 平均 MIN <20:−5、<25:−3 | 分鐘 |
| b2b | `b2b_fatigue` | 球隊前日有賽（−2 主／−4 客） | 賽程 |
| home_away | `home_away` | 主客 PPG 分裂；缺值 fallback 主 +1／客 0 | 主客 |

## 2. 做法：用 live 函數算項，唔重寫項
- 每行調用 **live** `calc_adjusted_winprob`（EXP-02 已做），取回 `breakdown` 入面 7 個項嘅值（`t_*`）同 `base`。
- 每個 arm 嘅機率 = **live 組合公式**：`s = Σ(選中項)`；`s = max(s, −20)`（live −20 cap）；`p = clamp(base + s, 5.0, 98.0)`（live clamp）。呢兩行係唯一重寫嘅嘢（live 函數冇辦法只開部分項），**harness 強制 assert：全開 arm 同 live 回傳值逐行相同（EXP-02 嘅 `e` 欄）**，否則整個實驗作廢。
- **Reference ＝ all-off ＝ (a) live base**（未 clamp 嘅 `hit_L10`，同 EXP-02 一樣）。
- ⚠️ **Clamp confound**：任何有項嘅 arm 都會經過 live 5–98 clamp，而 (a) 冇；clamp 本身會改變 0%／100% 命中率嗰批嘅機率。為隔離，加 **arm `C0` ＝ 只 clamp、冇項**。判決規則按用戶要求對 (a)，但同時報對 `C0` 嘅差作敏感度（若兩者判決唔同，會明文標示）。

## 3. 預先登記嘅 arm（寫定，唔准再加）
共 **22 個**（相對 reference (a)）：
1. `ALL`：7 項全開（＝ EXP-02 候選 (e)）。
2. `C0`：只 clamp。
3. `ADD_x`（7 個）：base＋單項 x（x ∈ trend, cov, buffer, sip_n04, sip_n01, b2b, home_away）。
4. `LOO_x`（7 個）：全開減 x。
5. **4 個重疊 pair（add-both-to-base）**，因為兩項由同一組 L10 數值導出，懷疑重複計數同一訊號：
   - `P_trend_buffer`：trend＝`hit_L5−hit_L10`、buffer＝`(avg_L10−N)/avg`；兩者都係「近期相對線嘅位置」，而 base 本身就係 `hit_L10`，所以三者互相高度相關。
   - `P_trend_sip04`：trend 睇 L5 vs L10 命中率；sip_n04 睇 L1／L3 值 vs 線；同樣係「最近幾場表現」嘅兩個切法。
   - `P_buffer_sip04`：buffer 睇 L10 平均 vs 線；sip_n04 睇 L1／L3 vs 線；兩個都係「值低過線」嘅罰分。
   - `P_cov_buffer`：cov 同 buffer 都由 L10 平均／sd 導出（cov＝sd/avg），而「波動大」同「平均離線近」本質上係同一個不確定性嘅兩面。
- 理由寫喺度、**結果出咗之後唔准加／改 pair**。冇做三項以上組合（避免 2^n 搜索，`feature-ablation` 規矩）。
- 冇任何參數被擬合。dev 同 H2 **只用嚟睇符號一致性**，唔用嚟揀 arm 或調參。

## 4. 數據、切分、指標（同 EXP-02，凍結）
- Population：EXP-02 primary（MIN≥15 賽後過濾，≥10 prior，3 條最近 `m` 嘅整數線，`m≥1`）；同 S1 敏感度（prior-10 平均 MIN≥20）只報 pooled ADD／ALL。
- Dev：2025-26 日期 `<2026-01-01`；Gap：1 月；**H1：2025-26 `≥2026-02-01`（只評估一次）**；**H2：2024-25 整季**。
- 機率 clip `[0.01, 0.99]` 先計 Brier／log-loss；Brier、log-loss、逐 stat（PTS／REB／AST／3PM）同 pooled、logistic recalibration slope／intercept。
- 配對 bootstrap：cluster＝GAME_ID，**2000 次，seed 20261021**；報 `ΔBrier`、`Δlog-loss` 95% 百分位 CI。Holm 調整（跨 21 個 arm vs reference 嘅 H1 pooled ΔBrier）**只作額外資訊**。
- 確認 `rows.csv` 嘅舊欄位同 EXP-02 重建後逐值一致（determinism check）。

## 5. 預先登記嘅判決規則（逐項，唔准事後改）
對每項 x 用 `ADD_x` arm（H1 pooled，primary，對 reference (a)）：
- **harmful**：`ΔBrier` 95% CI **全部 > 0**，**且** dev 同 H2 嘅 `ΔBrier` 點估計亦 **> 0**。
- **helpful**：CI **全部 < 0**，**且** dev 同 H2 點估計 **< 0**。
- 否則 **no evidence**。
- 附加（描述性，**唔改判決**）：`LOO_x` 對 `ALL` 嘅 ΔBrier（移除 x 後點變）、逐 stat 結果、slope、對 `C0` 嘅 ΔBrier、S1 sensitivity、Holm p。
- **互動檢查**：報 `Σ_x ΔBrier(ADD_x)`（單項總和）對 `ΔBrier(ALL)`（聯合）嘅差，H1／dev／H2；同每個 pair 嘅 `ΔBrier(pair) − [ΔBrier(ADD_a) + ΔBrier(ADD_b)]`（bootstrap CI）。若 `ALL` 比單項總和差得多，且 pair 可解釋，就報告「互動／重疊」；解釋唔到就照講「解釋唔到」。
- **Clamp／cap 現實檢查（描述性）**：`ALL` arm 喺 dev／H1／H2 入面：`Σadj < −20`（cap 咬住）比例、`base+Σ < 5`（下 clamp）同 `> 98`（上 clamp）比例、`base ∈ {0,100}` 比例；每項非零比例同平均貢獻；`Σadj` 嘅平均／sd。

## 6. 重跑
（跑完後填）

## 7. 結果
（跑完後填）
