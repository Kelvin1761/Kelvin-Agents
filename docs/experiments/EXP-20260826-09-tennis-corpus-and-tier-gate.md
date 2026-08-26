# EXP-20260826-09 — Tennis：績效語料係事後回填；match-winner 路徑冇 tier 閘

- **日期**：2026-08-26
- **平台**：Tennis (tennis-wong-choi)
- **Commit**：未 commit（等 Kelvin 跑 `./保存.sh`）
- **語料**：`tennis-wong-choi/tennis_wc.db`，備份喺
  `data/backups/pre_pit_migration/tennis_wc_pre_pit_20260826.db`

## 假設

「Tennis prop 帳面 +2.86% ROI」係真績效；match-winner 路徑冇落注係因為冇機會。

## 結論（一句）

兩個都係假。**帳面 ROI 有 70% 係賽果出咗之後才評分寫入嘅**；而 match-winner
路徑其實有 472 個 BET 決定，只係從來冇人落（`bet_ledger` 同 `prop_live_bets`
都係 0 行），而且其中 38% 落喺一個 props 路徑早就判定唔可以打嘅級別。

---

## 發現 1：`prop_tracker` 係事後重評嘅（決定性）

13,658 行**全部** `recorded_at` 喺 2026-08。**2026-08-10 一個 run 寫咗 9,594
行，覆蓋 match_date 2026-05-10 → 08-11**。

`match_date` 唔可以做判斷依據 —— 佢係賽事本地日，`recorded_at` 係 UTC，所以有
335 行「按日期睇係賽前」但實際係開賽之後寫。唯一站得住嘅比較係
`matches.start_time_utc`：

| 分類 | 行數 | 已結算 | 有落注旗標 |
|---|---|---|---|
| 證實賽前（`recorded_at < start_time_utc`） | 2,296 | 2,140 | 291 |
| 證實開賽後 | 6,187 | 5,360 | 621 |
| 無法核實（冇 `start_time_utc`） | 5,175 | 4,898 | 1,392 |

ROI（配對 bootstrap，4,000 次，seed 固定）：

| 語料 | n | ROI | 95% CI |
|---|---|---|---|
| 全部（發佈嗰個數） | 2,304 | **+2.86%** | [−1.36, +7.36] |
| **證實賽前** | **291** | **−23.38%** | **[−33.92, −12.65]** |
| 證實開賽後 | 621 | −4.73% | [−12.66, +2.88] |
| **無法核實** | **1,392** | **+11.74%** | **[+6.24, +17.58]** |

**全部利潤都喺「量唔到幾時寫」嗰批。** 證實賽前嗰批顯著蝕。月度講同一件事：
05 −14.8%、06 +12.4%、07 +10.8%（全部回填），08 −9.2%。

pooled model-vs-market AUC 0.82 對市場 0.64 亦係同一個來源，唔可以當能力證據。
真正賽前語料逐個 `market_key` 分層之後只剩 49–107 行，冇 power。

## 發現 2：排程會喺開賽之後覆蓋賽前價（真 bug，已修）

`record_prop` 嘅 upsert 只要求 `result_status = 'PENDING'`，而已經開賽嘅賽事
一樣係 PENDING。所以每日卡同 recovery job 都會重新定價並**覆蓋原本嘅賽前價**：

| match_date | 遲寫行數 | 平均遲幾個鐘 | 最遲 |
|---|---|---|---|
| 08-19 | 229 | 31.7h | 144.1h |
| 08-20 | 108 | 47.8h | 124.4h |
| 08-25 | 10 | 0.3h | 0.3h |

最近 14 日 3,991 行有 1,824 行（45.7%）中招。已加 upsert 守衛：post-start 嘅
寫入唔准覆蓋一個已經標記賽前嘅行。

`start_time_utc` 覆蓋率由 2026-08-17 起係 **100%**，所以個閘向前基本零成本。

## 發現 3：match-winner 模型顯著輸市場（複核，成立）

2,001 場有賽果 × 最早 `match_winner` 快照去水（`MIN(id)`；`check_odds_are_pre_match`
數到 2,925 個賽後快照，一個 selection 由 1.26 走到 41.0 —— 係走地價）：

| | logloss | AUC | Brier |
|---|---|---|---|
| 模型 | 0.6567 | 0.6648 | 0.2324 |
| 市場 | **0.5996** | **0.7042** | **0.2078** |

配對 bootstrap Δlogloss **+0.0571，CI [+0.0416, +0.0730]**。最佳混合權重 w≈0.0–0.2。
平注跟模型 EV：EV>0 −3.42%、EV>0.20 −5.23%（平均賠率 3.98→4.96）—— **聲稱超額
越大蝕越多**，係「唔識定長賠盤」嘅特徵。

