# 發佈「一 merge 就過期」：現況量度同改善方案（待 Kelvin 批）

> 狀態：Kelvin 2026-10-21 批准。**A、B、C 已完成**（B+C 見 §7）；D 未定。

## 1. 而家點運作

`./保存.sh` → `release_manager.prepare_release` → `release_automation.auto_approve_release` → `release_approval.approve_release`：

1. **準備**：喺 worktree 跑 `./檢查.sh`（full 或 quick，按 policy），commit，push 去 release 分支，寫 manifest，
   記低 `rollback_target = origin/main`。
2. **攞鎖**：`auto-release.lock`。有另一個 release 揸住 → 即刻報「another automatic release is running」放棄。
3. **批准前**：`origin/main` 一定要仲係 `rollback_target`，否則「approval expired」。
4. **批准 gate**：喺 clean clone 對**同一個 SHA** 再跑一次 `./檢查.sh`（clean clone 冇資料根，只有數據合約一步會 skip）。
5. **gate 之後**：再 fetch，`origin/main` 仍然要等於 `rollback_target`，否則「changed while approval gate was running」。
6. fast-forward push 去 main，再 activation。

設計上保證嘅嘢（呢份方案**唔會放寬**）：
> **每一個落到 main 嘅 commit，都喺「佢落去嗰一刻嘅 main」之上、對嗰個確切 SHA 跑過完整 gate。**

## 2. 量度（2026-10-07 → 10-21，`WongChoiControl/releases` + `release-events`）

| 項目 | 數值 |
|---|---:|
| manifest 總數 | 210 |
| 最終 merged | 152 |
| superseded（refresh 取代） | 34 |
| `pushed` 但從未 merge（殘留） | 16 |
| `push_failed` | 8 |
| 需要 >1 次先 merge 到嘅改動 | 15%（131 個入面 19 個） |
| 準備完到 merge（批准段）中位數 | 5 分鐘（p75 6、最長 275） |

**過期時，main 期間改咗嘅檔案同 release 範圍有冇重疊**（只計有 commit message 可配對嘅 15 次）：

| 結果 | 次數 |
|---|---:|
| 完全冇重疊 | **11（73%）** |
| 只撞 `docs/experiments/INDEX.md` | 3 |
| 真正撞檔（`hkjc_daily_schedule.py`） | 1 |

另外有 43 個 manifest 冇 commit message（大概係某條自動化路徑），呢批無法配對，冇計入。

2026-10-21 我自己五次發佈入面四次要重做：兩次係 shared 大型語料測試超時（已修，b7849740），
兩次係 main 被 NBA／dashboard release 推前。四次全部冇撞檔。

## 3. 問題喺邊

1. **已經有工具但冇人知**：`central_wong_choi.py refresh --commit <sha>`（`release_refresh.py`）會將過期 release
   replay 去新 main、重新 gate、**自動 reject 舊 manifest**。`AGENTS.md` 冇提，所以 agent（包括我）都係人手開新分支重做，
   舊 manifest 就留喺度變「pending」殘留 —— 上面 16 個 `pushed` 殘留，至少有部分係咁嚟（我今日嘅 34897e27、9e249bfc、3663707a 就係）。
2. **冇撞檔都要成個流程重來**：過期之後要再跑「準備 gate + 批准 gate」兩次 full check。而 73% 嘅過期，main 改嘅嘢同今次完全無關。
3. **鎖係「攞唔到即走」**：等緊另一個 release 嘅時候唔會排隊，要人手 `auto_approve_release.py` 重試；
   等嘅期間 main 一郁就過期。
4. **INDEX.md 係人人都 append 嘅檔**：佔咗剩低撞檔個案嘅 3/4。

## 4. 方案（由低風險到高風險，逐步批）

### A. 文件同習慣（零風險，建議即刻做）
- `AGENTS.md` 加一段：過期就用 `python3 .agents/skills/central_wong_choi/scripts/central_wong_choi.py refresh --commit <sha>`，
  唔好人手開新分支；舊 manifest 會自動 superseded。
- 順手用同一工具清走而家 16 個殘留 `pushed`（逐個確認已經喺 main 或者已被取代先 reject）。
- **已做（2026-10-21）**：重新點算後，31 個 `pushed` 入面 26 個早已 `approval_rejected`（第 2 節個 16 係我用錯事件名多計咗）；
  真正殘留 5 個。reject 咗 4 個（34897e27、9e249bfc、3663707a 係我嘅；7457c827 內容已經以 ac0c507a 入 main），
  reason 全部寫明取代佢嘅 commit。留低 20e2fcf8（另一個 agent 1 個鐘前嘅 dashboard release，內容未入 main，可能仲做緊）。

