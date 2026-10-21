# EXP-20261021-02 NBA 球員 prop 機率校準度量（只用公開 game log、嚴格時間切分）

- **日期**：2026-10-21
- **平台**：NBA
- **假設**：live 引擎核心腿機率（L10 命中率 `hit_rate` + 加減調整項）喺「剛好圍住球員 L10 平均」嘅 milestone 線上校準唔好；至少一個簡單替代（season-to-date 收縮、Poisson/NB、live MC 公式）可以喺 holdout 顯著降低 Brier。**呢個假設可以被證伪：** 若 holdout 冇任何候選嘅 Brier 差 CI 全部喺 0 下面，結論就係「未證明更好」。
- **搜索過嘅舊記錄**：`grep -il nba docs/experiments/` → 只有 `_TEMPLATE.md`、EXP-20261014-01（Evidently drift，無關）、EXP-20261015-02（AU，無關）。EXP-20261021-01（NBA ML train/serve parity）喺另一條 branch，未 merge，睇唔到。冇任何 NBA 校準研究。
- **改到嘅檔案／組件**：**冇改 production code。** 只新增 harness `docs/experiments/patches/nba_calibration_exp20261021_02/`。
- **狀態**：🔵 協議已寫（未跑結果）—— 此節以下「協議」喺計算任何結果前 commit。結果見文末「結果」節（跑完先填）。

> ⚠️ **最大限制（先睇）**：本實驗選嘅線係「最近 L10 平均嘅 3 個最近整數」，唔係莊家實際開價嘅 milestone 母體（莊家喺成個範圍開價，並且會 shade）。所以量度嘅係 **機率引擎自己嘅校準度**，**完全冇講過落注有冇利潤**。亦冇用賠率。

## 1. live 引擎實際做咗乜（STEP 1，讀 code 所得）

來源：`.agents/skills/nba/nba_wong_choi/scripts/generate_nba_reports.py`（`hit_rate`、`calc_adjusted_winprob`、call site ~L594-612）同 `monte_carlo_nba.py`。

**Base（核心腿機率 `base_rate`）**
- `hit_rate(data, N)`：`data` = 球員最近 ≤10 場（newest-first）該 stat 值；命中 = `x >= N`（milestone「N+」）。`pct = round(hits/len(data)*100, 1)`。
- 10 場 → 步長 **10pp**（0,10,…,100）；`data` 少過 10 場時步長唔同、分母跟 `len(data)`。冇 cap、冇 shrink、冇 Laplace。`0%`、`100%` 照出。
- 同一個 call site 亦算 `hr_l5`（最近 5 場同一條線）、`hr_l3`。

**調整項（`calc_adjusted_winprob`，加法，單位 pp）** `adjusted = clamp(base + Σadj, 5.0, 98.0)`，`Σadj` 下限 −20。
| 項 | 輸入 | 可由 game log 重現？ |
|---|---|---|
| trend | `hr_l5 − base`（≥20:+8, ≥10:+5, ≥−10:0, ≥−20:−5, else −8） | ✅ |
| cov | L10 母體 sd/avg（≤.15:+6, ≤.25:+3, ≤.35:0, ≤.45:−3, else −6） | ✅ |
| buffer | `(avg−N)/avg`（±6 階梯，clamp ±7；`amc=0`） | ✅ |
| sip_n04（L1/L3 低於線） | L10 newest-first | ✅ |
| sip_n01（bench 分鐘 <20:−5, <25:−3） | prior-10 平均 MIN | ✅ |
| b2b_fatigue（−2 主 / −4 客） | 球隊前一日有賽 | ✅（由全聯盟 log 推賽程） |
| home_away | live 用 season home/road **PPG** 比；缺值 fallback：主 +1／客 0 | ⚠️ 部分：用 prior 同季 PTS 主/客平均重現（各 ≥3 場，否則 fallback） |
| minutes_floor | 賽前 spread（blowout） | ❌ 冇 spread |
| pace、opp_defense、matchup_pace | 對手 pace／防守排名 | ❌ 唔喺 game log |
| usg_shift（傷兵 USG 轉移） | 傷兵名單 | ❌ |
| playoff_guard | 季後賽 | N/A（只常規賽，MID_SEASON） |
| ML hybrid（`ml_predictor`） | ML 模型 | ❌ **out of scope**（AUC 0.939 已判洩漏，無效）|

❌ 嗰啲喺 live 缺值時本身就係 0，所以 candidate (e) 喺「呢啲項冇資料」情況下同 live 行為一致，但**唔代表**有完整 context 時嘅 live 機率。