## 發現 4：唯一方向對嘅子群 —— 短賠熱門（NOT SHIPPED）

| 子群 | n | Δlogloss | 95% CI | P(模型贏) |
|---|---|---|---|---|
| odds ≤1.6 | 254 | −0.0112 | [−0.0466, +0.0213] | 0.748 |
| odds ≤1.8 | 379 | −0.0071 | [−0.0325, +0.0172] | 0.717 |
| odds ≤1.6 ∩ ATP | 177 | −0.0296 | [−0.0713, +0.0109] | 0.921 |
| odds >3 | 767 | +0.1335 | — | 0.000 |

全部 CI 跨零 → **NOT ENOUGH DATA**。已寫 `scripts/measure_short_favourites.py`
（純量度，唔落注，`--min-sample` 預設 600 之下拒絕出判決，walk-forward 切點寫死）。

**排除咗一個混淆**：短賠位可能只係書商抽水薄。實測抽水逐段幾乎一樣 ——
1.0–1.4: **1.0716**、1.4–1.6: 1.0736、1.6–1.8: 1.0698、1.8–2.2: 1.0738、
2.2–3: 1.0760、3+: 1.0768。所以唔係「書商冇落力」。但同時，7.2% 抽水遠大過
0.011 logloss 嘅優勢 —— 即使呢個優勢係真，都未必夠打抽水。

walk-forward（切 2026-07-15）：before n=105 Δ−0.0160 P=0.706；after n=149
Δ−0.0079 P=0.642 —— 方向一致但減弱，兩邊都冇 power。

## 發現 5：match-winner 路徑冇 tier 閘（已修）

props 路徑以 482 場實測拒絕 ITF／UTR（Brier 0.2330 對市場 0.1838，gap +0.0492
CI [+0.035, +0.063]）。**嗰個證據講嘅係 match probability 本身**，但 match-winner
路徑從來冇收到：472 個 BET 決定裡面 165 個係 ITF、13 個係 UTR（合共 38%）。

已將同一個 allow-list 加落 `apply_bet_filter`。**關鍵細節**：一定要傳
`tournament_levels.level`，唔可以只傳名 —— 26 個賽事嘅「名」係外部 id
（`421-2026`、`188-2026`），涉及 390 個 BET 決定，而佢哋實際係 GRAND_SLAM /
ATP_1000 / ATP_250。只用名嘅版本會封殺盤面最好嗰批：

| 閘 | 保留 n | ROI | 95% CI |
|---|---|---|---|
| 冇閘（全部 BET） | 472 | +0.17% | [−10.98, +11.48] |
| **只用名（我差啲 ship 嘅 bug）** | 166 | +3.20% | [−14.79, +23.12] |
| **名 + 結構化 level（已上線）** | 277 | **+10.76%** | [−3.52, +25.38] |
| （閘剷走嗰批） | 195 | −14.88% | [−32.07, +2.60] |

**判決依據係同已接受嘅 ITF 證據一致，唔係上面呢個 ROI 對照** —— CI 全部跨零。
另外要記住：`bet_ledger` 同 `prop_live_bets` 都係 0 行，一路都冇真錢，所以呢個
改動係紙上改動。

## 發現 6：兩個順手修好嘅證據管線缺口

1. `family_reliability` 嘅 quality CTE 用 `MIN(data_quality_score)` 掃**所有**
   snapshot —— 正正係 `snapshot_quality.LATEST_QUALITY_CTE` 為咗取代而寫嘅
   舊 pattern，呢個 call site 漏咗。即係「一場賽事歷史上最差嘅質素分」做閘，
   重建幾多次都返唔到 sample。已改用 latest。
2. `feature_snapshots` 949MB／1.9GB **完全冇 retention**（`maintenance.py`
   只做 `raw_api_responses`）。30,028 行對 6,390 個 distinct (match, player,
   version) = 每個 4.7 份，716MB 係已被取代嘅。已加 prune（保留行、只清
   body、newest-per-triple 任何年齡都保）。實跑：**1.9GB → 1.1GB，釋放 823MB**，
   直接紓緩 recovery job 個 `disk_headroom` 閘（要 2× DB 闊度）。
   `check_features_are_as_of` 亦改成只數 latest snapshot，唔然清盤會靜靜咁
   推低嗰個比率。

## 發現 7：找到 08-10 回填嘅兇手 —— `replay_prop_strategy.py --rebuild-source-tracker`

