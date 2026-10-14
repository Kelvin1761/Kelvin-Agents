# 旺財離開電腦一個月前檢查 — 2026-09-09

檢查時間：Sydney 10:25 起。結論：**未可以確認適合一個月完全無人值守**。已完成有證據支持嘅程式修復，但未 commit、push、merge 或 activate；production 仍用原有版本。

## 現場證據

- 24 個 `com.antigravity.*` LaunchAgents 全部載入。四線及 Central 實際 plist 指向 `/Users/imac/wongchoi-scheduler`，runtime verifier 判定 aligned。
- 開始檢查時 production HEAD：`396dc5223ec0a5c3d1c2df156c5e36ca4862bb9f`；修復分支基準：`75dd2c91b3e7423ef41519f589150950157a7437`。production 有兩個資料型 dirty files，activation 要按 release manager 規則核對，唔可以直接 reset。
- AU 10:00 morning 當時仍 running，未過 6 小時 timeout；之前 09:15 heal 因 deploy Python／shell 問題失敗。舊 shell 問題已有其他 release，今次冇重做嗰份改動。
- HKJC 有今日 Happy Valley 8 場 logic；08:00 prerace 曾因 UTF-8 解碼失敗。最近 recovery dormant 唔等於已證明所有上游問題都復原。
- Tennis 09:00 card 失敗；10:30 recovery 日誌明確出現 `duplicate_skipped`，指返同一份失敗 09:00 manifest，未真正重新分析。SQLite read-only `PRAGMA quick_check` = `ok`。
- NBA 最近 canonical run 係 09-09 pregame dormant（休季），唔係主 checkout 舊日誌所報嘅 08-29。NBA model 仍 shadow，實際新季 evidence 未齊。
- 30 日 slot SLO：AU 22/35（62.9%）、HKJC 845/890（94.9%）、Tennis 24/28（85.7%）、NBA 88/88（100%）。包含歷史失敗；唔可以當成未來成功機率，亦唔可用休季 NBA 數字保證開季可靠。
- AU／HKJC model registry = production；Tennis／NBA = shadow。今次冇改評分、模型、baseline、golden 或判決規則。
- 中央 evidence audit 正常，120/120 production decisions 可追溯；原有 pending approvals 及歷史 push failure 仍保留。

## 已實作修復（未上線）

1. **Tennis recovery 真正可以再跑**：用 `card-recovery-1`／`card-recovery-2` 獨立 slot，保留每日最多兩次；唔再撞 09:00 immutable manifest。
2. **Telegram `/retry` 唔再撞晚更**：用獨立 `telegram-retry-HH:MM:SS` slot，避免食咗或重用 22:00 正式排程。
3. **HKJC／Tennis／中央 subprocess UTF-8 容錯**：無效 diagnostic bytes 唔再拋 UnicodeDecodeError 蓋過真實 exit code。上游命令失敗仍然判失敗；冇將壞來源資料當成好資料。
4. **中央 timeout 清理 process group**：唔再只殺父程序，正常同組 descendants 一併終止，避免 worker 持續佔住鎖同 pipe。刻意 detach 去新 session 嘅程序仍然唔喺呢個邊界內。
5. **新增 `/recover au|hkjc|tennis`**：只接受 authenticated Telegram dispatcher 同固定白名單，使用已安裝 launchd recovery job。冇 `-k`、冇任意 shell、冇重置 retry 上限。回覆明確只係啟動確認，唔係復原成功。

修復分支：`codex/automation-resilience-20260909`。
Worktree：`/Users/imac/Antigravity-repo/.codex/worktrees/wc-automation-resilience-20260909`。
完整改動及 exact scope：本目錄 `automation-fixes.patch`、`scope.json`。

## 離開前仍需解決／驗證

