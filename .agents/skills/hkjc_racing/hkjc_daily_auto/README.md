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
- `postrace`：賽日翌日抽正式賽果、對齊 snapshot、跑 unified reflector 及更新 forward corpus。
- `weekly`：星期一發 performance/drift 摘要；只有 `HKJC_Candidate_Gate.json` 明確為 `passed` 先建立 non-draft PR，永遠唔會自動 merge。

## Install on macOS

```bash
bash .agents/skills/hkjc_racing/hkjc_daily_auto/install_macos_launchd.sh
```

安裝後時間（Australia/Sydney 主機時間）：

- racecard watch：09:15、18:15
- pre-race refresh：08:00、11:00
- post-race：08:30
- weekly review：星期一 09:00

Telegram 使用 shared `racing_telegram.py` 嘅既有環境設定。首次設定：

```bash
cp .agents/.env.example .agents/.env
# 然後填 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
```

可用
`WC_HKJC_ANALYSIS_LEAD_DAYS` 改 pre-race 提前日數；forward 正式起點預設
`2026-09-06`，可用 `WC_HKJC_FORWARD_START` 覆蓋。

Runtime state/log 會寫入 `state/` 同 `logs/`，唔應 commit。候選 gate 由研究／
evaluation workflow 寫入 `state/HKJC_Candidate_Gate.json`；必須包含 paired
performance、branch、PR title 同 body file，scheduler 只負責開 PR 等人批准。
