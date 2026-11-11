# 全線 cutover 逾時同回滾唔齊（2026-11-11）

## 現象

release 範圍包括 `install_production_runtime.sh` 就會觸發全線 launchd cutover。過去 15 次只有
2 次成功（2026-08）。2026-11-04、11-05、11-10 三次都係 `installer timed out after 300 seconds`
（exit 124），回滾報 `installer state restore failed (exit 1)`，`rollback_status: blocked`。
11-10（`wc-release:0fda08eb72e7:2026-11-10T145127.965152_0000`）之後 `hkjc-wong-choi.startup`
冇 load 返，要人手 `launchctl bootstrap`。

## 量到嘅原因

### 1. 逾時 = research review 驗收跑咗一個完整 pass

- 11-10 activation_started 14:51:38Z → activation_failed 14:56:41Z（300 s + 回滾 3 s）。
- 被殺時 stdout 最尾係 `run_central_research_review.sh --initialize` 嘅 `"status": "verified"`
  JSON；下一行 `run_central_research_review.sh > pass.json` 輸出 redirect 咗，所以冇印嘢。
- 隔離量（`test_runtime_installer.py` 嘅 harness，假 `launchctl`／`pgrep`，研究 pass 即刻返）：
  由 preflight 到 `production runtime cutover verified` 合共 **9.5 s**
  （HKJC 1.9 s、NBA 2.9 s、Tennis 1.7 s、Central＋research 驗收 1.9 s）。
- 真 pass 長度：`runs/central/*/research-review/*.json` 由 started_at 到 mtime，近兩星期
  **2,284–3,602 s**（合約 `timeout_seconds_per_domain` 900 × 4 個 domain = 3,600 s 上限）。
- 仲有第二重：驗收之後 `--status --receipt` 只當 `succeeded` 係過，但 35 個 receipt 入面
  `partial` 26、`deferred` 6、`failed` 2、`succeeded` 1。即係就算冇時限，驗收都幾乎一定 fail。

### 2. 回滾唔齊 = bootout 係非同步

- HKJC installer 14:52:08Z bootstrap 咗 `startup`（RunAtLoad）→ 即刻開跑。
- 14:56:41Z 回滾 `bootout` SIGTERM 咗佢（`runs/hkjc/2026-11-11/startup/startup/attempt-1.json`：
  `scheduler received SIGTERM`），`restore_runtime` 跟住即刻 `bootstrap`；job 未退完，bootstrap
  失敗，`>/dev/null` 吞咗係邊個 label。
- 其實嗰個 plist 同快照一模一樣 —— 回滾根本唔使郁佢。

## 修正

- `install_research_review.sh`：驗收改為 `--initialize` ＋ read-only `--status`（cursor 狀態驗證），
  **唔再同步跑 review pass**。receipt 由每日 07:10 排程寫。
- `install_production_runtime.sh` `restore_runtime`：
  - plist 同快照 byte-identical 而且 loaded → 跳過（唔好 SIGTERM 緊跑嘅 job）。
  - `bootout` 後等 `launchctl print` 真係報冇咗先 cp／bootstrap（預設最多 100 × 0.2 s），
    bootstrap 失敗再等再試，最多 5 次。
  - 每個失敗印 `restore: <原因>: <label>`，一個 label 失敗唔阻其他 label 繼續還原。
- 測試（`.agents/skills/shared_wong_choi/tests/test_runtime_installer.py`）：有狀態假 `launchctl`
  模擬非同步 bootout（bootstrap exit 5 直到卸載完）；
  `test_restore_waits_for_async_bootout_and_leaves_unchanged_running_jobs` 重現 11-10，
  `test_restore_reports_the_label_that_never_unloads` 保住部分失敗；cutover 同 research installer
  測試 assert 永遠唔會跑 pass。舊 code 跑新測試：8 個紅。

## 仲未做

- HKJC／NBA／Tennis 各自 installer 都係 `bootout` 完即刻 `bootstrap`，同一個 race 喺正向路徑都可能
  出現（如果嗰刻 job 喺度跑）。active-run preflight 擋咗大部分，所以今次唔郁。