**live Monte Carlo（`monte_carlo_player_prop`）**：live call 冇傳 `season_avg`／`l20_avg`，所以 shrinkage 實際關閉（`proj_avg = L10 avg`）。PTS/REB/AST：截尾常態 `N(avg, sd)`（sd = L10 母體 sd；sd≤0 → 0.15·avg），命中 = `v >= N − 0.5`（continuity correction）；3PM：beta-binomial（`attempts = max(3, round(mean/0.36))`）。10,000 次抽樣。Context 因子冇資料時 =1。Candidate (f) 用**解析式**（無抽樣噪音）重現：常態 `sf(N−0.5)` 同 `scipy.stats.betabinom`；另抽樣核對解析式 vs 真 MC 函數。

## 2. 數據（STEP 2）

- 來源：`nba_api` `LeagueGameLog(player_or_team_abbreviation='P', season_type='Regular Season')`，2025-26 同 2024-25 各一個 call，0.8s sleep + retry；raw JSON 留 scratchpad，sha256 記喺結果節。
- 欄位：PLAYER_ID/NAME、TEAM_ABBREVIATION、GAME_ID、GAME_DATE、MATCHUP（`vs.`＝主、`@`＝客）、MIN、PTS、REB、AST、FG3M。
- **Data-quality（在看任何結果之前已核對，全部係結構性檢查）**：
  | | 2025-26 | 2024-25 |
  |---|---|---|
  | 行數 | 26,651 | 26,306 |
  | 日期範圍 | 2025-10-21 → 2026-04-12 | 2024-10-22 → 2025-04-13 |
  | 場數（GAME_ID） | 1,230 | 1,230 |
  | 重複 (PLAYER_ID,GAME_ID) | 0 | 0 |
  | MIN 缺失 / MIN==0 | 0 / 83 | 0 / 100 |
  | 每場唔係 2 隊 | 0 | 0 |
  兩季都完整常規賽，只有常規賽（無季後賽／Play-In）。MIN 係整數分鐘。`MIN==0` 當**冇上場**，丟棄（live 用嘅 PlayerGameLog 亦唔列 DNP）。
- 所有 raw 同中間檔留 scratchpad，唔入 repo。

## 3. 協議（STEP 3 —— 計結果之前凍結）

### 3.1 Unit 同 point-in-time
- 一個 unit = 一個球員一場 `g`（日期 `D`，季 `S`），而同時：(i) `MIN_g ≥ 15`；(ii) 同季、**日期嚴格早於 `D`** 嘅出場數 ≥ 10。
- **所有 feature 只准用「同季、日期 < D」嘅出場**（唔係 ≤，唔係以 index 為準）。L10 = 最近 10 場（newest-first），season-to-date = 全部。**Prior-season carryover：無**（每季頭 10 場出場前嘅 unit 唔入樣本）。
- Leakage 檢查（寫入 harness）：(1) 單元測試 `test_point_in_time.py`：同日／未來場次必須唔入 features，改動同日或之後嘅 stat 值，feature 唔准變；(2) 運行時 assert：每個 unit 用到嘅每個 prior 場 `date < D`；(3) shuffle test：將 `y` 喺同一 stat 嘅 dev units 之間全局隨機置換（固定 seed），所有候選嘅 Brier 必須掉到 ≈ 沒有技巧嘅水平（slope ≈ 0），否則報 LEAK。
- ⚠️ **已知選擇偏差（保留用戶規格但標明）**：`MIN_g ≥ 15` 用咗**賽後**嘅出場時間做過濾 —— 賽前拎唔到（受傷提早離場、blowout 都會被剔走），會令命中率輕微偏高。故加 **敏感度分析 S1（非判決）**：唔用 `MIN_g` 過濾，改用賽前可知嘅「prior-10 平均 MIN ≥ 20」。S1 只報告，唔參與判決。

### 3.2 Stats 同線
- Stats：PTS、REB、AST、FG3M（3PM）。
- Eligibility：該 stat 嘅 prior-10 平均 `m ≥ 1.0`。
- 線：`N` 為整數、`N ≥ 1`，outcome = `stat ≥ N`。選 **3 個最近 `m` 嘅整數**（按 `|N−m|` 升序，tie 取較細 N）。紀錄 `rel = N − m` 同 `rel/m`。線選擇只用 `m`，同候選無關。
- 每個 unit×stat 因此有 3 行；同一場嘅所有行（兩隊所有球員）係同一個 **cluster = GAME_ID**。

