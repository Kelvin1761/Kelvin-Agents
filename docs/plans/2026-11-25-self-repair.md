# 排程自動維修（self-repair）—— 2026-11-25

Kelvin：「可唔可以做到 scheduler 如果有啲咩問題你可以自動幫我維修」。

入口：`.agents/scripts/self_repair.py`。偵測全部用現成嘢：`job_freshness.py`（REGISTRY／輸出新鮮度／
最新 run 狀態）、`launchctl print`、control-plane manifest（`WongChoiControl/runs`）。
**預設 dry-run**（淨係講會做咩），`--live` 先真係郁。

## 自動修嘅（已知形狀）

| # | 症狀 | 點修 | 安全閘 |
|---|---|---|---|
| 1 | `~/Library/LaunchAgents/com.antigravity.<label>.plist` 喺度但冇 load | `launchctl bootstrap` | 要**連續兩輪、隔 ≥25 分鐘**都冇 load 先做（release cutover 會短暫 bootout）；`launchctl disable` 咗或者列咗喺 `WongChoiControl/self_repair_ignore.json` 嘅唔郁；每 job 每日最多 2 次 |
| 2 | 輸出過期、已 load、冇跑緊 | `launchctl kickstart`（冇 `-k`） | 只限 `KICKSTART_SAFE`（定時 tick／poll、自己有 flock、自己決定做唔做）；主排程 flock 有人開住就等下一輪；每 job 每日 1 次，之後仍然過期就轉「未知」 |
| 3 | 鎖嘅 holder 紀錄（`auto-release.lock.json`、HKJC `hkjc_daily_state.lock.holder`）PID 已死 | 刪紀錄 | 要 `lsof` 證實把 flock 冇任何 process 開住；**從來唔刪 `.lock` 檔**（全部係 flock，OS 會放）|
| 4 | 內置碟淨 < 10GB | `compress_data_root.py`（APFS 透明壓縮，內容唔變）＋ `offload_prediction_snapshots.py`（sha256 驗完先刪本機） | offload 要外置碟真係掛載；各每日 1 次；跑完仍然唔夠就轉「未知」叫人揀 |

`KICKSTART_SAFE`：AU betfair-snapshot、AU bot、HKJC intraday、HKJC recovery、NBA postgame、
Tennis betfair／preclose／settle、central durability。

**唔會 kickstart 日曆 slot job**（AU morning／midday／evening、HKJC watch／prerace／lineup／postrace／weekly、
NBA warmup／production／final-refresh／health、Tennis card／daily／night、ROI 總結、model-probe、astra-audit、健康）：
佢哋嘅 slot 由觸發時間決定，亂開會食咗另一格（見記憶「control plane 兩個靜靜殺 run 嘅形狀」）或者重發 card。只做診斷。

## 只做診斷嘅（未知）

- 輸出過期但係日曆 slot job、或者 kickstart 咗仍然過期
- 輸出新鮮但最新 run 自己寫住 `failed／partial／blocked／error`
- bootstrap 兩次仍然冇 load、碟清完仍然唔夠
- self_repair 自己某一步 exception

每個寫一個診斷包：`WongChoiControl/self_repair/<日期>/<label>.json`（原因、launchctl 狀態、freshness、
stderr／stdout 尾、最新 manifest）。**dry-run 都會寫**（純診斷，唔郁任何嘢）。

live 模式：同一日同一個 job 只發**一條** primary Telegram（`racing_telegram.send_message(audience="primary")`），
附住 Claude Code 診斷命令（喺新 worktree 開 `claude -p`）。

### 自動 LLM 診斷（opt-in）

`--allow-llm-diagnosis`（只喺 `--live` 生效，預設關）：由 `origin/main` 開
`/Users/imac/Antigravity-repo/.claude/worktrees/self-repair-<label>-<日期>` 新分支，背景開
`claude -p`，`--disallowedTools` 封咗 `git push`、`launchctl`、`./保存.sh`、`rm`。佢淨係可以讀、改 code、
跑 pytest、commit 落嗰個分支，同寫 `diagnosis.md`。**唔會 push、merge、部署**；收唔收貨係 Claude 主 session／Kelvin 決定
（跟 AGENTS.md「收工規則」）。每日最多一次。log：診斷包旁邊 `<label>.claude.log`。

## 永遠唔做

改 code（LLM 只喺自己分支）、merge、部署、改 plist 內容、掂 secrets、刪資料、`launchctl bootout`、
`kickstart -k`（殺跑緊嘅 run）。

## 狀態檔

- `WongChoiControl/self_repair_state.json`：每日每 job 用咗幾多次、第一次見到冇 load 嘅時間、今日通知過邊個。
  只喺 live 寫；保留 14 日。
- `WongChoiControl/self_repair/latest.json`：每次 run 都寫（dry-run 都寫）。已登記入 `job_freshness.REGISTRY`
  （`central-wong-choi.self-repair`，上限 1.5 鐘）—— 自動維修自己死咗，`健康.sh` 會見到。
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
