# Wong Choi 系統升級（2026-11-24 → 11-25）

起因：Kelvin 問「Wong Choi 可以點升級」。Claude 同 Codex（Sol，獨立意見）各自覆核，頭五項一致；Kelvin「幫我做哂你講既升級」。

| # | 升級 | 狀態 | 位置 |
|---|---|---|---|
| 1 | **市場尺**：模型喺收市價以外有冇資訊（排名改善 ≠ 投注改善） | ✅ AU（SP＋BSP）、HKJC 已上線 | `shared_racing/scripts/market_ruler.py`；合約「市場尺 m1」；EXP-20261124-90／-92、EXP-20261125-01 |
| 1b | Betfair 記錄器 BSP 一直 null | ✅ 修好兼補返 11-06 → 11-24 | EXP-20261124-91 |
| 2 | **異地加密備份**＋還原演練 | ✅ 工具、測試、排程 installer；⏳ **等 Kelvin 揀目的地** | `.agents/scripts/offsite_backup.py`；`central_wong_choi/install_offsite_backup.sh` |
| 3 | **實驗前功效預估** | ✅ AU／HKJC；合約 §6 加規則 | `shared_racing/scripts/power_precheck.py`；EXP-20261125-02 |
| 4 | **健康警報睇輸出新鮮度**，唔信退出碼 | ✅ `健康.sh` 排程段 | `.agents/scripts/job_freshness.py` |
| 5 | **Forward 測試總板**（四個 domain 一個格式） | ✅ 四個 tracker 寫快照、`健康.sh` 總覽 | `shared_wong_choi/forward_board.py` |

## 量到嘅結論
- AU 現行模型：對 Sportsbet SP Δll −0.00043 [−0.00159, +0.00078]、對 BSP −0.00037 [−0.00133, +0.00058]。
- HKJC 現行模型：對最終獨贏賠率 −0.00029 [−0.00066, +0.00005]。
- 即係兩個賽馬模型都冇市場以外可量度嘅資訊；排名改善嘅資訊市場已經有。BSP 比 SP sharp（nll 低 0.018／場）。
- 功效：EXP-20261122-32 嗰類（1.4pp × 9%）連理想訊號都 1/3 量到。

## 過程中搵到嘅問題
- Betfair 記錄器 BSP 18 日全 null（已修）。
- `central-wong-choi.research-review` 由 10-21 起每日 failed（NBA cursor 驗證失敗，例外訊息被吞；網球 11-15 起報告超過 128KB 上限）。
  新鮮度檢查第一次跑就標 ❌。**未修** —— 係 Stage5 研究覆核子系統（fail-closed、封印證據鏈），要獨立處理，唔可以重置 cursor 繞過。

## 要 Kelvin 做／決定
1. **異地備份目的地**：建議 Cloudflare R2（已經用緊 Cloudflare；~10GB 喺免費額度內）。要開一個 bucket（例 `wongchoi-offsite`），
   然後 `python3 .agents/scripts/offsite_backup.py init --backend r2:wongchoi-offsite`、**將 `~/.wongchoi_offsite.key` 抄落密碼管理器**、
   `./.agents/skills/central_wong_choi/install_offsite_backup.sh`。
2. 要唔要用市場尺取代排名尺做 KEEP 條件（合約話留畀 Kelvin）。
3. HKJC 落注定義（而家冇，所以量唔到 HKJC 賺唔賺錢）。

## 異地備份實測（本地測試目的地，2026-11-25）
- 第一次全量：45 組、203,469 個檔、加密後 2.4GB、55 分鐘（外置碟細檔讀得慢）。
- 第二次：重用 41 組、只重傳 4 組（主要係全日都寫緊嘅網球 DB）、7.5 分鐘。
- 還原演練：隨機 4 組（包括 3,498 個 HKJC 快照檔）全部冇缺、冇大細／內容唔對。
- 之後加咗 `gdrive-export-20261121`（舊 Drive 資料唯一副本，1.9GB，唔變 → 只上傳一次）。
- 未包：`hkjc-history`（15GB）、`tennis`（5.2GB）—— 視乎目的地容量，要 Kelvin 揀。

## 刻意冇做
- 冇重寫四個 forward tracker 嘅判決同推送（已上線、有用）；總板只係記錄同總覽。
- 冇改任何模型、排名、注單。

## 第二輪（2026-11-25，Kelvin「go ahead with 1 - 7 except 5」）

| # | 升級 | 結果 |
|---|---|---|
| 1 | 模型對落注嗰刻嘅價（早更／前一晚 Sportsbet） | **冇額外資訊**（EXP-20261125-05）；`market_ruler --price early` |
| 2 | 證據唔再靜靜斷 | 規則「搬嘢要抄快照、原位留低」＋`evidence_integrity.py`（健康.sh）；**唔做** sha256 代位（會破壞封印設計：搬咗本身就係證據改變） |
| 3 | research-review 去留 | **暫停**（launchd 移除，plist 存 `WongChoiControl/paused-launchd/`；code／cursor／證據保留） |
| 4 | 長期紅燈 | 5 個賽後抽場次排除；AU「未開盤」唔再令 run partial；NBA 撞鎖被取代唔計入 SLO（94.5% → 98.4%） |
| 6 | 紙上測試 | 總板顯示 ROI＋CI（未到判決點標明唔准提早停）；去到判決點而預先登記判決 REJECT／STOP → ⛔ |
| 7 | 減 code | 移除 203 個冇人提到嘅 scratch 檔（清單＋還原命令：`docs/archive/scratch-removed-20261125.md`）；防線測試唔准正式 code 行 scratch |

### 異地備份：Google Drive（將來選項，Kelvin 2026-11-25 想用）
- **唔可以**寫入 `~/Library/CloudStorage/GoogleDrive-*`：launchd 讀寫嗰度會 PermissionError 或者無聲卡死（Drive 退役原因）。
- 可行做法：`rclone` 經 Google Drive API（唔經 CloudStorage 資料夾）。Kelvin 喺瀏覽器授權一次（`rclone config` → Google Drive），
  唔使信用卡；token 存本機 `~/.config/rclone/rclone.conf`。`offsite_backup.py` 加 `rclone:<remote>:<folder>` 後端
  （put／get／delete 用 `rclone copyto`／`rclone deletefile`），其他（加密、分組、保留、演練）全部照用。
- 暫時：Kelvin Hardisk 1 照用（`./備份.sh`）。
