# EXP-20261021-03 NBA live 調整項逐項 ablation（邊項令機率更差？）

- **日期**：2026-10-21
- **平台**：NBA
- **假設**：EXP-20261021-02 發現「可由 game log 重現嘅 live 調整項合起嚟令 Brier 更差（+0.019，slope 0.41）」。本實驗問：**係邊幾項令佢更差？係單項本身有害，定係幾項由同一組 L10 數值導出、重疊計數（互動）？** 可證偽：若冇任何單項過預先登記嘅 `harmful` 條件，且單項效應總和 ≈ 聯合效應，就唔存在「某項有害」嘅證據。
- **搜索過嘅舊記錄**：EXP-20261021-02（本實驗前置；同 population／切分／bootstrap）。`grep -il nba docs/experiments/` 冇其他 NBA ablation。
- **改到嘅檔案／組件**：**冇改 production code。** 只喺 `docs/experiments/patches/nba_calibration_exp20261021_02/` 加 `nba_ablation.py`（同目錄，重用 EXP-02 harness），並喺 `nba_calib.py` 加（純增量）欄位 `t_*`＝live `calc_adjusted_winprob` 回傳嘅逐項 breakdown。
- **狀態**：✅ 已跑一次，結果記錄喺 §7。協議（§1–§5）喺計算任何結果前已 commit（`5199bdf6`），harness 喺跑真數據前已 commit（`ec047209`）。
- **決定**：**5 項 `harmful`（cov、buffer、sip_n04、sip_n01、b2b），2 項 `no evidence`（trend、home_away），0 項 `helpful`。NEEDS MORE TESTING —— 只係「後續 release experiment 候選」，唔係對 production 嘅建議。**

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
共 **20 個** arm（相對 reference (a)；原稿寫「22」係計錯數，列表內容冇變，亦無加減 arm）：
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
- 配對 bootstrap：cluster＝GAME_ID，**2000 次，seed 20261021**；報 `ΔBrier`、`Δlog-loss` 95% 百分位 CI。Holm 調整（跨 20 個 arm vs reference 嘅 H1 pooled ΔBrier）**只作額外資訊**。
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

環境：Python 3.9.6、numpy 2.0.2、pandas 2.3.3、scipy 1.13.1、nba_api 1.10.2；`PYTHONDONTWRITEBYTECODE=1`。
Repo commit（harness）：`ec0472093fd8ee5d63a2a2394bdc99c1dd3a4dc6`（`nba_calib.py` 只加 `t_*` 欄位）。Live code blob：`generate_nba_reports.py` `82ee97cc…`（冇改）。
Scratchpad：`/private/tmp/claude-501/-Users-imac-Antigravity-repo--claude-worktrees-nba-calibration-exp-56dc4c/1fa02346-3347-461b-80cf-3be02bd426e1/scratchpad/`
- raw：同 EXP-02（`raw/*.json` sha256 `43523d96…`／`320455e0…`）
- `out3/rows.csv` sha256 `dc5cb311a114869e4c51de628dffd4b61086252ec5402f9c9e06226aaacfcbb9`；`out3/results3.json` sha256 `7fc5140333187eb6d1e06881092d9bb3ec6db85ddf95f97e3bc408c0fc1c87e2`

```bash
export PYTHONDONTWRITEBYTECODE=1
H=docs/experiments/patches/nba_calibration_exp20261021_02; S=<scratchpad>
python3 -W ignore -m unittest discover -s $H -p "test_point_in_time.py"          # 5/5 OK
python3 -W ignore $H/nba_calib.py   build   --raw $S/raw --out $S/out3             # rows + t_* 欄位
python3 -W ignore $H/nba_ablation.py check  --old $S/out --out $S/out3             # determinism + ALL==live
python3 -W ignore $H/nba_ablation.py analyse --out $S/out3                         # 只跑一次
```
`check` 通過：舊欄位同 EXP-02 `rows.csv` 逐值一致（366,972 行）；`ALL` arm（用 live 組合公式由 `t_*` 重組）同 live 回傳值 `e` 逐行一致；7 項以外嘅 live 項（pace、minutes_floor…）全部 = 0。