| 優先 | 問題 | 證據及安全下一步 |
|---|---|---|
| 高 | 磁碟容量 | HOT 只剩約 15.84 GiB，低過 repo 20 GiB critical／30 GiB warning。先以已驗證備份及 restore proof 決定可歸檔內容，再批准清 source；今次冇刪用戶資料。一般 browser cache 合計只係數 GB，唔足以直接保證一個月容量。 |
| 高 | 停電／重新啟動 | `sleep=0` 已防自動睡眠，但 `autorestart=0`、FileVault On；全部排程係 GUI LaunchAgents。部機未成功開機／登入時，Telegram bot 無法執行。 |
| 高 | 遙距解鎖未驗證 | 本機 arm64、macOS 26.5.1。Apple 文件指 Apple silicon + macOS 26 可在 Remote Login 開啟、有網絡時經 SSH 解鎖 FileVault；今次 `sudo -n systemsetup -getremotelogin` 因需要密碼未能核實。需由另一部裝置／外網驗證登入及復原，唔好臨離開先首次測。唔建議為咗方便直接關 FileVault。 |
| 高 | 修復仍未 activate | release dry-run 判 automation、full gate、四線 production sync；不需要 installer 或 Dashboard deploy。必須正式 exact-scope release，再綁定 SHA approval，並等待現有 AU 工作結束／release preflight 允許。 |
| 中 | AU Dashboard 仍舊 | 10:32 左右 live JSON 有 HKJC 09-09，但 AU 仲係 09-07 Dubbo／Grafton／Tatura；本機有 09-09 Belmont／Devonport。需等 morning 完成後核實 production alias；檔案存在唔代表已發佈。 |
| 中 | D1 第二副本 | 03:20 本機 snapshot 約 7 小時新，restore_verified=true，但 warm_verified=false、cold_verified=false。外置碟有約 877 GiB，需 foreground verified backup 補 WARM；launchd TCC 要獨立處理。 |
| 中 | Drive mirror | AU 有 PermissionError，保留本機正本及 Dashboard 主線；唔可將 best-effort mirror 問題當成已備份成功。 |
| 中 | 健康報告侷限 | 主 checkout `健康.sh` 會讀到舊 NBA logs；Tennis DB mtime 新亦唔代表 card 成功。應以 canonical manifest、當日分析、live dashboard 三者一齊判。 |
| 中 | 同機監控盲點 | Telegram poller 每 120 秒執行，適合短暫網絡復原，但整機／供電／互聯網一齊停時無法自我通知。需要機外 heartbeat 或現場後備；今次未新增外部服務或訂閱。 |

最新 Tennis live feed 雖然 `analysis_run_id=tennis:2026-09-09`、`validation_status=valid`，其 generated_at 係上一晚；唔可以用呢個代替今朝失敗 refresh 已成功嘅證據。

Apple 參考：[Managing FileVault in macOS](https://support.apple.com/en-gb/guide/security/sec8447f5049/web)。

## 手機操作（修復上線後）

- `/status` 睇四線最新 run；`/slo` 睇歷史可靠性；`/storage` 睇容量；`/release` 睇等批版本。
- `/recover tennis`：沿用已有兩次 recovery 上限；耗盡後唔會任意重跑。要睇結果，唔只睇啟動訊息。
- `/recover hkjc`：使用現有 recovery job；未齊來源會繼續 pending。
- `/recover au`：使用 AU healthcheck 及已有自我修復路徑。
- `/retry`：AU 抽取補跑，原有 evening 模式及工作鎖保留；今次只修正 slot 衝突。
- `/health` 現時只係 AU 體檢，唔應當成四線／整機完整健康。

## 發佈及驗證

Release dry-run 已完成，12 檔 exact scope、無 unrelated dirty；risk=automation、auto_merge=false、auto_activate=false。本次未發 Telegram、未改 launchd／電源設定、未停止正在運作嘅排程。

已加入實際子程序／grandchild lock／無效 byte 測試，以及 recovery 兩次獨立 slot、第三次唔再啟動、Telegram 白名單及權限測試。最終檢查結果見同目錄 `validation.txt`。
