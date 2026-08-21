# Tennis Wong Choi 分階段完成計劃

## 目標

將重建後 player-prop engine 變成一條可重現、可每日結算、可用 Telegram 監察，而且只有通過 out-of-sample 門檻先會出正式推薦嘅 production analysis pipeline。

## 現況基線（2026-08-21 audit）

- 2026-08-07 至 2026-08-20：813 個 fixture、642 個有 Sportsbet 價、599 個有分析、705 個已有賽果。
- 重建版正式 profile paper sample：343 settled，177 win，-22.683u，ROI -6.61%；最近 100 注 ROI -28.07%。
- Match prediction：131 settled，-7.420u，ROI -5.66%。
- 所有 player-prop family 現時都應維持 `RESEARCH_ONLY`；`prop_live_bets` 仍然係 0，paper ROI 唔可以寫成實際投注回報。
- 2026-08-21 09:00 scheduler 因 production code／checkout 不一致而失敗；recovery entrypoint 同樣缺檔。

## Phase 0 — 統一 production 版本同恢復 automation

- [x] 將現役 production Tennis tree 同目前 checkout 對齊；完整 baseline 404 tests 通過。正式 branch 收斂／commit hash 固定仍要喺獨立 clean PR 做，避免混入 repo 內既有 AU/HKJC dirty changes。
- [x] 確認 launchd launcher、09:00 card、18:00 settle/review、10:30/12:30 recovery 全部指向同一 checkout；補回 `--source launchd` 同 `tennis_card_recovery.py`。
- [ ] 將 analysis output 固定喺一個 canonical local root，再 best-effort mirror，避免 Google Drive／repo root 分裂。
- [ ] 跑兩日 canary，證明 09:00 有 card、18:00 有 review、recovery 無 missing-file error。
- [x] 修正每日 Elo rebuild 主要瓶頸：168,806 場由逐場兩次 SQL update 改成 provider-scoped set-based update，並將 history insert 批次化；production DB benchmark 降至 5.44 秒。同步修正不同 provider 重用 match ID 時會互相覆寫 opponent Elo 嘅 correctness bug。
- [x] card pipeline 已輸出逐 stage duration（settlement、各 ingestion、feature snapshot、pricing、report、tracker sync、dashboard），下一步兩日 canary 可直接定位超時 stage。

驗收：連續兩個 Sydney 日有 `HEALTH_JSON`、card、review、settlement、dashboard deploy；log 內 model commit hash 一致；09:00 card 同 recovery 各 stage 均有 duration，總 runtime 不超出預設發布窗口。

## Phase 1 — 修正 settlement 同數據完整性

- [x] 修正 `prop_tracker` 已結算但 `clv_tracker` 仍 `PENDING` 嘅同步問題；265 個明確 mismatch 已清零。
- [x] 舊 value pending 已分類：34 筆係未有 match result；9 筆 Ace 只得比分、無 Ace 統計。下一步係將呢個分類直接放入每日告警，而唔係只報一個總數。
- [x] 清理 6 個不可能 scoreline，統一標記做 `incomplete_scoreline`／retired；critical validation 由 6 降至 0。
- [x] prop→CLV WON/LOST/VOID 權威同步有 regression tests；完整 suite 404/404 通過。

驗收：settled source row 同 CLV row 狀態 100% 一致；72 小時以上無原因 pending = 0；impossible score warning = 0。

## Phase 2 — 建立可信 performance contract

- [ ] 永久分開 `paper_recommendation`、`confirmed_live_bet`、`research_scorecard`，所有報告必須標籤清楚。
- [ ] 每個 prediction／prop 儲存 immutable `analysis_run_id`、model version、odds timestamp、match start time、selection/gate version。
- [ ] 以 2026-08-10 rebuild 為 cutover；replay data、當時真實 card、重建後 forward data分開計，禁止混合 ROI。
- [ ] 固定輸出 1 日、7 日、14 日、30 日及 since-cutover：settled、W-L、stake、PnL、ROI、CLV coverage、Brier、log-loss、pending coverage；按 family／surface／tour／gender／odds band 分層。

驗收：同一 DB 重跑兩次結果一致；任何 ROI 都可以追返 immutable source rows；paper 同 live 永遠唔會合併。

## Phase 3 — Telegram 每日 performance