## 7. 結果（primary population；pooled；ΔBrier ＝ arm − (a)，95% CI 來自 GAME_ID cluster bootstrap 2000 次）

### 7.1 逐項判決（`ADD_x`＝ base 加單項；預先登記規則）
| 項 | dev ΔBrier | **H1 ΔBrier [95% CI]** | H2 ΔBrier | 對 `C0` 嘅 H1 差 | slope H1 | **判決** |
|---|---|---|---|---|---|---|
| trend | +0.0005 | −0.0001 [−0.0006, +0.0004] | +0.0002 | +0.0000 [−0.0005, +0.0006] | 0.55 | **no evidence** |
| cov | +0.0062 | **+0.0077** [+0.0070, +0.0085] | +0.0074 | +0.0079 | 0.53 | **harmful** |
| buffer | +0.0026 | **+0.0029** [+0.0026, +0.0032] | +0.0031 | +0.0030 | 0.48 | **harmful** |
| sip_n04 | +0.0020 | **+0.0020** [+0.0016, +0.0024] | +0.0023 | +0.0021 | 0.55 | **harmful** |
| sip_n01 | +0.0033 | **+0.0043** [+0.0039, +0.0048] | +0.0039 | +0.0044 | 0.53 | **harmful** |
| b2b | +0.0003 | **+0.0006** [+0.0003, +0.0008] | +0.0005 | +0.0007 | 0.57 | **harmful（極細）** |
| home_away | −0.0001 | −0.0001 [−0.0004, +0.0001] | −0.0002 | +0.0000 [−0.0002, +0.0002] | 0.57 | **no evidence** |

- Reference (a) H1：slope 0.545、mean p − mean y = −0.031。`C0`（只 clamp 5–98）ΔBrier = −0.0001（三個窗口）→ **clamp confound 可以忽略，判決對 (a) 同對 `C0` 一樣。**
- 0 項 `helpful`。
- Holm（20 個 arm，H1 pooled Brier，只作資訊）：cov／buffer／sip_n04／sip_n01／b2b 全部 0.010；trend 0.69、home_away 0.65。**結論唔變。**
- `harmful` 嘅幅度差好遠：cov（+0.0077）同 sip_n01（+0.0043）佔大頭；b2b（+0.0006）喺 dev 嘅 CI 下限剛好貼住 0，屬「統計上有、實質上細」。
- 逐 stat（H1 `ADD_x` ΔBrier）：cov 全部 4 個 stat 都顯著正（PTS +0.0118、REB +0.0088、AST +0.0057、3PM +0.0026）；buffer 全部正（+0.0017～+0.0036）；sip_n01 全部正（PTS +0.0072）；sip_n04 PTS +0.0034／REB +0.0024／AST +0.0011／3PM +0.0005（CI 跨 0）；b2b 只 PTS（+0.0013）同 REB（+0.0005）顯著；trend 喺 PTS 負（−0.0012 [−0.0022, −0.0002]）、3PM 正（+0.0012），互相抵消；home_away 只 PTS 有細幅負（−0.0005）。**呢啲逐 stat 係描述性**（判決只睇 pooled）。

### 7.2 `LOO_x`（全開減 x）對 `ALL`（描述性）
H1 ΔBrier（負＝移走 x 令 `ALL` 變好）：cov **−0.0086**、sip_n01 **−0.0049**、sip_n04 **−0.0038**、buffer **−0.0025**、b2b **−0.0010**；trend **+0.0028**、home_away **+0.0007**（移走令 `ALL` 更差）。dev／H2 同號、CI 全部同 0 同側。
即係喺**已經有其他項**嘅情況下，trend 同 home_away 係「用嚟抵消其他項負偏」，而唔係自己有預測力（`ADD_` 時冇效果）。