### B. 批准時嘅「無撞檔自動 replay」（code 改動，要測試）
喺 `approve_release` 第 3 步過期嗰陣，唔即刻放棄，改為：
1. 計 `git diff --name-only rollback_target..origin/main`，同 manifest `scope` 求交集。
2. **有交集 → 照舊過期**（要人睇）。
3. 冇交集 → 喺 clean clone 將 release commit cherry-pick 上新 main；唔乾淨 → 照舊過期。
4. 對**新 SHA** 跑完整 gate（第 4 步原本就要跑，所以唔係多跑），通過先 push 新 SHA 去 release 分支、寫新 manifest、
   舊 manifest 記 superseded，然後 fast-forward main。
5. gate 期間 main 再郁 → 重複最多 3 次，之後照舊過期。

保證不變：落 main 嘅仍然係「喺佢落去嗰刻嘅 main 之上、對嗰個確切 SHA 跑過完整 gate」嘅 commit。
**唯一分別**：唔使再跑多一次準備 gate，亦唔使人手介入。

風險同對策：
- *冇撞檔但語義衝突*（例如 main 改咗我呼叫嘅 function）→ 由對新 SHA 嘅完整 gate 捉，同而家任何 release 一樣；唔會弱過現狀。
- *scope 漏報*：交集只信 manifest `scope`；replay 後再核對「新 commit 改嘅檔 == scope」，唔等就放棄。
- *model 類 release*：policy risk 係 model／deployment 嘅，replay 後照樣行 activation 預檢；可以選擇第一版只開放 docs_tests／code。

### C. `INDEX.md` 用 union merge（細改動）
`.gitattributes` 加 `docs/experiments/INDEX.md merge=union`：兩邊各加一行就自動兩行都保留。
配合 B，將 INDEX 撞檔變成「冇撞檔」路徑；B 第 3 步嘅 cherry-pick 會用到。要測試 union 唔會整亂排序（INDEX 係按 EXP 編號排）。

### D. 攞唔到鎖就排隊（細改動）
`single_run_lock` 攞唔到時，等最多 N 分鐘再試，而唔係即刻報錯。配合 B，等完發現 main 郁咗都會自動 replay。

### 唔建議
- **放寬 SHA 重驗**（例如「main 郁咗都照 merge」）：會打破第 1 節嗰條保證。
- **一次 approve 全部**：`release_refresh.py` 已經寫明點解唔做 —— 每個 merge 都會令其餘過期。

## 5. 建議次序

1. **A**（文件 + 清殘留）—— 今日可以做完。
2. **B + C** 一齊做（C 令 B 覆蓋多 3/4 嘅撞檔個案），寫測試：無撞檔 replay 成功、有撞檔照過期、cherry-pick 唔乾淨照過期、
   gate 失敗唔 push、gate 期間 main 再郁會重試同封頂。
3. **D** 最後，視乎 B 上線後仲有幾多「攞唔到鎖」。

## 6. 重現

```bash
python3 docs/plans/scripts/release_expiry_stats.py     # 讀 ~/WongChoiData/WongChoiControl
```

## 7. B+C 實作（2026-10-21）

- `release_automation.auto_approve_release`：`approve_release` 報過期 → fetch → `_replay_conflicts`
  （`git diff rollback_target..origin/main` ∩ manifest scope，減去 origin/main 上 `merge=union` 嘅檔）→
  冇衝突就 `_replay_release`：喺臨時 `git worktree --detach` 跑現有 `refresh_release(auto_approve=False)`
  （cherry-pick、準備 gate、push 新分支、舊 manifest superseded），再對新 SHA 行 `approve_release`
  （clean-clone 完整 gate + main 不變檢查 + fast-forward）。最多 `MAX_REPLAYS = 3`。
- **同方案嘅分別**：仍然係兩次 gate（refresh 嘅準備 gate + 批准 gate），唔係一次。要慳嗰次就要喺 `prepare_release`
  加「跳過 gate」開關，我寧願唔開呢個口。慳到嘅係「人手介入」同「等人發現」，唔係 CPU。
- `prepare_release` / `refresh_release` 加 `auto_approve=True`（預設不變）：replay 自己揸住批准鎖，唔可以再遞歸觸發。
- 人手 `approve_release`（Telegram `/approve`）**完全不變**，照舊一過期就停。
- C：`.gitattributes` 加 `docs/experiments/INDEX.md merge=union`。
- 測試：`tests/test_release_replay.py`（10 個）——無撞檔 replay 並且 gate 嘅正正係落 main 嗰個 SHA、唔郁 caller checkout、
  撞檔照停、replay 後 gate 失敗唔 merge、非過期錯誤唔 replay、上限 3 次、人手批准不變、INDEX union 可以 replay、
  冇 union attribute 照停、repo 真係有 union 設定。release 相關 45 個測試全過。
