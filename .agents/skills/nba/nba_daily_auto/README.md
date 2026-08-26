# NBA Wong Choi Daily Automation

呢層只編排現役 `nba_orchestrator.py` 同 NBA reflector，唔包含另一套 scoring。

## Schedule（Australia/Sydney）

- `pregame`：21:00 分析聽日並保存 append-only `warmup` snapshot，但唔 publish／唔發content投注卡；00:30 refresh後保存正式 `production` snapshot並發佈；06:30只刷新未開賽game，有material source change先保存 `final_refresh` snapshot。所有舊snapshot保留，已開賽game artifacts不可改寫。
- `postgame`：18:30、21:30 抽賽果、verify props、更新 reflector DB、產生 dashboard settlement proposal；結果完整先歸檔。
- `health`：10:30 核實 ESPN schedule、今日 prediction snapshot 或已歸檔狀態。
- `startup`：登入後補昨日 postgame，再補當前 pregame。

Off-season／官方確認冇賽事會記為 `dormant` 並 exit 0。官方 schedule 讀唔到、盤口未齊、賽果未齊、deploy 失敗會 exit 75，保留現場等下一次安全重試。

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
