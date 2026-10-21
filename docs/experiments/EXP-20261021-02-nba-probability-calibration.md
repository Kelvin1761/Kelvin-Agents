# EXP-20261021-02 NBA 球員 prop 機率校準度量（只用公開 game log、嚴格時間切分）

- **日期**：2026-10-21
- **平台**：NBA
- **假設**：live 引擎核心腿機率（L10 命中率 `hit_rate` + 加減調整項）喺「剛好圍住球員 L10 平均」嘅 milestone 線上校準唔好；至少一個簡單替代（season-to-date 收縮、Poisson/NB、live MC 公式）可以喺 holdout 顯著降低 Brier。**呢個假設可以被證伪：** 若 holdout 冇任何候選嘅 Brier 差 CI 全部喺 0 下面，結論就係「未證明更好」。
- **搜索過嘅舊記錄**：`grep -il nba docs/experiments/` → 只有 `_TEMPLATE.md`、EXP-20261014-01（Evidently drift，無關）、EXP-20261015-02（AU，無關）。EXP-20261021-01（NBA ML train/serve parity）喺另一條 branch，未 merge，睇唔到。冇任何 NBA 校準研究。
- **改到嘅檔案／組件**：**冇改 production code。** 只新增 harness `docs/experiments/patches/nba_calibration_exp20261021_02/`。
- **狀態**：✅ 已跑一次，結果記錄喺 §5。協議（§1–§3）喺計算任何結果前已 commit（`72be0661`），harness 喺跑真數據前已 commit（`35c2f2f8`）。
- **決定**：**全部候選＝「not shown better」（按預先登記規則）；而 reference（live base）本身嚴重過度自信（slope ≈ 0.55）。NEEDS MORE TESTING（見 §6）。唔係對 live 模型嘅任何改善聲稱。**

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

環境：Python 3.9.6（macOS system）、numpy 2.0.2、pandas 2.3.3、scipy 1.13.1、nba_api 1.10.2；`PYTHONDONTWRITEBYTECODE=1`。
Repo commit（harness）：`35c2f2f8ccc29e2ea5b7beb6719f73afb4219264`（結果檔由呢個 commit 嘅 code 產生）。
Live code blob hash（唯讀 import，冇改）：`generate_nba_reports.py` `82ee97cc…`、`monte_carlo_nba.py` `5b6d91ce…`（`git hash-object`）。

Scratchpad（raw + 中間檔，唔入 repo）：`/private/tmp/claude-501/-Users-imac-Antigravity-repo--claude-worktrees-nba-calibration-exp-56dc4c/1fa02346-3347-461b-80cf-3be02bd426e1/scratchpad/`
- `raw/leaguegamelog_P_2025-26.json` sha256 `43523d9699e848913754edec4e8504cd5f602a78d7e3462bb1b82e0290f986a6`（26,651 行）
- `raw/leaguegamelog_P_2024-25.json` sha256 `320455e052599988d11342b4871c53450314453a5298da8df2a4f8cff7cd1f8a`（26,306 行）
- `out/rows.csv` sha256 `ed4dd3805129f260184fbb2cb36dec50f7e72f9e9c2eab67c905d3de9c855def`（366,972 行 = unit×stat×line，兩季）
- `out/results.json` sha256 `03ddf4a0a5a1074501879da08131912631dc5f9da681de206836b3e68d8d2213`

```bash
export PYTHONDONTWRITEBYTECODE=1
H=docs/experiments/patches/nba_calibration_exp20261021_02
S=<scratchpad>
# 1. 抽取（nba_api LeagueGameLog，兩季，0.8s sleep + retry；fetch 腳本等同：
#    leaguegamelog.LeagueGameLog(season=<s>, season_type_all_star="Regular Season", player_or_team_abbreviation="P")）
# 2. 單元測試（point-in-time）
python3 -W ignore -m unittest discover -s $H -p "test_point_in_time.py"
# 3. 解析式 live-MC 對真 MC 核對
python3 -W ignore $H/nba_calib.py validate-mc
# 4. 建 feature 行，跑分析（只跑咗一次）
python3 -W ignore $H/nba_calib.py build   --raw $S/raw --out $S/out
python3 -W ignore $H/nba_calib.py analyse --out $S/out
```
注：`analyse` 一次過行 primary 同 S1 兩個 population；H1 只評估一次、冇用嚟調參（參數只喺 dev 擬合）。