個 flag 會 `DELETE FROM prop_tracker` 然後用今日嘅模型重新定價每一個歷史日期。
佢有正當用途（「stored tracker 係由已經唔存在嘅定價 code 寫嘅」），而且係
leakage-safe chronological replay —— 每個日期嘅 calibration 只睇到之前嘅賽果。
**問題唔係佢跑咗，係佢嘅輸出同真紀錄放同一張枱，之後被當成真紀錄讀。**

三個修正：

1. 因為 `record_prop` 而家逐行印時間戳，replay 寫落去嘅行自動全部
   `is_point_in_time = 0` —— 判決層自動排除，兩種行再撞唔埋。
2. Replay 自己個 summary 要明文 `point_in_time_only=False`。喺自己輸出上，
   gated report 按定義係空嘅；「replay 讀 replay」係呢個 flag 唯一老實用法。
3. `--rebuild-source-tracker` 一旦見到 live tracker 有證實賽前行就**拒絕跑**，
   除非再加 `--discard-point-in-time-record`。實測拒絕訊息：
   「would delete 2296 provably pre-match rows, which are the only real record
   and cannot be rebuilt」。

## 判決層 vs 營運層（呢個分界要記住）

**已加閘（輸出會影響決定）**：`family_reliability`、`prop_roi_report`、
`model_vs_market_scorecard`、weekly review、stop rule、`holdout_validation`、
`evaluate_market_residual_props`、四個逐市場 evaluator。

**故意唔加閘（加咗就係 bug）**：settlement 本身（開賽後嘅行一樣要結算，唔然永遠
PENDING）、`prop_live_bets` 查詢、`tennis_daily_schedule` 砌卡、`validation.checks`
嘅行數統計（只睇乾淨子集嘅 data check 睇唔到佢要報嘅問題）。

判準唔係「呢個 query 有冇碰 prop_tracker」，而係「呢個數字會唔會改變我哋做咩」。

## 發現 9：喺真 pipeline 上驗證（唔止 test）

改咗生產行為就要喺真數據上跑，唔可以只信 unit test。

**寫入路徑**（`record_prop`，喺真 DB 嘅副本上、真 schema、真 row，match 14211）：

| 動作 | 結果 | 預期 |
|---|---|---|
| 賽前寫入 | odds=2.00, pit=1 | ✅ |
| 開賽後重寫 | odds=**2.00**, pit=1 | ✅ 守衛守住，賽前價冇被覆蓋 |
| 再一次賽前寫入 | odds=2.50, pit=1 | ✅ 正常重新定價仍然行 |

**落注閘**（250 個真 feature snapshot，08-13 之後）：60/60 snapshot 砌得成，
零 exception。Level 全部解得出（GRAND_SLAM / ATP_250 / WTA_500 / CHALLENGER /
ITF / UTR / UNKNOWN）。

**tier 閘唔係多餘嘅** —— 呢個我一開始估錯。今日盤面 ITF 大部分本來已經被
`data_quality_score_below_65`（58/60）同 `missing_core_elo_inputs`（48/60）攔住，
睇落好似重複。實測：

| | NO_BET | BET |
|---|---|---|
| 冇 tier 閘 | 221 | **29** |
| 有 tier 閘 | 232 | **18** |

**閘剷走 11 個（38%）其他閘放過嘅 BET 決定** —— 同歷史比例（472 個裡面 178 個）
一致。而且佢嘅價值在於「攔嘅理由對」：數據質素一改善，質素閘就唔會再攔 ITF，
而 tier 嘅理由會跟住消失。

## 發現 10：唯一未死嘅線索已入每週報告

「繼續量」如果只係一句承諾就會死。短賠熱門而家印喺會發送嘅 weekly review 上：

```
🔍 短賠熱門（賠率 ≤1.6，唯一未死嘅線索）：254/600 場｜模型領先市場 0.01125 logloss｜P=0.748
  - NOT ENOUGH DATA (n=254, need 600)
```

harness 用 call-site + 內部雙層 try/except 包住（有 test 鎖死）：研究 code 唔可以
成為營運報告嘅單點故障。個 test 一寫就即刻捉到我只包咗內層。

## 一個我要撤回嘅講法

我最初報「39% 場次 `tour='UNKNOWN'` 係標籤缺口」。**唔係。** 1,803 場裡面 1,782
場（98.8%）係 ITF、9 場係 UTR —— `tour` 係 ATP/WTA 巡迴標籤，ITF 本來就唔屬於
任何一邊，而 `tournament_levels.level` 已經正確分類咗佢哋。呢個唔係缺陷。

## 發現 8：第 2 步（跨盤不一致）已測完 —— **結構性 REJECT**

