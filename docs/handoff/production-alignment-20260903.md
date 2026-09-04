# 四線 production 版本對齊完成 — 2026-09-03

用戶明確批准一併處理 AU／HKJC／NBA／Tennis 共用 production 版本對齊。
原有 Telegram approval 對應的 immutable commit 沒有改變。

## 已完成的版本與驗證

- GitHub main、AU、HKJC、NBA、Tennis production 全部為
  `6b97eea1808cbdfff9be16403a957ef952006c74`。
- 共用 production：`/Users/imac/wongchoi-scheduler`；目前分支
  `codex-production-main-20260903`，追蹤 `origin/main`，ahead／behind 均為 0。
- Central 於 Sydney 2026-09-03 13:45:54 記錄 `activation_succeeded`。
- 最新 main 的完整 `./檢查.sh` 通過全部 10 suites；production 本身
  `./檢查.sh --quick` 通過，包括清 bytecode、AU/HKJC golden、說明及 data contract。
- Allowlisted `install_production_runtime.sh` 執行及最終 `--status` 通過；
  實際 installed plists 與 loaded labels 四線 aligned。
- 四線 control-plane dry-run dispatcher 均指向 production scheduler。
- 455 個 production 程式／設定檔與已批准 checkout 的 SHA256 完全相同：
  AU 142、HKJC 82、NBA 34、Tennis 157、shared 40；不含 tests 及可變 mapping。
- 四個新 Python process 實際 import AU/HKJC scoring、NBA math engine、Tennis
  probability model，`__file__` 全部位於 production；不是開發 worktree。
- 工作區唯一 dirty path 為允許的 `sb_archive_meeting_ids.json`。本機原有 keys／values
  已用 union 保留，所有模型及程式檔與批准 commit 相同。

## 保留及回復

舊 `au-production` 分支仍在，HEAD
`dae33573ef18e1671f0a6d7c1bed11ceb9c902ba`；沒有改写或刪除該歷史。
四個既有 source/test hotfix 已證明包含在 approved main，原始五檔及 patch 另有
hash 備份及 Git stash。開發主 worktree 的未發佈工作完全未納入。

持久備份及部署證據目錄：
`/Users/imac/WongChoiData/WongChoiControl/production-migrations/20260903-main-6b97eea1808c/`

- `prepared.json`、`working-files/`、`working.patch`、`old-tracked-checkout.tar.gz`、`plists/`
- `attempt-3/execution.json`、`central-activation.json`、`runtime-final.json`
- `attempt-3/engine-source-parity.json`、`module-imports.json`、各 domain dispatcher smoke
- `full-gate.log`、`attempt-3/production-quick.log`、`attempt-3/installer.log`
- Tennis 備份位置／lossless 解壓 hash 以 `backup-storage.json` 及 `RESTORE.txt` 為準。

Tennis 三個實際 plists 繼續使用同一 live DB：
`/Users/imac/Antigravity-repo/tennis-wong-choi/tennis_wc.db`；interpreter 同 logs 同樣
留在原 runtime 目錄。沒有覆寫、搬走 live DB，也沒有重跑或覆寫舊賽前預測。

首次嘗試使用 `codex/...` 時，repo 既有名為 `codex` 的分支令 Git 無法建立
子 ref。Git 曾先更新 index／working tree 才報錯；其 115 個 own-operation paths
已逐項確認為 exact target tree，再完整回復原版及五檔 hashes，見
`partial-switch-recovery.json`。重試先建立／驗證不衝突的 ref，之後切換成功。

回復時應先驗證沒有 domain run 或 concurrent writes，保存最新 mapping，再透過
已保存的 installer snapshot 回復 plists，切回保留的舊分支及 hash-verified working
files，最後 union runtime mapping。不得直接把開發 worktree 複製到 production。

## 營運及邊界

最終唯讀快照：AU morning succeeded；Tennis card succeeded；HKJC/NBA startup dormant。
前兩項是最近完成的 run，不能當成新版本已完成整個下一次賽事分析的證據。
本次已驗證新版本載入及排程入口，下一次正常排程會用對齊的 production。

Registry 仍記 AU/HKJC production、Tennis/NBA shadow；舊 model registry code metadata
與 checkout deployment evidence 是不同資料。本輪沒有重新 bootstrap registry、
改 stage、改模型權重、改評估規則，或冒充 Telegram approval actor。

Dashboard configured，本次 release 不要求 Dashboard deploy，沒有寫 D1 ledger。
D1 既有 local restore-verified backup 的 WARM copy 仍 pending。
WARM 磁碟 available；既有 COLD catalog 五項已經 Google Drive 驗證。
本輪額外外置 Tennis 備份嘗試被 automatic approval review 拒絕（未有特定外傳目的地
授權），沒有執行外傳；改為本機 lossless 壓縮本輪新建備份，保留完整回復 hash。
壓縮備份 173.4 MiB，完整解壓 hash 驗證通過；原始 live DB 未改。
最終 HOT 可用約 19.3 GiB，Central 仍報 storage critical；這是獨立營運 attention，
沒有把它宣稱為全機健康綠燈，亦沒有刪除任何既有資料來清空間。

此對齊無需新增模型 commit：目標本來已 committed、pushed、merged，現在亦已 activated。
先前 AU 完整「移除最終放大」refactor 仍屬未發佈工作，不能宣稱隨本次對齊上線。
