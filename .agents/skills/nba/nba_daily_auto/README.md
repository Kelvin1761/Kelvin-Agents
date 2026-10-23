# NBA Wong Choi Daily Automation

呢層只編排現役 `nba_orchestrator.py` 同 NBA reflector，唔包含另一套 scoring。

## Schedule（Australia/Sydney）

- `pregame`：19:00 分析聽日並保存 append-only `warmup` snapshot，但唔 publish／唔發content投注卡（逐場約 8 分鐘，2026-10-20 實測）；21:00 refresh後保存正式 `production` snapshot並發佈，21:45 再跑一次補返因盤口未開而 partial 嘅場次（全部完成就 `already_snapshotted` 即跳過）；06:30只刷新未開賽game，有material source change先保存 `final_refresh` snapshot。所有舊snapshot保留，已開賽game artifacts不可改寫。
- `postgame`：18:30、21:30 抽賽果、verify props、更新 reflector DB、產生 dashboard settlement proposal；結果完整先歸檔。
- `health`：10:30 核實 ESPN schedule、今日 prediction snapshot 或已歸檔狀態。
- `startup`：登入後補昨日 postgame，再補當前 pregame。

Off-season／官方確認冇賽事會記為 `dormant` 並 exit 0。官方 schedule 讀唔到、盤口未齊、賽果未齊、deploy 失敗會 exit 75，保留現場等下一次安全重試。

Sportsbet discovery 同時讀常規賽 `6927` 同季前賽 `3079`，再按 Sydney 日期同
ESPN 賽程過濾。抽唔到任何盤口會 exit 75，唔會回報成功。賽前失敗留下嘅空
analysis folder，postgame／startup 會記 `dormant: no_prediction_artifacts`；
有任何檔案但冇 snapshot 仍會報錯，保留資料查證，唔會事後補造賽前 snapshot。

Season classifier 使用六個公開階段：`OFF_SEASON`、`PRESEASON`、
`EARLY_REGULAR`、`REGULAR_SEASON`、`LATE_REGULAR`、`POSTSEASON`。
`POSTSEASON` 再以 `postseason_type=PLAY_IN|PLAYOFFS` 分開。Preseason 會照跑
數據、報告同 immutable shadow snapshot，但強制 `NO BET`，唔 deploy 投注 Dashboard、
唔發 content 投注卡；regular season 開始先轉 production mode。

## Commands

```bash
.agents/skills/nba/nba_daily_auto/install_macos_launchd.sh
.agents/skills/nba/nba_daily_auto/install_macos_launchd.sh --status
.agents/skills/nba/nba_daily_auto/run_nba_daily_schedule.sh health
.agents/skills/nba/nba_daily_auto/run_nba_daily_schedule.sh pregame --date 2026-10-21
```

Live analysis 仍放 repo root，等 dashboard exporter 讀取。完成日會搬去本機
`~/WongChoiData/Wong Choi NBA Analysis`，避開 launchd 對 Google Drive File Provider 嘅權限問題。

每次 run 寫結構化 JSON 去 `logs/`；prediction copy 同 SHA-256 manifest 放喺該日分析 folder 嘅 `_prediction_snapshots/`。外部 dashboard settlement 只會產生 proposal，唔會自動 `--apply`。

## Telegram messages

Scheduler 會沿用共用 `~/.wongchoi_notify.env` 設定：

- `primary`：分析／覆盤完成、health 異常、pipeline 失敗、投注卡被驗證閘攔截。
- `content`：正式賽前投注卡（Banker + SGM，或者明確 `NO BET`）同賽後命中摘要。
- 投注卡只讀 Dashboard `export_nba_snapshot()` 已驗證 contract；`partial`、資料缺失或其他 blocked 狀態一律唔發建議。
- 賽後命中率只計 reflector `cleared=0/1` 嘅 legs；未落實項目會列出但唔計入。
- 每類成功送達嘅訊息都有 durable key；launchd 重試唔會重複洗版。Telegram 發送失敗／部分失敗會留喺 run log，下次仍可重試，亦唔會將分析誤判為失敗。

內容收件人由 `WC_NOTIFY_TELEGRAM_EXTRA` 控制；primary 永遠都會收到 content 訊息。可用 `WC_TELEGRAM_DISABLE=1` 暫停發送而唔影響 pipeline。

## Preseason and regular-season opener data

The extractor keeps the target season's actual roster. Preseason shadow analysis
uses completed previous-season statistics, with explicit `roster_season`,
`statistics_season`, `history_mode`, and historical cutoff metadata. Early
regular-season L10 can include the previous season until ten current-season
games are available; every L10 row records its source season. Current API
failures are not treated as an empty season. The entire US game day and future results are
excluded, and regular-season/playoff rows are ordered by parsed game dates.