原本嘅假設：唔需要贏市場，只需要搵書商自己標錯嗰條腿。同一場比賽有幾個盤係
被算術鎖死嘅：

```
P(A 贏)          == P(A 2-0) + P(A 2-1)      [Match Betting / Set Betting]
P(兩邊都贏一盤)   == P(A 2-1) + P(B 2-1)      [Yes-No / Set Betting]
```

**一個量錯要先講**：只比較每個盤「最早」嗰個快照，會顯示 Set Betting 遲咗大約
22 個鐘（MW 05-09、SB 05-10），咁「Set Betting 更有料」就純粹係時光機。**唔係。**
Set Betting 只係喺一場比賽嘅生命週期較遲才入 scrape；一旦改成揀「同一次 scrape
occasion 同時有兩個盤」，1,092 場**全部**都喺一分鐘之內。配對一定要用
`fetched_at` occasion，唔可以用逐盤 `MIN(id)`。

**兩個中途好睇但錯嘅結果，照記：**

1. 用擬合 power exponent 去水，Set Betting 真係顯著好過 Match Betting：
   Δlogloss **−0.00517，CI [−0.01009, −0.00066]，P=0.989**。用比例去水同一個
   比較只有 P=0.853 過唔到。power 喺 4-way／14% overround 係**先驗上**正確嘅方法
   （唔係因為佢贏才揀），但兩個都要一齊報。
2. **按日期切半，效果全部喺前半**：first half −0.01047（CI [−0.01881, −0.00331]，
   P=0.999）、second half **+0.00012**（CI [−0.00505, +0.00519]，P=0.472）。
   典型衰退型優勢。

**真正嘅判決唔靠顯著性，靠「分歧 vs 抽水」：**

| 恆等式 | n | 中位分歧 | 要打嘅抽水 | 比率 |
|---|---|---|---|---|
| Match Betting vs Set Betting | 1,092 | 0.0150 | 0.0749 | **0.20×** |
| 兩邊都贏一盤 vs Set Betting | 222 | 0.0065 | 0.0891 | **0.07×** |

書商同自己一致到只差自己抽水嘅五分一（同十四分一）—— 呢個就係「幾個盤由同一個
內部模型出價」應有嘅樣。**分歧細過抽水，幾多樣本都落唔到注**：1,092 場只觸發
33 注，因為兩個盤平均只差 1.5pp 而抽水係 7.5pp。

**呢個係結構性 REJECT，唔係 power 問題。** 補數據唔會改變一個比率。

已寫 `scripts/measure_market_coherence.py`（純量度，7 個 test）—— 加新盤對只需
加一個 identity function，「分歧／抽水」比率係可重用嘅判準。

## 發現 11（08-27）：排名覆蓋率係七個 500 疊出嚟嘅，唔係 ITF 冇排名

分叉點問題：「如果 ITF 根本冇官方排名，補輸入喺 85% 盤面做唔到，可能要放棄。」

**答案：ITF 球員有官方排名。修得到。** 實測 feed 深度 —— ATP **2,161** 個排名
（深至 2,162）、WTA **1,572**（深至 1,517）。我哋一直只要 500，而 M15/W15 球員典型
排名 400–1,500，正正被切走。

| 七個 500 | 位置 |
|---|---|
| ATP request | `rowCount: "500"` |
| WTA request | `for page in range(5)` × 100 |
| **ATP parser** | `if len(rows) >= 500: break` |
| **WTA API parser** | 同上 |
| **WTA PDF parser** | 同上 |
| **WTA HTML parser** | 同上 |
| `ingest_rankings` | `LIMIT 500`（決定邊個真係拎到 `current_rank`）|

**四個 parser cap 才係關鍵。** 只放寬兩個 request cap 完全冇效 —— payload 收齊
2,161 行，parser 照樣回 500。順手加嘅截斷警告一開就即刻印
`parsed 500 of 2161` —— 比佢要守嘅 cap 更值錢。

### 第八個問題：合併搬走歷史，但丟掉搬歷史嘅理由

放寬之後新排名落喺**新** player row。`plan_merges` 提 472 組（395 組會令一個
priced player 拎到佢欠嘅排名），但 `apply_merges` 只 repoint foreign key 同記
alias，**從來冇搬 `players` 自己嘅欄位** —— 447 組合併完覆蓋率 44.3% → 44.3%
（`Aaron Funk` id 19836 有 rank 1342，canonical id 5928 係 NULL）。已修：
canonical row 用 `COALESCE` 由 duplicate 補 `current_rank`／`overall_elo`／
`surface_elo_json`。

### 第九個問題：我自己個修正放大咗一條前視路徑

