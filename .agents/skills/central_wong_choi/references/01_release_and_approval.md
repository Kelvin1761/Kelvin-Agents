# Release and Approval

2026-10-10 用戶授權自動批准，設定見 `../resources/release_automation.json`。
enabled=true 時，下文嘅批准步驟由 `user-delegated:auto-release` 自動執行，
唔等 Telegram `/approve`；immutable SHA、clean checkout recheck、scope、
domain evidence 同 rollback 防線繼續生效。enabled=false 恢復人手批准。
`./保存.sh --path ... --expected-result "預期影響" "commit message"`
會通知預期影響及最終 merge／activation 狀態。預期結果唔等於已量度改善。

## Classification

- `docs_tests`: quick gate；可自動 push 同 fast-forward main；永不自動 activate。
- `code`: full gate；push branch；要批准先 merge。
- `model`: full gate + domain evaluation evidence；要批准先 merge/promotion。
- `evaluation`: 必須獨立 release，唔可以同候選 model 一齊改把尺。
- `automation`: full gate + scheduler/lock/idempotency smoke；要批准先 activate。
- `deployment`: full gate + backup/verify/health/rollback plan；要批准先 deploy。

## Safe Release Sequence

1. 喺 isolated worktree 確認 explicit scope，拒絕 unrelated dirty/staged paths。
2. 跑 policy gate；只 stage exact paths；`git diff --cached --check`。
   `single_clean_gate=true` 嘅自動 release 會先用獨立暫存 index 建立候選 tree／未發佈 commit object，
   對**同一個 SHA** 喺乾淨 clone 跑完整 gate（連資料根 marker），成功先用 compare-and-swap 保存到工作分支。
   gate 失敗唔會改 HEAD 或真正 index；gate 期間 source／HEAD／index 改變會停。
   有 Git hooks、commit signing 或未固定 interpreter 嘅本機 `.venv` 會用原有流程，保留原來行為。
3. Commit 同 push feature branch；寫 immutable release manifest。
4. Docs/tests-only 重新分類整段 unmerged history，仍然安全先 fast-forward main。
5. 高風險 release Telegram 顯示 short commit、risk、gate、rollback target。
6. Approval 時 fetch remote；branch commit、origin/main、scope、gate freshness任何一項唔一致即失效。
   同一個 Python process 可重用 15 分鐘內、同 SHA／check／Python 套件版本及位置／環境／資料根嘅完整 gate receipt；
   批准前仍喺乾淨 clone 跑 quick gate，刷新資料合約，再 fetch 驗 main。receipt 只存記憶體，唔會從 manifest／log 還原；
   resume、過期、環境改變一律重新 full gate。replay 新 SHA 自己跑一次 full，絕不重用舊 SHA 嘅 receipt。
7. 每個allowlisted runtime installer先做external-state snapshot；installer／deploy／verifier任何後續失敗，先用candidate installer restore plists，再退回Git checkout。
8. Merge／activation 完成後 append event，唔改寫原 manifest。

## Unified Runtime Cutover

- `install_production_runtime.sh`係唯一可自動切HKJC、NBA、Tennis同Central launchd嘅installer；AU bot係approval caller，所以activation期間唔bootout AU。
- AU四個plist必須已經指向同一production checkout，否則fail closed。
- Tennis只換versioned code path；`WC_TENNIS_RUNTIME_ROOT`內現有SQLite、`.venv` interpreter、logs同Google Drive output path不搬、不刪，三個plist必須明文固定`TENNIS_PYTHON_BIN`。
- 安裝前要過Sydney timezone、Tennis read-only SQLite quick-check、system Python dependency、legacy NBA plist同active-run preflight。
- 安裝後read-only verifier要逐個plist比對exact path兼確認loaded；未全線aligned就自動restore舊plist。
- 第一次由舊bot升級時，用`bootstrap_telegram_approval.sh SHA`開五分鐘authenticated handoff；timeout或任何錯誤必須restore舊production poller。
- Handoff期間只可對`com.antigravity.au-wong-choi.bot`套用transient unloaded allowance；path仍要exact aligned，其他labels照常要求loaded。離開handoff後Central status一律恢復strict。

## Failure Policy

Gate output 即時送 stderr（CLI stdout 保留 JSON），每 30 秒印已用時間；manifest／approval event 記低 gate 耗時及 log 路徑。
等批准鎖亦每 30 秒更新。gate timeout 會終止整個 process group，避免遺留測試子程序爭資源。
診斷 log 存喺系統暫存根嘅 `wc-release-gate-logs/`，唔係永久 evidence；immutable manifest／event 仍係正式紀錄。

- Gate fail：唔 stage、唔 commit。
- Push fail：保留 local commit，manifest 標記 `push_failed`。
- Main 已變：自動模式只對無撞檔範圍 replay，對新 SHA 重跑完整 gate，最多三次；其他情況 approval expired，跟 `AGENTS.md` 用 refresh。
- Production checkout dirty：block activation，唔還原用戶改動。
- Post-sync verifier／installer／deploy fail：退回activation前captured SHA，expected runtime mapping union保留；發critical Telegram，唔宣稱成功。
- Runtime installer有外部plist改動時：先restore snapshot；external rollback同Git rollback任何一邊失敗，activation都標failed，唔准報成功。
- Rollback期間有unrelated dirty path：fail closed，唔reset；failure event要同時記原錯誤、rollback blocked同精確paths。
- Model registry首次遷移：只可由authenticated Telegram chat喺release `merged + activation_succeeded`、四線production同SHA、已入main、evidence audit ok兼registry空白時執行；重覆同版本只讀回覆。
