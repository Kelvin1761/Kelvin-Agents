# Tennis：缺 Elo 輸入及真實歷史來源核對

2026-11-03；接續[原始部署後 card 審計](tennis-rank-reference-release-20261103.md)。**這是輸入診斷；沒有量度或證明準確度提升，沒有改 live history、身份、cache、權重或 qualification。** 原十五個 REJECT_DEV 及 frozen ruler 不變。

## 全量缺值範圍

沿用原審計 activation 至 inventory as_of 的全部三份原始 card，沒有重新挑樣本。唯一非空 card 的 55 個原始 observations 中，28 個缺一邊或兩邊 Elo：12 個兩邊、16 個一邊，共 **40 個 player sides／39 位 unique players**。另外兩份空 card 不算樣本。原 prediction clock／match day 不變；讀原始私有輸入只在記憶體，匯出只有 IDs、counts、flags、hashes。

以預測前已有的公開 frozen input `public-hot-capture-v1/revision.sqlite` 比對全部 40 sides；SHA256 `e337495ddb2714e89acd2f157061dfd1ece67637dee932439fcbf65e1269cb64`，整份雜湊及唯讀狀態核對。這份輸入的 generation available_at 早於原 prediction，但仍屬 `UNQUALIFIED_RESEARCH_ONLY`，不能冒充已合格歷史 replay。

| 檢查 | player sides |
|---|---:|
| 缺 overall Elo | 40 |
| 在較早公開 snapshot 未有該 player ID | 21 |
| 該 ID 有賽日前 owned history | 0 |
| 該 ID 有 Elo 可用 winner edge | 0 |
| warm legacy as-of cache 可用 | 0 |
| cold rebuilt as-of cache 可用 | 0 |

winner edges 使用實際 runtime `ELO_PROVIDERS`：`jeff_sackmann`、`tennismylife_history`、`tennisexplorer`，要求 ACTIVE、有效對手及賽日前資料。初版曾硬寫錯兩個 provider 名；已改為 import 真實常數再跑，保留原失敗版本／protocol／結果，所有 absence/cache 數字相同。不能將錯名版本當正式依據。

**結論限於這份較早輸入及這些 IDs：重建同一份資料的 cache 不會憑空補出這 40 個 Elo。** 21 是 sides，不是 21 位 unique players；亦不代表外部世界沒有歷史，或現有身份一定正確。

## 現時資料及 routing 核對

2026-11-03T11:52:39Z 起，另在 primary live SQLite 做單一唯讀 transaction，耗時 0.1913 秒；mode=ro、query_only、busy timeout 100ms、5 秒 cooperative deadline。全部 39 IDs 仍存在、沒有 placeholder。按同 tour normalized exact name、已登記 canonical 及 alias 關係查候選，沒有其他候選帶可用 history/cache。

其中 player 26414 現有一筆賽日前 ACTIVE history 及 as-of cache；其餘 **38 位**在自身 ID 仍沒有賽日前 owned history 或 as-of cache。這是「現在讀到舊 event day 前的紀錄」，**不能把今日取得／建立的資料倒填成原預測已知**。Exact name／現有 alias 也不是獨立 source identity proof，未涵蓋所有縮寫、改名或未登記分身。

另核對已安裝四份 Tennis launchd plist，其 DATABASE_URL 均明文指向同一 primary SQLite；不是誤讀另一份 DB 的證據。只查這個特定 routing 問題，不等於四 domain run health 或完整 storage 審計。

## TennisExplorer 已有每日接線，並有真實新 receipt

在 `e0798a0cc75cb24cf57c2ef28193150cd3f4deea` source tree 核對：

- `tennis_daily_schedule.py:review_previous_day` 會先呼叫 `top_up_lowtier_corpus`，後者執行 `build-lowtier-corpus --start <review day>`。一般 daily 路徑覆盤 yesterday；same-day refresh 路徑不經這段，skip-review 也會跳過。因此不能說 TE history 完全未接排程。
- `run-daily` 本身另跑 composite 的 ESPN history、當年 TML low-tier、再 rebuild Elo；不等於 TE 歷史多年 backfill。production 設定的 default history window 為 21 日，但不能套用成 TE top-up 的 window。
- TE history writer 的 source receipt 修正已正式交付；`_store_history` 目前寫 `surface=None`、`format=BO3`、`round=R`。原始賽果 receipt 完整不表示這些派生欄位已驗證；不能單靠補 overall Elo 聲稱 surface／props 合約齊備。