### 7.3 互動檢查
| | dev | H1 | H2 |
|---|---|---|---|
| 單項總和 Σ ΔBrier(ADD_x) | +0.0147 | +0.0173 | +0.0171 |
| 聯合 ΔBrier(ALL) | +0.0165 | **+0.0190** | +0.0185 |
| 聯合 − 總和（CI） | +0.0018 [+0.0014, +0.0021] | +0.0018 [+0.0015, +0.0020] | +0.0014 [+0.0013, +0.0016] |

- **≈ 91% 嘅害處係加法（單項總和）；互動只係額外 ~0.0018（≈ 9%）**，雖然 CI 全正但實質細。
- 4 個重疊 pair（H1，`pair − (ADD_a + ADD_b)`）：trend+buffer **−0.0002**（輕微次加法）、trend+sip_n04 +0.0003、buffer+sip_n04 +0.0007、cov+buffer +0.0004（全部 CI 窄、`|效應| ≤ 0.0007`）。所以「由同一組 L10 數值導出、重複計數」**喺統計上存在，但只解釋到 ≤ 0.0007 級**，唔係 `ALL` 嘅主因；我冇用 pair 去解釋晒 0.0018（pair 成員互相重疊，唔可以直接相加）。
- **實質主因係單項各自帶負偏**：reference 本身已經低估 3pp（mean p − mean y = −0.031），而 live 項大多只減唔加（`cov` 87% 行為負、平均 −4.7pp；`sip_n04` 60% 行 −2.3pp；`sip_n01` 平均 −1.6pp；`b2b` 全部 ≤0），`Σadj` H1 平均 **−7.7pp**（sd 8.7）→ `ALL` 嘅 mean p − mean y 變成 **−0.100**（`ADD_cov` −0.076、`ADD_sip_n04` −0.053）。`trend`／`buffer`／`home_away` 有正有負，抵消一部分，所以 `LOO_trend`、`LOO_home_away` 反而令 `ALL` 更差。**呢段係描述性機制解釋，唔係預先登記嘅檢定。**
- 單項總和 vs 聯合（H1 per stat）：PTS 0.0237→0.0249、REB 0.0206→0.0219、AST 0.0130→0.0150、3PM 0.0080→0.0112（3PM 互動比例最大）。

### 7.4 Clamp／cap 現實檢查（`ALL` arm，primary，描述性）
| 窗 | n | `Σadj < −20`（cap 咬） | `base+Σ < 5`（下 clamp） | `> 98`（上 clamp） | base∈{0,100} | `Σadj` 平均 (sd) |
|---|---|---|---|---|---|---|
| dev | 53,322 | 7.4% | 5.1% | 1.8% | 2.2% | −7.2 (8.8) |
| H1 | 84,783 | 8.1% | 5.2% | 1.4% | 2.0% | −7.7 (8.7) |
| H2 | 176,430 | 7.4% | 5.2% | 1.5% | 2.0% | −7.4 (8.8) |

約 **7–8% 行被 −20 cap 截**、約 **5% 行被 5% 下限截**。所以加法項喺幾個百分比嘅行會失去線性（cap 令最多人罰嘅行唔再多罰）。**Clamp 本身冇傷 Brier**（`C0` −0.0001），但改善 log-loss（`C0` −0.0034，因為避免 0%／100%；`ADD_` arm 嘅 log-loss 差包含呢個）——所以我哋嘅判決用 Brier，唔用 log-loss。
各項非零比例（H1）：cov 91%、buffer 80%、home_away 71%、sip_n04 60%、trend 55%、sip_n01 42%、b2b 18%。

