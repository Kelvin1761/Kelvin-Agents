# Tennis研究交接：歷史規則resolver及point輸入盤點

目標仍為完成原統一計劃並證明分析準確度改善；尚未達成，不能以synthetic correctness或本次資料盤點代替。

## 已完成的可核對工作

- 已部署研究kernel `089037c12de47fd98f67b6c3b74983bb3c4b3ca4`，未接pricing。
- resolver候選`b18478aed7639fea975c3900a885be3ef31890a3`已完整gate通過（1329.8秒）、commit／push；當記錄本交接時，Central仍排隊等待AU release `9897d4aff372`的approval lock，沒有宣稱merge／activation。
- 候選scope：pyproject的JSON resource、rule_resolver.py、pinned slam_rules.json、驗證runner／58項新測試、EXP-23／INDEX／completion audit。110支援、2取消拒絕、1980接線比較一致；10513條既有Slam僅metadata規則路由。
- WTA-only點數盤點EXP-24：966 sides，302核實（151成對比賽、185玩家；5人≥5條），664暫扣；48 raw partial_match包括36個舊OK。只有current-cutoff input inventory，不是歷史PIT／訓練／模型資格。v1欄名錯誤中止已保留，v2及detail replay完成。

## 正在跑的release，不要重新啟動

原工作區：`/Users/imac/.codex/worktrees/tennis-observation-diagnostics/Antigravity-repo`。

本session工具handle `57993`（exec_command session）；先poll同一handle或查實際process，不能只因觀察timeout就重開。日誌：`/private/tmp/tennis-rule-resolver-release-20261101.log`。若已終止，先讀JSON的status／automation_status／manifest，再核對origin/main及`/Users/imac/wongchoi-scheduler` HEAD。

queue是有程序在等鎖，不是用戶未批准；用戶已授權自動發佈。不得人手重做另一份b184 release。若自動replay，驗證新SHA及`replayed_from`；若manifest過期，按AGENTS refresh流程處理。

最新補充：排隊270秒後，main／runtime已到`10f664defe68a29e9689d2aa370bae6cc383d78e`。同一live session57993已自動replay，新候選`37df3367b71f`正重跑full gate，日誌為`/var/folders/h1/br6y1s5j0nb07gfb5rjqxk6r0000gn/T/wc-release-gate-logs/37df3367b71f-full-sdxc6hs9.log`。不要重啟舊b184流程；同一handle會返回最終automation結果。此時尚未證實新候選merge／activation。

## 證據位置及接續

根：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/`，含resolver-v1／point-input-feasibility-v1及v2／native-feature-current-20261101T072544Z。hash與完整方法見EXP-23／EXP-24；原生feature inventory仍129 records／127 bundle／0 verified feature predictions。

EXP-24、INDEX及本交接先commit／push到`codex-tennis-point-input-notes-20261101`，是備份，未release。使用本對話原有且確認乾淨的notes worktree；舊`codex-tennis-unified-research-20261028`分支仍保留，沒有將其失敗model code帶入新分支。

待resolver release終態確認後，再將這份文件及EXP-24的有效診斷內容按exact scope交付main（先刷新其中的排隊／分支狀態文字）。不能為方便而改動正在審批的immutable candidate。

後續實質工作：先擴至Sackmann／TML原始point denominators與current-cutoff來源身份／可用性盤點，不能將WTA局部樣本量當全局缺資料；保持舊REJECT、歷史publication clock FLAG及F10依賴。另繼續真實輸入／capture缺口，不放寬reader、不切出失敗舊卡的33行製造forward。正式point-skill整合及LL/Brier改善仍未證實。
