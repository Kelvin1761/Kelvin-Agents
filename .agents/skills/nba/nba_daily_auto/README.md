# NBA Wong Choi Daily Automation

呢層只編排現役 `nba_orchestrator.py` 同 NBA reflector，唔包含另一套 scoring。

## Schedule（Australia/Sydney）

- `pregame`：21:00 分析聽日並保存 append-only `warmup` snapshot，但唔 publish／唔發content投注卡；00:30 refresh後保存正式 `production` snapshot並發佈；06:30只刷新未開賽game，有material source change先保存 `final_refresh` snapshot。所有舊snapshot保留，已開賽game artifacts不可改寫。
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