## 5. 結果

### 5.0 完整性檢查
- 單元測試 5/5 pass（嚴格 `<`、同日唔入、改 outcome 唔郁任何 feature、≥10 prior、線選擇只靠 `m`）。
- **Shuffle test（dev，primary）**：將 `y` 喺同 stat 內全局置換後，所有候選 slope = a 0.008／b 0.010／c 0.007／d 0.009／e 0.010／f 0.011（≈0）→ **冇發現洩漏**。（S1：0.010–0.027，同樣 ≈0。）
- 解析式 live-MC (f) 對真 `monte_carlo_player_prop`（n=100,000，8 個 avg/sd/line 組合）最大差 0.0037（真 MC 輸出四捨五入到 0.1%，差異喺抽樣噪音＋rounding 量級）。
- 樣本：primary dev 53,322 行／351 場；H1 84,783 行／501 場；H2 176,430 行／1,085 場。線位置：`N−m` 平均 +0.07（sd 0.90），即線圍住平均略偏上。總命中率 0.555（dev）／0.562（H1）／0.564（H2）。
- Tuned（只用 dev）：(b) `w`（L10 權重）PTS 0.40、REB 0.30、AST 0.30、3PM 0.15；(c) NB `α(PTS)=0.205`，其餘 Poisson。

### 5.1 判決（primary、pooled、H1；預先登記規則）
| 候選 | H1 ΔBrier vs (a)，95% CI | dev ΔBrier | H1 slope [CI] | 條件1 CI<0 | 條件2 dev 同號 | 條件3 slope∈[.85,1.15] | **判決** |
|---|---|---|---|---|---|---|---|
| (b) 收縮 L10↔season | −0.0072 [−0.0085, −0.0059] | −0.0052 | 0.746 [0.72, 0.77] | ✅ | ✅ | ❌ | **not shown better** |
| (c) Poisson／NB | −0.0126 [−0.0140, −0.0112] | −0.0114 | 0.769 [0.75, 0.79] | ✅ | ✅ | ❌ | **not shown better** |
| (d) season hit rate | −0.0024 [−0.0044, −0.0004] | −0.0041 | 0.648 [0.62, 0.67] | ✅ | ✅ | ❌ | **not shown better** |
| (e) base＋可重現調整項 | **+0.0190** [+0.0175, +0.0205] | +0.0165 | 0.412 [0.40, 0.43] | ❌（更差） | ❌ | ❌ | **not shown better（顯著更差）** |
| (f) live MC 公式 | −0.0107 [−0.0116, −0.0098] | −0.0091 | **0.840** [0.82, 0.86] | ✅ | ✅ | ❌（點估計 0.840，差 0.01） | **not shown better（臨界）** |

- 條件 3 按預先登記用 **點估計**；(f) 0.840 而 CI [0.82, 0.86] 包住 0.85，所以係臨界；規則冇改。
- 多重比較：5 個候選 vs (a)，bootstrap p（2000 次，地板 1/2001=0.0005）；Holm 調整後，(b)(c)(e)(f) 仍 0.0025、(d) 0.018，**結論唔變**。
- H2（2024-25，獨立）同 dev／H1 方向全部一致：ΔBrier (b) −0.0077、(c) −0.0128、(d) −0.0053、(e) **+0.0185**、(f) −0.0103（CI 全部同 0 同側）；slope：a 0.553、b 0.746、c 0.795、d 0.687、e 0.412、f 0.843。

### 5.2 Reference（a）= live base 本身校準得幾好（描述性）
| 窗 | Brier | log-loss | slope（理想 1） | intercept | mean p − mean y |
|---|---|---|---|---|---|
| dev | 0.2320 | 0.6638 | 0.576 | +0.135 | −0.020 |
| H1 | 0.2348 | 0.6703 | **0.545 [0.53, 0.56]** | +0.178 | −0.031 |
| H2（2024-25） | 0.2347 | 0.6692 | **0.553 [0.54, 0.56]** | +0.173 | −0.030 |