All preseason game, SGM, and Banker reports carry `NO BET — PRESEASON SHADOW
ONLY`. Shadow validation requires analysis for every priced player with
verifiable history; unavailable rookie/roster matches are disclosed, never
invented. Production retains its minimum player coverage gate. Full-name
matching normalizes accents and punctuation, preserves Jr./Sr. identities, and
rejects ambiguous matches.

Only Sportsbet's full-game `Match Betting`, `Line`, and `Line Betting` markets
supply game context. Quarter/half moneylines and `Pick Your Own Line` cannot
overwrite them. Moneyline-only data is not a complete player-prop analysis:
`player_markets_not_open` exits 75 and produces no report or snapshot. Scheduled
pregame refreshes retry live extraction; missing markets are not fabricated.

## Market evaluation ledger（forward-only，模型 vs 市場）

NBA 由來冇同市場比過。`nba_market_ledger.py` 只做記錄同結算，**唔改任何預測、選腿或 SGM**。

- **位置**：`$WONGCHOI_NBA_MARKET_LEDGER_ROOT`，預設 `~/WongChoiData/NBA_Market_Eval/`
  （本機；唔入 repo）。`ledger/<Sydney日期>.jsonl` append-only；`reports/evaluation_latest.json` 係最新評估。
- **寫入**：每次 `refresh_sportsbet_odds` 成功 → 每條 milestone 腿一行 `price_obs`；每個 snapshot →
  `model_obs`（每條評估過嘅腿：`p_final`、`p_hit_rate_10f`、`p_ml`、`p_monte_carlo`、`picked`）、
  `sgm_obs`（每個組合：naive／correlation-adjusted joint prob、腿價相乘，加 N1 shadow：
  `sim_joint_prob`＝同一場模擬比賽入面全部腿一齊中嘅比例，共用 pace／賽果分差→主力垃圾時間／
  球隊得分／球員角色因子；`sim_independent_prob`、`sim_correlation_lift`、
  `sim_scaled_joint_prob`＝p_final 相乘 × lift；seed 每場固定）。shadow 只記錄，**唔改發佈邊條 SGM**；
  未有足夠已結算 n 之前唔准講模型 vs 市場。概率嚟自
  `generate_nba_reports.py` 同一次 run 寫嘅 `Game_<TAG>_Full_Analysis.md.market_legs.json`（綁住報告 SHA-256，
  對唔上就記 `model_missing`）。
- **結算**：postgame 歸檔後用 reflector 嘅 `Results_Brief_<US日期>.json` box score（同 `verify_props_hits`
  一樣嘅配對／DNP void 規則）；每條腿第一次結算為準，唔覆寫。
- **Point-in-time**：`captured_at` ≥ tip-off → `post_tip`；`recorded_at` ≥ tip-off → `late_write`。兩者都
  唔入任何賽前指標。冇 backfill：漏咗賽前 snapshot 就係漏咗，報告會數 `legs_missed_pretip_price`／
  `legs_without_pretip_model`。Dormant／off-season 唔會寫任何嘢；preseason 照記但評估預設排除。
- **close 唔係真收市價**：排程 19:00／21:00／21:45／06:30（Sydney）先抓價，最後一次通常離 tip-off 幾個鐘。
  CLV（earliest vs close）因此係「觀察到嘅最後賽前價」。
- **De-vig**：評估腿都係 Sportsbet milestone（「X+」）；milestone 階梯只列球員名、冇 Under，**逐條線
  永遠 de-vig 唔到**，raw `1/price`（含水）會**偏幫模型**。Sportsbet 另有「{Player} - Points」O/U X.5
  （兩邊有價）：extractor 寫入 `player_props_two_way`（`player_props` 不變，揀腿唔受影響），ledger
  記做 `price_source=ou_two_way`、line = X.5+0.5（Over 24.5 = 25+），`market_devig_close` 用最近一次
  賽前 O/U 對做 two-way proportional。raw close／CLV 只用 milestone 價，兩種來源唔混。覆蓋只限
  milestone 線啱好等於 O/U 線嘅腿（`devig_coverage`），verdict 嘅 n 亦只計呢批 cluster。
- **Sportsbet SGM 價**：Sportsbet 網頁 bet slip 用嘅 `POST /apigw/multi-pricer/combinations/price`
  唔使登入（2026-10-14 實測 200，回傳分數價 + quoteId）。extractor 喺 Sportsbet JSON 寫 `sgm_pricing`
  （class／competition／event external id 同每條 milestone 腿嘅 market／outcome external id）；
  排程每個非 warm-up snapshot 之後，對已經 render 咗嘅組合逐個報價，寫 `sgm_price_obs`（ok 或者點解冇價）。
  evaluate 用最近一次賽前報價做 `sportsbet_sgm_implied`；冇報價嘅組合就只可以同「腿價相乘」比。
  SGM 價係單邊、含水，de-vig 唔到。舊 `nba_analyst/scripts/nba_report_generator.py` 係孤兒檔，冇用。