### 3.3 候選
| ID | 定義 | 參數／tune |
|---|---|---|
| **(a) REFERENCE = live base** | `hit_rate(L10, N)/100`，**直接調用 live 函數**（import 原檔，唔另寫） | 無 |
| (b) | `w·hit_L10 + (1−w)·hit_season_to_date`（同一條線） | `w ∈ {0,0.05,…,1}`，**每 stat 一個，只喺 dev 按 Brier 揀**，tie 取較細 w |
| (c) | Poisson（REB/AST/3PM）、NegBin（PTS）；`μ = rate_season × projMIN`，`rate_season = Σstat/ΣMIN`（同季 prior 全部），`projMIN = prior-10 平均 MIN`；`P(X≥N)` | NB 嘅 `α`（Var=μ+αμ²）只喺 dev units 用 MLE（一個 unit 一個 obs，唔係每線）。**註：** 若 rate 用 prior-10 計，則 `rate×projMIN` 恆等於 prior-10 平均 stat（退化），故特意用 season rate。 |
| (d) trivial | `hit_season_to_date`（同一條線） | 無 |
| (e) 探索 | live base + **可重現嘅 live 調整項**（見 §1 表），調用 live `calc_adjusted_winprob`，不可重現嘅輸入用 live 缺值預設 | 無 |
| (f) 探索 | live MC 公式（解析式，無 shrinkage，MID_SEASON） | 無 |

- **Reference 預先定為 (a)**（因為係 live 實際行嘅 base）。(e)(f) 標為「探索」：同樣套用判決規則，但報告時註明一共 5 個候選 vs reference，即係有多重比較；再另外列 Holm 調整後結論（**唔改判決規則，只係額外資訊**）。
- 所有機率 clip 到 `[0.01, 0.99]` 先計 Brier 同 log-loss（(a) 嘅 0%/100% 否則 log-loss 無限）。呢個 clip 對所有候選一樣。

### 3.4 切分
- **dev**：日期 `< 2026-01-01`（2025-26）。**gap**：2026-01-01 至 2026-01-31（unit 唔入任何評估，但可作 feature 歷史）。**holdout H1**：日期 `≥ 2026-02-01`（2025-26，至季末）。**只跑一次確認，唔准用嚟調參。**
- **H2（第二個獨立 holdout）**：2024-25 整季（滿足 ≥10 prior 出場嘅 unit）。只用 2025-26 dev 嘅 tuned 參數（`w`、`α`）去算，唔做任何 tuning。H2 喺時間上係**倒退**（早過 dev），所以係「跨季穩健性」，唔係前瞻驗證。

### 3.5 指標
- 每候選、每 stat、同 pooled（所有 stat 平均於所有 units）：Brier、log-loss、10 桶 reliability（桶界 0.1 等寬，報 n、mean p、mean y）、logistic recalibration `logit(P(y=1)) = a + b·logit(p)` 嘅 **slope b、intercept a**，同 calibration-in-the-large（mean p − mean y）。
- 配對 bootstrap：以 GAME_ID 為 cluster 重抽（**2000 次**，seed 固定 20261021），報 `Brier_cand − Brier_ref`、`logloss_cand − logloss_ref` 嘅 95% 百分位 CI。Slope 另報 bootstrap CI（300 次，只作資訊）。

### 3.6 預先登記嘅判決規則（唔准事後改）
一個候選只有喺**同時**滿足以下三點先叫 **「better」**，否則 **「not shown better」**：
1. H1 pooled `Brier_cand − Brier_ref` 嘅 95% CI **全部 < 0**；
2. dev 同一差值嘅**符號同為負**（點估計 < 0）；
3. 候選喺 H1 pooled 嘅 calibration slope ∈ **[0.85, 1.15]**。

- Headline 用 **pooled**；per-stat 同一規則逐 stat 報告（描述性，唔改 headline）。
- 同時註明 reference 本身嘅絕對校準：slope／intercept 點估計同 CI，用嚟答「(a) 校準得好唔好」（**描述性，唔係判決**；若 slope 明顯 <1 即過度自信）。
- 唔准改指標、窗口、線選擇、clip、桶數、bootstrap 次數去救候選。想換設計 → 開新實驗。
- 唔准用結果決定任何 production 改動。就算有「better」，都只係「值得喺真 line 母體再測」。

## 4. 重跑
（跑完後填）

## 5. 結果
（跑完後填）
