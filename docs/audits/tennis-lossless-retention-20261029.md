# Tennis：原始來源與 feature body 無損保存

2026-10-29 Sydney；接續統一研究 F00／C04／C17。**資料保存正確性修正，未證實模型準確度或 ROI 改善。** 原有 REJECT_DEV、來源資格閘、模型／權重、ruler 及 shadow 均不變。

## 已重現問題

舊 `database/maintenance.py` 每日清空超過七日、非最新嘅 `match_history` raw body 及 superseded feature body，但保留 row／reference。舊註解「冇 reader 讀舊版本」不成立：歷史來源審計、research evidence 及按 raw ID 查核仍需要原文。資料列未消失，原始內容卻已不可讀，不能再用 row count 當保存證據。

本次開始時唯讀 live dry-run：9 份 raw、33,648,066 UTF-8 bytes 已符合舊清理條件；feature 為零。呢個只係當時盤點，唔代表下一次排程後仍存在。舊空白欄位、上輪確認已缺失嘅 11 份特定原文並冇因此恢復。

## 修正及讀取合約

- 保留原本七日／最新版本 inline 政策；舊原文改存**同一 SQLite DB** 嘅 `retained_payload_blobs`／`retained_payload_refs`。原始 UTF-8 SHA256、長度、gzip SHA256 及逐 row reference 一併保存，跨 row 相同 bytes 可去重；來源 ID、fetched／created clocks、metadata 不改。
- 一個 savepoint 內先寫入、讀回驗證，再清原 inline body。任何壓縮、寫入、雜湊／長度錯誤會 rollback 整批，亦唔會 commit caller 原有 transaction。兩張 retention 表禁止 UPDATE／DELETE。
- 原文讀取統一經 `tennis_wc.database.payload_archive.read_payload`；native raw-ID evidence／歷史審計、settlement adapter、cached WTA 讀取及相關研究 scripts 已接入。共享研究 reader 還原 raw／feature，保留單份及整批解壓 budget；超限／損壞拒絕整批，唔截短語料。
- **直接 SQL 睇 `response_json`／`features_json` 可以見到空字串**，唔可以據此斷定原文缺失；要連同 accessor／receipt 判斷。未有 receipt 嘅 legacy 空白仍為空白，唔會從今日 feed 補砌歷史內容。
- 正常 SQLite backup 包含兩張 retention 表；備份後 VACUUM 及唯讀還原測試保留原文與 append-only triggers。備份／還原要保存完整 DB。舊版程式唔識 retention 格式，不能單靠回退舊 reader 讀取已壓縮資料；必要時須配合匹配嘅完整 DB 備份。
- 每份 archive 原文上限 128MiB；壞 receipt、zip bomb、尾隨 gzip member、截斷、inline 與 receipt 衝突均拒絕。壓縮不等於建立賽前可知時鐘、PIT 資格或新 forward 樣本。

Scheduler 改報「無損壓縮」及實際新增 gzip bytes；`bytes_freed` 只指 inline UTF-8 bytes，**唔係已退還 filesystem 嘅空間**。冇自動 VACUUM、刪外部備份或將原文搬離 DB。

## 完整凍結語料 A/B

控制版本 `dd82400750e1c3fafd0ba28cb1fd1c7e611e68ca`；使用統一研究原有完整 `warehouse.db`，SHA256 `67e62704fc83299ee1cb2172eed9a747aa9d46415bd24715c7fde6969aa02f58`，1,939,058,688 bytes。原檔唯讀，兩邊各用 SQLite consistent backup；每個 arm 完成即刪大型副本，全部位於已掛載外置碟。

事前 `protocol.json` 鎖定五份實作 source SHA、完整來源 SHA、keep_days=7 及假設清理日期 **2026-11-06**。呢個日期只模擬已擷取資料到期，冇使用該日新比賽／未來賽果。每張原表逐 row／column 核對；body 用 exact UTF-8 hash／長度，其他欄位照原樣計 logical hash。

| 同一完整語料 | 舊版控制 | 無損修正 |
|---|---:|---:|
| 處理 raw bodies | 60 | 60 |
| 處理 feature bodies | 160 | 160 |
| 原始 body bytes | 清空 240,516,742 | 原樣可還原 240,516,742 |
| 新增 gzip bytes | 0 | 9,742,621 |
| 原有 40 表 row counts | 全部不變 | 全部不變 |
| 原有 40 表 logical hashes | 2 表改變 | **全部一致** |
| Native 歷史來源 audit | 改變 | **完全一致** |

共核對 2,597,966 行。舊版 `header_matches_saved_source` 由 134,290 跌至 121,695，`unknown_raw_match` 由 860 升至 13,935；新版本維持原 audit 全部 counts／內容。呢個係來源可讀性證據，唔係比賽命中率。

兩個工作副本已刪；原來源檔 stat／SHA 鎖及實作 SHA 鎖通過。保留兩邊結果、全部表 hashes、native audits、源碼／protocol 及 `retained-bodies.sqlite` 作獨立核對。冇對 live DB 手動壓縮、修寫歷史、重建 Elo、重發 card 或改 settlement。

## 驗證與證據位置

145 個相關 archive／source／native tests、76 個 scheduler tests及 quick gate 通過，包括來源原樣、跨 namespace 去重、整批 rollback、caller transaction、read-only、解壓 budget、落盤後損壞拒絕、backup／VACUUM。完整 immutable gate／merge／activation 以 Central manifest 為準。

第一輪完整 gate 正確攔截一個未更新嘅 ablation harness 假連線測試（只實作 fetchone，唔支援新 reader 嘅 iterator），Tennis 為 920 passed／1 failed，其他 15 suites 通過；冇 stage／commit／部署。已換成真 SQLite，並補已壓縮新版本優先於舊 inline、archive 損壞不得靜靜 fallback 嘅正反例，再跑 native 全套及新 SHA 完整 gate。第一輪失敗 log 保留，唔將佢當成功 receipt。

外置證據：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/lossless-retention/`。重現入口 `replay-source.py`，與 `protocol.json`／`replay-summary.json` 一起保存；呢個係 storage correctness replay，唔係模型 A/B。

後續正常排程應驗無損壓縮 log 與 retained receipts。Legacy 缺失及混合身份仍須原始證據、完整備份、逐項 exact-plan 修復；不能用保存修正當成呢啲問題已解決。
