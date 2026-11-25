# 排程自動維修（self-repair）—— 2026-11-25

Kelvin：「可唔可以做到 scheduler 如果有啲咩問題你可以自動幫我維修」。

入口：`.agents/scripts/self_repair.py`。偵測全部用現成嘢：`job_freshness.py`（REGISTRY／輸出新鮮度／
最新 run 狀態）、`launchctl print`、control-plane manifest（`WongChoiControl/runs`）。
**預設 dry-run**（淨係講會做咩），`--live` 先真係郁。

## 自動修嘅（已知形狀）

只有 `REPAIR_SAFE` 入面嘅 tick job 會被自動郁：AU betfair-snapshot、AU bot、HKJC intraday、HKJC recovery、
NBA postgame、Tennis betfair／preclose／settle、central durability（全部係定時 tick，有自己 flock，自己決定做唔做）。

| # | 症狀 | 點修 | 安全閘 |
|---|---|---|---|
| 1 | tick job 嘅 plist 喺 `~/Library/LaunchAgents` 但冇 load | `launchctl bootstrap` | 只有 `launchctl print` exit 113（service 唔存在）先算冇 load，其他錯誤只診斷；連續兩輪、隔 ≥25 分鐘先做；`launchctl disable`、`self_repair_ignore.json`、`WongChoiControl/paused-launchd/` 入面有嘅唔郁；`print-disabled` 讀唔到都唔郁；每 job 每日最多 2 次 |
| 2 | tick job 輸出過期、已 load、冇跑緊 | `launchctl kickstart`（冇 `-k`） | 主排程 flock 有人開住就等；每 job 每日 1 次，之後仍然過期就轉「未知」 |
| 3 | 內置碟淨 < 10GB | `compress_data_root.py`（APFS 透明壓縮）＋ `offload_prediction_snapshots.py`（sha256 驗完先刪本機） | offload 要外置碟真係掛載；各每日 1 次 |

日曆 slot job（AU morning／midday／evening、HKJC watch／prerace／lineup／postrace／weekly、NBA warmup／production／
final-refresh／health、Tennis card／daily／night、ROI 總結、model-probe、astra-audit、健康）**冇 load 都唔 bootstrap、
過期都唔 kickstart**：slot 由觸發時間決定，亂開會食咗另一格或者重發 card。只做診斷。

## 全局安全閘（Sol 覆核 2026-11-25）

- **整個 run 揸 `WongChoiControl/self_repair.lock` flock**，第二個 instance 即走。
- **上限喺動手之前先原子寫落 state**（tmp + fsync + rename）；動手途中 crash，下一輪都唔會再做。
- **state 檔壞咗 → 拒絕動手**（只診斷 + 通知），唔會當空白重新開始，亦唔會覆蓋個壞檔。
- **release／activation 進行中 → 一樣都唔郁**：`auto-release.lock` 有 process 開住、`auto-release.lock.json`
  holder pid 仲生（或者讀唔到）、或者 `activation-recovery/` 兩個鐘內有新 snapshot。

## 只做診斷嘅（未知）

- 日曆 slot job 過期／冇 load；kickstart 咗仍然過期；bootstrap 兩次仍然冇 load
- 輸出新鮮但最新 run 自己寫住 `failed／partial／blocked／error`
- launchctl 查詢出錯（唔係 113）
- **死 PID 嘅鎖 holder 紀錄**（`auto-release.lock.json`、HKJC `hkjc_daily_state.lock.holder`）：自動刪有 TOCTOU 競態，
  所以只係報，附人手命令（`lsof -- <lock>` 冇輸出先 `rm -- <record>`）。紀錄係 advisory，唔會擋 flock。
- 碟清完今日仍然唔夠；state 檔壞咗；self_repair 自己某一步 exception

每個寫一個診斷包：`WongChoiControl/self_repair/<日期>/<label>.json`（原因、launchctl 狀態、freshness、
stderr／stdout 尾、最新 manifest）。dry-run 都會寫（純診斷）。

live 模式：同一日同一個 job 只發**一條** primary Telegram（`racing_telegram.send_message(audience="primary")`），
附唯讀 Claude Code 診斷命令。

### 自動 LLM 診斷（opt-in，唯讀）

`--allow-llm-diagnosis`（只喺 `--live` 生效，預設關）：由 `origin/main` 開 **detached** worktree
`/Users/imac/Antigravity-repo/.claude/worktrees/self-repair-<label>-<日期>`，背景跑
`claude -p --permission-mode plan --allowedTools Read Grep Glob --disallowedTools Bash Edit Write NotebookEdit WebFetch WebSearch`。
輸出只係診斷包旁邊嘅 `<label>.diagnosis.md`（成因、證據、建議 diff 草稿）—— 唔改檔、唔跑命令、唔開分支、唔 push。
每日最多一次。修唔修係 Claude 主 session／Kelvin 決定。

## 永遠唔做

改 code、merge、部署、改 plist 內容、掂 secrets、刪資料（包括鎖 holder 紀錄）、`launchctl bootout`、
`kickstart -k`（殺跑緊嘅 run）。

## 狀態檔

- `WongChoiControl/self_repair_state.json`：每日每 job 用咗幾多次、第一次見到冇 load 嘅時間、今日通知過邊個。
  只喺 live 寫；保留 14 日。
- `WongChoiControl/self_repair/latest.json`（live）／`latest-dryrun.json`（dry-run）：每次 run 寫。
  `job_freshness.REGISTRY` 嘅 `central-wong-choi.self-repair` 接受任何一個（上限 1.5 鐘）。
- `WongChoiControl/self_repair_ignore.json`：`["label", …]`，人手唔想佢郁嘅 job。

## 點開（dry-run → live）

```bash
python3 .agents/scripts/self_repair.py            # 1. 手動 dry-run，睇會做咩
.agents/skills/central_wong_choi/install_self_repair.sh            # 2. 裝 launchd，每 30 分鐘 dry-run；睇幾日 logs/self-repair.out
.agents/skills/central_wong_choi/install_self_repair.sh --live     # 3. 轉 live
.agents/skills/central_wong_choi/install_self_repair.sh --live --allow-llm-diagnosis   # 4.（可選）加自動 Claude 診斷
.agents/skills/central_wong_choi/install_self_repair.sh --status | --uninstall
```

要喺 `/Users/imac/wongchoi-scheduler`（生產 checkout）入面行 installer，路徑先指去生產 code。
**未安裝**：呢個改動只係加咗腳本、template 同 installer。

## 第一次 dry-run（2026-11-25 真機）

冇嘢要自動修（冇 job 冇 load、冇 tick job 過期、冇死 holder、碟淨 30GB）。4 個未知：
AU evening 最新 run partial、NBA warmup failed、model-probe failed、astra-audit 輸出過期（未寫過 latest.json）。

## 順手修咗：NBA reliability 停咗喺 2026-11-16

`reliability_latest.json` 由 `nba_daily_schedule.run_postgame` 嘅 `_reliability_text` 寫，但佢只喺
`if SGM_TELEGRAM:` 入面先叫。2026-11-16（eb0b58e2，SGM 改做只追蹤）`SGM_TELEGRAM = False` 之後就再冇計。
而家每次 postgame 都計同寫檔，淨係 Telegram 嗰行仍然跟 SGM 開關（content 只收精選）。
測試：`test_track_only_sgm_postgame_still_refreshes_reliability`。