2026-11-03T12:09:58Z 起另核對固定兩個新 TE receipt。primary SQLite 唯讀 transaction 2.6285 秒；讀完關閉連線再在記憶體 parse HTML，沒有發網絡請求或再次入庫。URL、match date、entity day、來源 fetch clock、receipt clock、HTML SHA256 均一致：

| raw ID | source day | 真實 fetched UTC | parsed results／skipped | 現時連結 ACTIVE history rows |
|---|---|---|---:|---:|
| 26285 | 2026-11-01 | 2026-11-02T07:00:07Z | 531／14 | 1,062 |
| 26463 | 2026-11-02 | 2026-11-03T07:00:12Z | 423／10 | 846 |

兩筆均 HTTP200、`tennisexplorer-results-html-v1`，每個 parsed result 對應兩邊 history row 的數量一致。HTML hashes 分別 `ba68693e0338076b9e34b922af6c96eb97664cafa02a42842e50020ff95fc8bb` 及 `86e5bf754e474aecda139c0fcd586f8179c7865afc1dcb4bf99cc505b50ac217`。

第一份 receipt 早於上述原 55 forecasts，第二份晚於 forecasts；後者不能用作舊預測已知輸入。這完成「正式 source 修正後有沒有真實新原文」核對；沒有獨立證明每行 actor ownership、歷史 availability、場地或模型準確度，亦沒有新增 qualified forward。

## 固定 33 日窗口的 primary receipt 盤點

按下節事前固定的 2026-10-01 至 2026-11-02 日曆窗，先只盤點現有 primary receipt，沒有取決於球員勝負或是否有資料。最新 100 筆 TE endpoint metadata 已跨過窗口起點；窗口內 33 日各有一份 receipt，其中 **2 日有 hash 核對的 HTML，31 日只有摘要或未驗證內容**，沒有無 primary receipt 的日子。這不代表其他封存目錄沒有原文，也不代表整體 archived corpus 審計已完成。

唯讀 transaction 3.4178 秒，使用現役 retained-payload accessor 核對壓縮保存，不能把 inline 欄位空白直接算原文遺失。初版在窗口篩選前直接 parse inline body，遇到空欄而 JSONDecodeError；原 script／protocol／空 stdout 及失敗原因保留，修正 accessor 後才產生正式結果。沒有改任何 source row。

已另外重驗既有 `te-source-capture-20261101/public-parity-v1/` 的兩份公開 HTML：10-31／11-01 的 decoded SHA 與[原實驗](../experiments/EXP-20261102-01-tennis-te-source-capture.md)一致，manifest SHA `dec00b524af0e2e05cb9a1d04aff8881fdb69c31895a6c11896750af4e0c4cbc`。因此至少10-31在已知外置研究artifact有原文；不可由primary的31日缺HTML推斷全數必須重抓。11-01較早research版本與較後production版本分開保存，不能當同一內容或完整性相等。

這31日中已識別10-31的外置研究原文，其餘30日尚待既有archive盤點；未宣稱它們沒有原文。下一輪先完成這個盤點，再決定缺頁擷取範圍；沒有授權用摘要追認來源，也沒有因為只有兩日原文而縮小 39-player 分母。尚未逐來源核實全部 39 位身份或取得整窗可用 history。

對全部39位球員另做既有來源的首輪候選盤點：兩份已知外置HTML加兩份production receipt，合共4個內容版本、3個unique source days。沿用現役name normalizer做完全相同名稱比較，39位均沒有exact-name候選；未作模糊配對或自動合併。這只說明這個不完整來源集合未找到相同normalized字串，**不代表39位都沒有歷史，也不證明縮寫不屬同一人**。獨立身份確認仍為0；完整33日來源及source profile/context仍待處理。

## 下一個固定範圍實驗

下一輪先做 **source coverage／identity pilot**，不是重新調參。事前鎖定以下範圍，結果無論正負都保存：