- [x] 18:00 review 完成後產生一段 3,800 字內香港中文摘要，沿用現有 AU Telegram credentials／audience routing。
- [ ] 訊息包括：昨日 settled W-L/PnL、rolling 7/14 日 ROI、各正式 family 狀態、model-vs-market、pending/coverage、今日 gate verdict。
- [x] 如果 `prop_live_bets` 無紀錄，明示「Paper performance，非實際投注」；有 live bets 後再另列現金 stake/PnL。
- [ ] stale DB、settlement mismatch、樣本不足或 automation failure 時發告警，唔發貌似正常嘅 performance。

現況：launchd 已重新安裝並載入 `TENNIS_NOTIFY_PERFORMANCE=1`；read-only Telegram self-test 確認 `WongChoii_bot` 同 2 個 content recipients 全部可達。手動實發因未逐一確認外部 recipients 而未執行，連續兩日 canary 仍待觀察。

驗收：fixture 測試覆蓋正數、負數、無 bet、pending、Telegram 分段及單一 recipient failure；連續兩日實際收到同 DB 對得上嘅摘要。

## Phase 4 — 重新校準共用分析底層

- [x] 以 bookmaker de-vig probability 做必須擊敗嘅 baseline；`holdout_validation.py` 而家逐 family 分開輸出 train／holdout model-vs-market Brier。
- [x] 將主要 family 拆成 joint-distribution holdout 實驗；已確認 fitted hold + 0.06 day-form dispersion可改善 game handicap／player games，但仍未擊敗市場，故只進 shadow model，唔放寬 edge threshold。
- [x] 新增 frozen chronological market-residual experiment；weight 只喺 split 前擬合，再喺 split 後評分，並試埋 surface-specific weight。現階段無 family 達到 +0.002 Brier gain，全部維持 market baseline／research-only。
- [ ] 暫停 match-winner 正式推薦；現時 14 日 ROI -5.66%，只保留 scorecard，直至獨立 holdout 同時過 Brier、calibration 同 ROI gate。

驗收：至少一個 family 喺完全未參與調參嘅 holdout 同時達到 model Brier < market、ECE 合格、bootstrap `P(ROI<=0) <= 0.10`；否則維持 research-only。

### Phase 4 實測基線（split = 2026-08-07）

Holdout 係 85.7% hard court，屬於明顯 regime shift；因此唔可以用較早 clay／grass 盈利直接推論現時仍有 edge。

| Player-prop family | Holdout scorecard n | Model Brier | Market Brier | Formal ROI |
|---|---:|---:|---:|---:|
| player_game_handicap | 499 | 0.2472 | 0.2106 | -9.37%（143） |
| player_win_a_set | 285 | 0.2120 | 0.1817 | -8.36%（57） |
| first_set_winner | 351 | 0.2414 | 0.2094 | +1.25%（32） |
| player_total_games | 197 | 0.2742 | 0.2477 | -16.29%（55） |
| player_aces | 48 | 0.3129 | 0.2592 | -10.86%（26） |
| player_set_handicap | 67 | 0.1408 | 0.1257 | -1.67%（4） |
| player_exact_set_score | 268 matches | 0.1757 | 0.1599 | 無正式 profile bet |

結論：每一個 family 嘅 raw model 都輸俾市場。用 split 前資料擬合 `market + w*(model-market)`，再喺 holdout 評分，亦無任何 family 達到預先定義嘅 +0.002 Brier gain；surface-specific weights 都未能改變結論。呢個係模型問題，唔係將 edge threshold 放鬆就會解決。

### 網上研究轉成嘅 implementation 原則