（對照：全部線都喺 L10 平均附近，真命中率 ≈ 0.55–0.56，Brier 0.25 = 永遠講 0.5。）

H1 pooled reliability（桶＝0.1 等寬，n／mean p／實際命中率）：
| 桶 | (a) live base | (c) Poisson/NB | (f) live MC |
|---|---|---|---|
| 0–.1 | 472／0.01／**0.225** | 1,241／0.069／0.191 | 534／0.060／0.245 |
| .1–.2 | 1,830／0.10／0.238 | 3,773／0.156／0.261 | 1,464／0.153／0.261 |
| .2–.3 | 4,069／0.20／0.337 | 7,882／0.256／0.354 | 3,259／0.256／0.282 |
| .3–.4 | 8,603／0.30／0.420 | 13,046／0.353／0.433 | 8,066／0.357／0.365 |
| .4–.5 | 14,433／0.40／0.490 | 15,976／0.450／0.512 | 16,812／0.452／0.456 |
| .5–.6 | 17,154／0.50／0.532 | 14,136／0.548／0.584 | 21,894／0.547／0.551 |
| .6–.7 | 15,135／0.60／0.604 | 10,543／0.648／0.669 | 15,792／0.647／0.659 |
| .7–.8 | 10,704／0.70／0.671 | 8,939／0.748／0.745 | 10,057／0.746／0.744 |
| .8–.9 | 7,164／0.80／0.743 | 7,237／0.846／0.829 | 5,579／0.842／0.809 |
| .9–1 | 5,219／0.921／0.817 | 2,010／0.927／0.912 | 1,326／0.934／0.849 |

(a) 講 0.01（clip 後；L10 一次都冇過線）嘅時候實際有 **22.5%**；最高桶（平均 0.92，包含 9/10 同 10/10 過線）實際只得 **81.7%**。典型「過度自信」形狀：10 場樣本嘅命中率噪音（SE ≈ 0.16）直接當機率用。

### 5.3 H1 per-stat（primary）
| Stat | (a) Brier | (a) slope | (c) ΔBrier [CI] | (c) slope | (f) ΔBrier [CI] | (f) slope | (e) ΔBrier [CI] |
|---|---|---|---|---|---|---|---|
| PTS | 0.2576 | **0.162** [0.10, 0.22] | −0.0107 [−0.0136, −0.0078] | 0.759 | −0.0165 [−0.0183, −0.0146] | 0.847 | +0.0249 [+0.0225, +0.0271] |
| REB | 0.2344 | 0.527 | −0.0167 [−0.0189, −0.0144] | 0.775 | −0.0109 [−0.0122, −0.0095] | 0.754 | +0.0219 [+0.0198, +0.0238] |
| AST | 0.2247 | 0.587 | −0.0110 [−0.0132, −0.0086] | 0.764 | −0.0076 [−0.0089, −0.0063] | 0.744 | +0.0150 [+0.0130, +0.0169] |
| 3PM | 0.2140 | 0.622 | −0.0117 [−0.0141, −0.0094] | 0.823 | −0.0057 [−0.0073, −0.0041] | **1.204** [1.16, 1.26] | +0.0112 [+0.0090, +0.0133] |

PTS 嘅 live base 幾乎冇資訊（slope 0.16，Brier 0.2576 **差過永遠講 0.5 嘅 0.25**）。(b)(d) per-stat 見 `results.json`；(d) 喺 PTS 同 AST 冇顯著差（CI 跨 0）。

### 5.4 敏感度 S1（賽前可知過濾，唔參與判決）
Unit＝prior-10 平均 MIN ≥ 20（唔用賽後 MIN）。H1 pooled：(a) Brier 0.2348／slope 0.569；ΔBrier：(b) −0.0086、(c) −0.0127、(d) −0.0052、(e) **+0.0085**、(f) −0.0059；slope：(b) 0.752、(c) 0.789、(d) 0.667、(e) 0.446、(f) 0.847。**方向同 primary 完全一致**，所以 `MIN_g ≥ 15` 賽後過濾冇改變結論。S1 嘅 (e) 劣勢細啲（+0.0085 vs +0.0190）。

## 6. 呢個實驗講到乜、講唔到乜