1. cohort 保留上述全部 39 位球員及 40 sides；連到原 55-card 的 IDs/hash，不因有沒有找到資料而縮小分母。
2. 固定公開結果搜尋窗為 2026-10-01 至 2026-11-02；primary 33 日 receipt 盤點已完成，但其餘 archive 原文仍待核對。缺頁才作有上限、按來源規則的公開擷取；保存 URL、實際 fetch UTC、內容 hash、parse/skipped/error，未完成日子照列，不以今天 fetch 假扮歷史 availability。
3. 逐來源核對球員識別及 tournament/date/opponent context。Exact-name 只能產生候選；沒有獨立 ownership 證據的留 unresolved，不自動合併 live 身份。記錄全 cohort 的 found／ambiguous／absent／source-error。
4. 隔離建立符合身份合約的 history 候選；unknown surface／round／format 保持 unknown。比較每位可用賽數、overall 與 surface Elo 覆蓋，以及來源依賴；不寫 primary DB，不對舊 card 追認資格。
5. 只有 lineage／兩個 cutoff／整批輸出與 rollback 合約通過，才按既有 generation 計劃預登記輸入候選及完整 ablation。原 15 個失敗假設不藉換窗重開；此搜尋窗只量 coverage，不用來選最有利準確率。
6. 最後才作同語料 baseline/candidate 的時間 folds、LL/Brier／校準及 Sportsbet 獨立 forward。沿用每 family 至少 600 個 match clusters 及 power 要求；其他莊家逐場 odds／ROI 僅供訓練研究，無報價時鐘不當可執行回報。

單日 top-up 成功、history/cache 覆蓋增加、rank 格式通過，都不能代替最後模型驗收。

## 可重現證據

外置共同根為 `/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/`：

- `missing-elo-availability-20261103/`：12 個 script／protocol／結果／log 全部唯讀，逐檔 hash／bytes 重驗；`artifact_manifest.json` SHA256 `1b403ab730dd3ce2249b166f8c17378fb4dbe6394b80f9ca648d7f5c5800b299`。
- `te-live-source-receipts-20261103/`：4 個 script／protocol／結果／log，唯讀封存並逐檔驗證；manifest SHA256 `5e602f4d7de169363636990477f047d682336b081748c2ae2ce4fd4daccce53a`。未匯出 HTML、姓名、價格或私人 snapshots。
- `te-source-window-inventory-20261103/`：8 個 script／protocol／結果／log／初版失敗紀錄，唯讀封存並逐檔驗證；manifest SHA256 `b16d0ccef5227d81a6d484ae572192e293c2943f13466a99686898e4bb61a556`。只輸出 33 日 source metadata，不輸出原文。
- `missing-elo-existing-source-pilot-20261103/`：4個script／protocol／結果／log唯讀封存，manifest SHA256 `3fbc5091297d682b49d10bb06b39b3dde3e876fe0961f410f44be1f3fba27df1`；只含IDs與候選定位hash，不匯出名字或HTML。
- availability 依次執行 `audit.py`、`current.py`，receipt/window/existing-source pilot 各執行 `audit.py`；均用 `PYTHONDONTWRITEBYTECODE=1`，載入實際 runtime package。availability/receipt/existing-source pilot 用 primary Tennis venv Python；window 用 system Python3。live source 在其他 run 後會改變，重跑不能要求 current counts 歷史相等；原次結果以封存 protocol/result/hash 為準。

八個外部 GitHub 項目 URL、固定 commit、檔案版本及資料用途繼續保存在[來源 manifest](../plans/tennis-external-project-sources-20261028.json)及[比較筆記](../plans/tennis-external-project-review-notes-20261028.md)。本次不下載或執行外部模型，也沒有修改評估把尺。

## 本次交付驗證

在基底 `e0798a0cc75cb24cf57c2ef28193150cd3f4deea`、僅上述文件改動的 worktree 跑 `./檢查.sh`，terminal exit0；16 suites全過，Tennis1096 passed／45.49秒，Shared1798 passed。ruff、AU/HKJC golden、模型說明及資料合約亦通過；既有Agent scripts兩個expected failures仍明示保留。這是repo程式驗證，不是四線營運健康或準確度評估。完整本次log SHA256 `efbc1a22e6e16416edd12d7bd82ba3993f8931afc2e2ed2933a3ee55a11d8c71`；來源及診斷的長期可重現檔案按上列四個artifact manifest保存。


2026-11-03 UTC／悉尼11-04接續：[固定33日來源pilot及draw／tour缺口](../experiments/EXP-20261103-14-tennis-te-draw-tour-coverage.md)已取得30日缺頁、核對32個source profiles，完成離線parity，重現兩項新history入口分類問題；全39人仍沒有獨立ownership確認，沒有回填舊card或聲稱準確度提高。下一輪修正前四臂比較已固定。