### 7.5 S1 敏感度（prior-10 平均 MIN≥20，賽前可知；只報 pooled，唔參與判決）
H1 `ADD_x` ΔBrier：trend +0.0016、cov +0.0023、buffer +0.0021、sip_n04 −0.0002、sip_n01 +0.0000、b2b −0.0001、home_away +0.0003（CI 全正者：trend、cov、buffer、home_away；dev／H2 同號）。`ALL` +0.0085（單項總和 +0.0060，聯合 − 總和 +0.0025）。
**定性一致**：cov、buffer 有害；sip_n01 喺 S1 冇效果係預期（prior-10 平均 ≥20 分鐘，bench 罰分只喺 20–25 分鐘先觸發，S1 入面 25% 行非零）。**但判決有兩處唔同**：sip_n04、b2b 喺 S1 變 `no evidence`；trend、home_away 喺 S1 變細幅 `harmful`。即係 **trend／home_away／sip_n04／b2b 嘅判決依賴 population**，唔好當成穩定結論；cov、buffer 兩個 population 都一致有害。

## 8. 呢個實驗講到乜、講唔到乜
**講到（喺本 population）**
1. 可重現 live 項之中，**cov 同 sip_n01（bench 分鐘）貢獻最大害處**，buffer、sip_n04 次之，b2b 極細；trend、home_away 單獨冇可測效應。冇任何一項有 `helpful` 證據。
2. 全部害處**主要係加法、唔係重複計數互動**（單項總和 ≈ 聯合嘅 91%）。呢個同我哋喺 §3 嘅「重疊」假設唔完全相符：重疊 pair 效應只有 ≤0.0007。主導嘅係「大部分項只減、reference 又已經略低估」造成嘅系統性負偏。
3. 喺 reference 本身 slope 只有 0.55 嘅情況下（EXP-02），**呢啲項冇一項令 slope 變好**（ADD arm slope 0.48–0.57 vs 0.545；trend／home_away 無實質差別）。即係佢哋冇修復過度自信。

**講唔到**
- **完全冇講利潤／EV，亦冇用賠率**；線係「L10 平均附近 3 個整數」，唔係莊家開價母體（莊家同樣會 shade）。
- 只量得 7 項。live 仲有 spread（minutes_floor）、對手 pace／防守、matchup_pace、USG／傷兵、ML hybrid、playoff guard，呢度恆為 0；有呢啲輸入時 live 嘅 `Σadj` 分佈、cap 咬住比例都會唔同，上面嘅結論**唔可以外推去完整 live 機率**。
- 項之間嘅關係用 add-one／leave-one-out／4 個預先登記嘅 pair 量；**冇做**三項或以上組合（避免 2^n），所以高階互動（例如 trend+buffer+sip_n04 三重）冇量。
- 判決用 pooled Brier；逐 stat 結果唔一致（trend、b2b、home_away 係 stat 依賴），冇做 stat 分層嘅判決。
- 只常規賽，2025-26 + 2024-25；季後賽 phase 項（playoff_guard、SIP 嘅季後賽版）冇數據。
- 「機制解釋」（負偏）係描述性觀察，唔係預先登記檢定。
- **冇建議改 production。** 以上最多係「後續 release experiment 嘅候選」：任何移除或重調 live 項，必須係獨立、用戶批准、並通過 `model-regression-gate` 嘅改動，而且要用真 line 母體（forward snapshot）而唔係本 population 去驗。

## 9. 建議下一步（唔喺本實驗內做）
1. 用 forward snapshot（排程自 2026-10-21 起）累積真 line 母體，再重做 ADD／LOO，睇 cov、sip_n01 嘅害處係咪喺莊家實際開價嘅線上仍然成立。
2. Calibration layer 實驗（EXP-02 §7 第 1 項）：而家知道負偏嘅主要來源，可以先做「只修 mean 偏差」嘅最簡單版本，睇 slope 會唔會順便改善。
3. 若要檢視 `cov`／`sip_n01` 嘅「應該罰幾多」：要擬合而唔係移除；須喺新協議內，dev 擬合、H1／H2 一次確認。
