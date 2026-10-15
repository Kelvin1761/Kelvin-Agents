# HKJC Wong Choi Daily Automation

同 AU automation 一樣，呢層只負責編排現有 full-Python pipeline，唔會另建
scoring implementation。

macOS background process 無法可靠讀 Google Drive File Provider，所以本機已用
`.wongchoi_hk_data_root` 將 HKJC primary 指向 local disk；完成後再按
`.wongchoi_hk_mirror_root` best-effort 複製返原 Drive folder。舊三個月 archive
要先喺 Finder 設成 **Available Offline**，先可以一次過搬入 local primary 做
historical/reference review；新季 forward 收集本身唔受呢個限制。

## Modes

- `watch`：休季期間每日查 HKJC official racecard；未有資料就 dormant，首次見到新賽日用 Telegram 通知。
- `prerace`：新賽日前兩日開始跑 extractor → Facts → fresh Logic → Auto scoring → data-health gate → dashboard deploy，再保存 immutable prediction snapshot。
- `recovery`：只喺 pre-race 曾因 racecard／starter PDF／formguide 未齊而標記 pending 時，每 30 分鐘自動補跑；冇 pending 就完全 dormant、唔打 HKJC 網站。
- `postrace`：賽日翌日抽正式賽果、對齊 snapshot、跑 unified reflector 及更新 forward corpus。
- `startup`：每次 macOS 登入後即時補查 pre-race 同 post-race，避免關機期間錯過一次排程。
- `weekly`：星期一發 performance/drift 摘要；只有 `HKJC_Candidate_Gate.json` 明確為 `passed` 先建立 non-draft PR，永遠唔會自動 merge。
- `monthly`：CLI fallback，只發一次 AU + HKJC review 提醒並按月份去重。正式月報由 Codex monthly automation 自動完成：彙總上一個完整曆月、輸出 Markdown／JSON／PDF，Telegram 傳摘要及 PDF；任何模型或 Matrix 改動仍只可提出候選，等人手批准。

### SpeedPro 只向前收集（純資料，唔入分）

HKJC 只喺 `consvc.hkjc.com/.../SpeedPro/current/` 公布 SpeedPro，**冇歷史檔**，錯過一個場次就永遠冇咗。
`prerace`（full pipeline 之前）同 `lineup`（「未分析過」early return 之前）都會 best-effort 行
`hkjc_race_extractor/scripts/collect_speedpro.py --date <賽日> --course <ST|HV>`：

- 存去 `<HK data root>/_speedpro_snapshots/<YYYY-MM-DD>_<ST|HV>/<UTC 時間戳>/`，每份有 `manifest.json`，永不覆蓋；內容冇變就只喺 `fetch_log.jsonl` 加一行。
- `current/` 仲係上一個場次 → exit 3（`not_current`），唔會存落錯日期。
- 有 300 秒 subprocess timeout，任何失敗只寫 log，**永遠唔影響**分析／發佈；`WC_HKJC_SPEEDPRO_MIN_INTERVAL`（預設 3000 秒）限住 lineup 每半個鐘敲 HKJC。
- 只有賽日連續 3 次失敗、而今場一份都未存過，先發一次 Telegram 警告。
- `WC_HKJC_SPEEDPRO_DISABLE=1` 關閉（測試 conftest 預設咁做）。

### 賽前賠率快照（forward-only，唔入分析）

`prerace`（pipeline 之前）同 `lineup`（賽日／前一日每 30 分鐘）各影一次
WIN + PLA 賠率，追加入 meeting folder 嘅 `HKJC_Odds_History.json`
（`captured_at` + `label`；每場有 `pre_race` = 兩個池仍然 `START_SELL`）。
來源係 bet.hkjc.com 自己用嘅公開 GraphQL（一個 GET 攞晒全日），詳見
`hkjc_race_extractor/scripts/hkjc_odds_capture.py`。失敗只記 state
（`odds_capture.failure_streak`）同 Telegram（第 1、每第 6 次、恢復），**唔會**
改變 pipeline exit code。`WC_HKJC_ODDS_CAPTURE=0` 可關閉。評分鏈唔准讀呢個檔
（`hkjc_wong_choi_auto/tests/test_odds_stay_out_of_scoring.py`）。

## Install on macOS

```bash
bash .agents/skills/hkjc_racing/hkjc_daily_auto/install_macos_launchd.sh
```

安裝後時間（Australia/Sydney 主機時間）：

- racecard watch：00:15、09:15、21:15、23:15
- pre-race refresh：00:30、08:00、11:00、21:30、23:30
- pending source self-recovery：每 30 分鐘（只在 pending 狀態先真正重試）
- post-race：08:30
- weekly review：星期一 09:00
- restart/login catch-up：登入後即跑一次（其餘排程亦會由 launchd 自動重新載入）

夜間三段時間同時覆蓋「約晚上 9 點」係 Sydney local time，亦覆蓋香港
21:00 對應 Sydney 23:00／00:00（視乎 daylight saving）。流程唔會硬編碼
星期三／六，因為新年、復活節、打吡等可能有星期日或公眾假期賽日；每次以
HKJC official future racecard 為準，只會處理未來兩日內嘅 meeting。

如果 racecard 已出但 starter PDF 或逐場 formguide 仲未 ready，extractor 會寫
`Extraction_Readiness.json`、保留上一份有效檔案並以 temporary exit 75 停止；唔會
生成／部署半套分析。Recovery job 會每 30 分鐘補跑，所有必需來源齊全先繼續
Facts → Logic → scoring → health gate。相同 snapshot 重跑唔會重複 Telegram 洗版。

賽後 reflector 成功後會重建及部署 dashboard；有
`HKJC_Reflection_Report.md` 嘅已完成賽日唔再出現。如果 Cloudflare 暫時失敗，
狀態會保存為 pending，下一次 post-race／startup 自動重試。

Telegram 會優先重用 AU automation 嘅 `~/.wongchoi_notify.env`：
`WC_NOTIFY_TELEGRAM_TOKEN` / `WC_NOTIFY_TELEGRAM_CHAT`。因此同一 bot、同一
chat 可以同時收 AU 同 HKJC 訊息，唔需要複製 token。未有 AU 設定先使用：

```bash
cp .agents/.env.example .agents/.env
# 然後填 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
```

如設定 `WC_NOTIFY_TELEGRAM_EXTRA`（多個 chat ID 可用逗號或分號分隔），HKJC
分析完成訊息會同時發畀 primary 同額外收件人。錯誤、路徑及 recovery 運維訊息
仍然只發畀 primary，額外收件人唔會獲得 bot 指令權限。

同一個 Telegram bot 亦提供兩個只限 primary chat 嘅手動後備指令：

- `/hkjc`：用正式 pipeline 強制分析 HKJC 官網最新 future racecard。
- `/hkjc_reflect`：抽取最近未覆盤賽日嘅正式賽果、跑 reflector，再更新 dashboard。

可用
`WC_HKJC_ANALYSIS_LEAD_DAYS` 改 pre-race 提前日數；forward 正式起點預設
`2026-09-06`，可用 `WC_HKJC_FORWARD_START` 覆蓋。

Runtime state/log 會寫入 `state/` 同 `logs/`，唔應 commit。候選 gate 由研究／
evaluation workflow 寫入 `state/HKJC_Candidate_Gate.json`；必須包含 paired
performance、branch、PR title 同 body file，scheduler 只負責開 PR 等人批准。