**講到（喺本實驗嘅 population：線圍住 L10 平均嘅常規賽 player-game）**
1. live **base**（L10 命中率，10pp 步長）嘅機率**系統性過度自信**：slope ≈ 0.55，跨兩個獨立窗口（2025-26 H1、2024-25）穩定，唔係某個窗口嘅運氣。PTS 幾乎冇資訊。
2. 所有候選（收縮、Poisson/NB、live MC 公式）喺 Brier／log-loss 都**顯著優於** base（H1 −0.007 至 −0.013），而且三個窗口方向一致。**但喺預先登記嘅 slope 條件下冇一個「過關」**（全部 slope < 0.85，(f) 0.840 差一線），所以按規則 = 「not shown better」。呢個結果要誠實咁讀：Brier 贏係真，但「校準好」嘅標準冇達到，連 Poisson 都仍然過度自信（0.77）。
3. **我哋可以重現嘅 live 調整項（trend／cov／buffer／SIP／B2B／主客／bench）合起嚟令 Brier 更差**（+0.019，CI 全正，兩季、primary／S1 一致；slope 0.41）。即係喺呢個 population，呢啲加法調整嘅**淨效果係負**。呢個係本實驗最有行動價值嘅發現，但**唔等於每一項都壞**——要 ablation 先知邊項。
4. 冇洩漏（shuffle slope≈0、單元測試）。

**講唔到**
- **乜都講唔到落注利潤／EV**：冇用賠率，線唔係莊家實際開價範圍；莊家喺高低兩端開價同 shade，母體唔同。Brier 贏唔等於正 EV。
- **未重現嘅 live 輸入**：spread（minutes_floor）、對手 pace／defence、USG／傷兵、ML hybrid、LLM 敘述。live 實際機率有呢啲輸入，可能同 (e) 唔同；(e) 嘅「負效果」只適用於缺呢啲輸入嘅部分。
- **近平均嘅線** ≠ 極端線。Slope 低部分源自「機率喺 0.2–0.8 內，真值被估計噪音推向 0.5」；喺 tail 線（高過／低過平均好遠）校準未量。
- (f)＝解析式 live MC，唔含 context 因子；(f) 喺 3PM 反而 slope 1.20（輕微欠自信），PTS／REB／AST 則過度自信（0.74–0.85）；即係 live MC 嘅 3PM beta-binomial 同其他 stat 嘅常態假設表現唔同，需要分 stat 睇（呢個係描述性觀察，唔係預先登記嘅檢定）。
- 結論只限常規賽、兩季；冇季後賽，冇 2026-27 數據。
- `MIN_g ≥ 15` 賽後過濾已用 S1 核對，冇改變結論。
- **冇聲稱 live 模型有任何改善。** 呢個係度量，唔係 release；production code 零改動。

## 7. 建議下一個實驗（唔喺本實驗內做）
1. **EXP（新）：calibration layer 可唔可以修好 slope。** 喺時間 dev（2025-26 < 2026-01-01）擬合 isotonic／Platt（slope 收縮）餵喺 (c)／(f) 或 base 上面，H1／H2 驗證。目標係 slope∈[0.85,1.15] 同 Brier 同時過閘。需要先喺新協議登記 population（最好加入「莊家實際開價範圍」嘅線）。
2. **EXP（新）：live 調整項 ablation。** 按 `feature-ablation` 逐項關閉 trend／cov／buffer／SIP-N04／SIP-N01／B2B／主客，用本 harness 同一 population 同 H1 規則，睇邊項令 Brier 變差（懷疑 trend + buffer + SIP-N04 同 base 重複計同一個訊號：全部都由 L10 值導出）。呢個係本實驗發現 3 嘅直接後續。
3. **EXP（新）：用真實 forward snapshot 驗證。** 排程由 2026-10-21 起產生 immutable snapshot；累積 ≥ N 注／場先評估真 line 母體同 spread／pace 等缺失輸入，唔好只信 game-log 模擬。
4. **ML 引擎重訓**要用同一個 time-ordered 切分（見 EXP-20261021-01 嘅 train/serve parity）；呢個 harness 嘅 feature 構造已經係 point-in-time，可重用。