`_rank_as_of` 揾唔到 as-of 行就 fallback 去 `players.current_rank` —— 而嗰個欄位
冇日期。5,748 個 player-side：51.1% 有真 as-of、29.9% 真係冇、**19.0% 收到今日排名
去評一場已打完嘅賽事**，而**放寬 feed 令呢條路行得更頻密**。已修：只有距今 ≤2 日
嘅場次可以 fallback。

### 實測結果（已應用到真 DB）

| 階段 | priced players | fixtures 雙方有排名 | ITF |
|---|---|---|---|
| baseline | 42.4% | 42.1% | **21.0%** |
| + 七個 cap | 44.8% | 44.1% | 23.6% |
| **+ 合併搬欄位** | **58.4%** | **58.7%** | **49.2%** |

備份：`data/backups/pre_pit_migration/tennis_wc_pre_rankfix_20260827.db`

### 一個唔可以繞開嘅限制

模型讀 `rankings_history` as-of（`ranking_date < match_date`），而深排名喺 8 月
之前每月只有 100–250 行 —— **歷史補唔返**。新排名 stamp 係 08-27，所以只幫到
08-28 起嘅場次。向前 as-of 上限量到 **53.3%**（現時 15–37%）。每月約 1,751 場
已結算，所以 Phase 1 個預先登記測試**約一個月**答得到。

### 剩落嘅缺口分解（1,636 個冇排名嘅 priced player）

- **467（28.5%）** normalise 後同名於一個已排名球員 → 合併可救
- **147（9.0%）** 姓＋首字母對得上 → 要獨立審（同姓同首字母唔等於同一人）
- **413** 雙打組合 → 正確地冇單打排名，應該由定價層排除
- **658** 真係配唔到（496 場 ITF ＋ 198 場 UTR fixtures，UTR／青少年／大學球員）
  → 排名永遠唔會有，但 **Elo 會有**（76.8% ITF 球員有比賽歷史）

## 發現 12（08-27）：Dashboard 之前唔會講可核實戰績

網球板顯示 family 記分卡同四條 2026-07-23 已歸檔 prop，**冇任何整體數字** ——
讀落好似平穩運作。已加兩樣落 `sports_feed.sports.tennis`：

- `verified_record`：291 注已結算、ROI **−23.38%**、實際落注 **0** 注、
  2,013 注唔計入判決
- `coverage.both_players_ranked_ratio` / `both_players_elo_ratio`：
  55.8% / 60.0% —— 即係 Phase 1 嘅進度指標

設計決定：覆蓋同策略狀態繼續收埋喺 `<details>`（診斷）；可核實戰績擺出面（答案）。
順手修：exporter 讀一個唔屬於自己嘅 DB，所以加咗欄位守衛 —— 一個
`OperationalError` 會被上游 `except sqlite3.Error` 吞掉，令整個網球板變
`unavailable`，即係診斷拖低佢要描述嘅嘢。

## 決定

- **KEEP（correctness）**：`is_point_in_time` 三態分類 + 單一真源
  `evaluation/corpus.py`；upsert 守衛；判決查詢一律只食證實賽前行；
  `feature_snapshots` retention；`family_reliability` 改用 latest quality；
  `check_features_are_as_of` 改用 latest；新 critical check
  `props_recorded_before_match`。
- **KEEP（行為）**：match-winner 路徑加 tier allow-list（傳 level）。
  依據 = 同已接受嘅 ITF 證據一致；ROI 對照本身唔夠 power。
- **NOT SHIPPED**：短賠熱門優勢。已寫量度 harness，等 n≥600。
- **REJECT（結構性）**：跨盤不一致。中位分歧只有抽水嘅 0.20×／0.07×，
  1,092 場只觸發 33 注；pooled 顯著但切半之後後半 +0.00012。呢個方向可以閂門。
- **KEEP（correctness，08-27）**：排名 feed 七個 500 上限、合併搬 player 欄位、
  關掉排名前視 fallback、dashboard 顯示可核實戰績同輸入齊全度。
  **分叉點答案：唔放棄。**
- **⚠️ 影響**：`family_reliability` 樣本大跌（例：`player_aces` 188→36 行，
  權重 0.0735→0.0000）。9 個 family 裡面 9 個而家 fit 到 0.0000，即「100% 市場、
  0% 模型」。呢個係老實狀態，唔係倒退 —— 之前嗰啲權重係喺事後價上 fit 嘅。

## 重現

```bash
cd tennis-wong-choi
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python \
  scripts/measure_market_coherence.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python \
  scripts/measure_short_favourites.py --report-overround
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python \
  -m tennis_wc.cli prune-raw-responses --dry-run
```