- **指標**：Brier／logloss（每個模型 variant vs 市場）、calibration buckets、CLV、按 market 同
  picked／not-picked 分拆、SGM joint prob vs realised。

**未有足夠 n 之前，冇任何「模型贏／輸市場」嘅判決係有效。** 粗略功效（`n = (z·sd/mean)²`，z=1.96，
mean 係**假設**值，唔係觀測值）：

- 逐腿 Brier 差：假設模型平均好 0.002、配對差 sd≈0.05 → n ≈ 2,401 個**獨立**結算單位。同一場同一球員
  嘅 15+／20+／25+ 高度相關，所以要數 player-game-market cluster，唔係數腿。
- 平注 ROI：賠率 ~2.0、每注 sd≈1.0、假設優勢 +3% → n ≈ 4,269 注。
- SGM 每場得一兩個組合，要以季計。

`evaluation_latest.json` 嘅 `verdict_status` 只會係 `market_not_devigged`／`insufficient_n`／
`n_adequate_pending_review`；最後一個都唔係判決，要按 `docs/model-evaluation-contract.md` 另行評審。

```bash
python3 .agents/skills/nba/nba_daily_auto/nba_market_ledger.py evaluate [--since D] [--until D] [--include-preseason] [--write]
```

## Availability freshness and probability identity

歷史數據 cache 同即時傷停／陣容分開核對。每份 extractor JSON 嘅
`meta.availability` 記錄已驗證來源、完整陣容身份及 UTC 時間；30 分鐘後先用輕量
`nba_extractor.py --refresh-availability <game.json>` 刷新。陣容改變會要求 full
extraction；來源失敗／未驗證／賽事已開始會保留原檔並阻擋發布。舊 cache 首次升級
要重新抽取，唔會用檔案 mtime 冒充來源時間。刷新成功先 atomic replace。

每條新機率都有 `probability_model_id`，由校準層版本及實際係數／clip 設定產生。
Market ledger 先選最新賽前 observation，再按身份分組；reliability 只評現役身份，
舊版同欠身份嘅歷史結果留喺背景統計。設定變更唔會延續舊係數嘅校準樣本。

校準設定損壞／讀取失敗／非有限係數會停止報告發佈；刻意關閉
`NBA_WC_PROB_LAYER=0` 或 `enabled=false` 仍然有效，監察會明示 disabled。

## Local ML model cache

`NBA_WC_MODEL_DIR` explicitly selects the existing ML model directory. The
launchd runner prefers `$HOME/WongChoiData/NBA_ML_Dataset/models/v3` when both
`model.pkl` and `feature_names.json` are present, avoiding CloudStorage hydration
stalls. An explicit override takes precedence; absent cache preserves the
configured dataset path and the existing fallback behavior.

The cache is a verified copy of the approved existing model, not a retrained
candidate. `drive_provenance.json` records source file IDs, modification times,
byte counts, and hashes. Approved future model replacements must refresh this
cache together with their model release; do not leave an older local v3 copy
active after updating the source artifacts.

## no_prediction write-off（冇 snapshot 嘅日子）

一日（或某幾場）賽前冇凍結到 `_prediction_snapshots`，**唔准事後補 snapshot**。
要由人決定，再用支援嘅方法標記做 no_prediction：

```bash
python3 .agents/skills/nba/nba_daily_auto/nba_daily_schedule.py \
  --mode mark-no-prediction --date YYYY-MM-DD --by Kelvin --reason "點解冇 prediction" \
  [--game TAG ...]   # 唔畀 = 成日；有 snapshot 嘅日子只可以逐場標未凍結嘅場
```

- 寫 `<日期資料夾>/_no_prediction.json`（append-only；記 reason／marked_by／marked_at／
  commit，同標記一刻檔案嘅 sha256 —— 只係審計，唔係 snapshot），同 market ledger 一行
  `no_prediction`。已有 snapshot 嘅日子／場次會被拒絕。
- `postgame`：唔再報 `live_analysis_has_no_prediction_snapshot`；reflector 用
  `--no-record`（唔寫 `nba_reflector.db`、唔做 ML），賽果 final 先歸檔；跳過
  settlement evidence、ledger settle 同表現 Telegram。
- `health`：回 `no_prediction`（exit 0）；partial snapshot 嘅 blocked 場全部標咗就回 `ok`。
- `pregame`：成日標咗就唔再跑，避免長出事後 snapshot。
- `nba_market_ledger evaluate` 排除標咗嘅日子／場次（`counts.excluded_no_prediction_rows`、
  `no_prediction_exclusions`）。