- [Spanias & Knottenbelt 嘅 low-level point model](https://academic.oup.com/imaman/article-abstract/24/3/311/897637)由每位球員 serve／return point probability 逐層推到 game、set、match；所以 games／handicap／win-a-set／first-set／exact-score 必須共用同一個 joint score distribution，唔可以各自用互相矛盾嘅 scalar curve。
- [Gollub 2021 serve forecasting](https://journals.sagepub.com/doi/abs/10.3233/JSA-200345)指出直接用歷史百分比會受細樣本同 strength-of-schedule 偏差影響，建議 Efron–Morris shrinkage；下一版 hold input 要做 player/surface/tour partial pooling，同時以對手質素調整。
- [Koopman & Lit 動態 surface-specific strength](https://academic.oup.com/jrsssa/article/182/4/1393/7070181)以 time-varying、surface-specific player ability 做 OOS 預測；現時 holdout 由 mixed surface 轉 86% hard，證實 static pooled weight 唔夠。
- [Knottenbelt 等 common-opponent stochastic model](https://www.sciencedirect.com/science/article/pii/S0898122112002106)以共同對手校正 strength of schedule；低 tier／ITF 直接平均 serve stats 要改成 opponent-adjusted estimate。
- [Walsh & Joshi 嘅 sports-betting calibration study](https://arxiv.org/abs/2303.06021)支持以 calibration 而唔係 accuracy 揀模型；所以 promotion 必須用 Brier／log-loss／reliability，再睇 ROI，唔會只追 hit rate。
- [Correction study of sportsbook mispricing](https://arxiv.org/abs/2306.01740)示範單一錯價同過時係數可以製造假盈利；本系統因此禁止 post-start odds、要求可核實 start time，並用固定 holdout／短期熔斷防止 lifetime ROI 掩蓋 decay。
- 專業 punter 做法亦一致：Betfair 訪問中專業 trader 強調[每日保存及分拆紀錄、所有決策都係 price](https://www.betfair.com.au/hub/education/punter-insights/in-play-trader/)；Pinnacle 風險文章指出 sharp bettors 常用 fractional Kelly。系統會維持細注、硬 stop、CLV 同逐 family ledger，而唔會為增加 action 放寬閘。

### 每個 player-prop family 嘅改良路線

1. `player_game_handicap`：由同一 joint simulator 直接產生 margin distribution；加入 time-varying hard-court serve/return strength、對手調整、day-form dispersion，按 handicap line band 評分。先要 OOS Brier 贏 market，因為現時係最大虧損來源。
2. `player_win_a_set`：同 exact score／set handicap 共用 set distribution；分開 YES 與 sweep-NO，保留 YES-only research cohort；固定近 100 注為熔斷，唔再用增長中嘅 30% lifetime window。
3. `first_set_winner`：用首盤專屬 serve order／first-set history，而唔係將 full-match win probability換算；現時 +1.25% 只係 32 注，Brier 大幅輸 market，唔可升級。
4. `player_total_games`：由 joint simulator輸出完整 player-games distribution；加 retirement policy、best-of、surface-specific tiebreak／7-5 set-length 修正，停止用固定 Normal SD 作正式 fallback。
5. `player_aces`：由「每場平均」改成 exposure model（預期 service points／service games × ace rate），以 opponent return、surface、tour 做 partial pooling；比較 Poisson／negative-binomial predictive distribution，細 history 必須 shrink。
6. `player_set_handicap`：同 exact set score共享 BO3 multinomial distribution；先累積至少 50 formal bets，現時 4 注 ROI 無決策價值。
7. `player_exact_set_score`：用完整四類 outcome probabilities同 multi-class log-loss/Brier；四邊 market 一次 de-vig，唔以多個 binary score混合計證據。
8. `player_double_faults`：目前 feed coverage = 0；先做 capture/identity/settlement，唔會因為模型 class 已存在就開市場。

### 賠率目標（2026-08-21 補充）

- 正式卡採用 EV-aware soft preference：所有 family／edge／quality／timing gate 都通過後，`2.00+` 候選獲 3 個百分點嘅排序 bonus；只會喺同最佳短價 EV 接近時升前，唔會跳過明顯更好嘅 1.50–1.99。
- 呢個唔係硬性最低賠率。若無合格 `2.00+`，經 OOS 及短期 gate 證明有正 edge 嘅 1.50–1.99 仍可出現。
- ROI 報表改用 `<1.60`、`1.60–1.99`、`2.00–2.24`、`2.25+`，唔再將 1.90 同 2.00 混埋同一 band。
- 舊 aggregate 顯示 `2.20+` lifetime ROI +10.5%，但近期 ROI -16.1%；相反舊 `1.90–2.19` band 近期約 +4.4%。所以唔會因為賠率較高就降低證據門檻，2.00+ 必須同樣證明正 OOS ROI／calibration。

每條路線用同一 promotion sequence：`capture → frozen feature spec → walk-forward train → untouched hard-court holdout → shadow forward → limited live`。任何一步無法證明增量，就 retire／繼續 research，唔以「調到正 ROI」作完成定義。

## Phase 5 — 完成現有 player-prop families

- [x] `player_game_handicap` 改用 fitted hold + 0.06 dispersion joint margin distribution：可用 holdout Brier 0.2445 → 0.2185，但 market 0.2066；完成 shadow 改良，未獲 promotion。
- [x] `player_win_a_set`、`player_set_handicap`、`player_exact_set_score` 共用同一 BO3 multinomial outcome distribution；set handicap 0.1408 → 0.1371、win-a-set 0.2111 → 0.2085，但兩者仍輸市場。
- [x] `first_set_winner` 保留首盤專屬模型：測試 common full-match joint 反而令 Brier 0.2421 → 0.2428；繼續 shadow，唔恢復 early-main。
- [x] `player_total_games` 改用 fitted hold + dispersion player-games distribution：holdout Brier 0.2734 → 0.2665，但 market 0.2492；保留 research-only。
- [x] `player_aces` 完成 service-games exposure capture/backfill（150,633 rows）、ace-rate × expected service games 模型，同 pre-split 擬合 negative-binomial size=3；holdout Brier 0.3129 → 0.2847，但 market 0.2592，故保持 shadow。Poisson 同舊 empirical exposure curve 已被 holdout 淘汰。
- [ ] 每個 family 繼續累積 forward settled sample；`player_set_handicap` 同 `exact_set_score` 尤其不可用細樣本 ROI 升級。

驗收：每個 family 有 model card（資料需求、coverage、settlement、baseline、walk-forward、風險、promotion gate）；未過 gate 一律唔出正式投注。

## Phase 6 — 新 player props 市場擴展

- [ ] 先用近 30 日 Sportsbet inventory + result availability 建 coverage matrix，再決定開發；「更多數據」只係必要條件，唔係開市場理由。
- [ ] 現有 recurring pre-match families（game handicap、win-a-set、first-set winner、player total games、set handicap、aces、exact score）其實已大致捕捉；先完成佢哋。
- [ ] `player_double_faults` 近期 feed coverage 為 0，唔投入 production；break-point／service-game micro markets 屬條件式 in-play，唔混入 pre-match model。
- [ ] 新 family 只可按 `capture -> price -> paper settle -> calibration -> frozen holdout -> limited live` 順序開放。
- [x] 新增 `First-set Game Handicap` 每日 shadow：joint simulator、兩邊去水、feed identity、首盤比分 settlement、report／tracker／scorecard 已接通；replay ROI +1.84%（56注），但 loss probability 43.05%、Brier仍輸市場，維持 `RESEARCH_ONLY`。
- [x] 新增 `Win First Set & Match` 每日 shadow：合併 Sportsbet 分拆嘅四個互斥 outcome 後一次去水，避免將非完整兩邊市場當成50/50；replay ROI -12.65%（26注），維持 `RESEARCH_ONLY`。

驗收：候選市場至少 100 個可 settle scorecard outcomes、30 個 formal paper bets、coverage/identity/line orientation 測試全過，先可以進 limited live；完整升級等 100–200 個 forward settled bets。

## Phase 7 — Live pilot 同風險治理

- [ ] 由 user-confirmed placed bet 寫入 `prop_live_bets`，保存實際 odds、stake、時間；系統唔可假設推薦等於已下注。
- [ ] 初期只容許一個已過 Phase 4/5 gate 嘅 family，0.5u cap；沿用預先註冊 -20u hard stop、100 注 interim review、200 注正式 review。
- [ ] 每週 reflector 比較 live vs paper、CLV、surface shift、closing-price quality 同 model drift；任何完整性失敗自動 pause。

驗收：live ledger 逐注可核對、stop-rule 可重現、Telegram 同 dashboard 數字一致，200 注 review 有書面 promote/hold/retire 決定。

## Phase 8 — 最終驗證

- [ ] 跑完整 unit/integration suite、read-only production DB audit、兩日 scheduled canary、Telegram self-test、dashboard parity check。
- [ ] 對每個 Phase exit criterion 留機器可讀 artifact；任何未過項目保持 `RESEARCH_ONLY`，唔以主觀判斷取代 gate。

## 完成定義

- automation 連續運作而且 code/model/data version 唯一；
- settlement、Telegram、dashboard 同 DB 數字一致；
- paper/live/replay performance 完全分開；
- 至少一個 player-prop family 真正通過 frozen out-of-sample gate，否則系統誠實維持「今日無正式推薦」。
