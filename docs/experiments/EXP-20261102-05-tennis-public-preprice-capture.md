# EXP-20261102-05：預測前公開輸入 capture 與 hot-source shadow 讀取

- 日期／平台：2026-11-02，Tennis；接續 [EXP04](EXP-20261102-04-tennis-indexed-shadow-native-readers.md)。起點 `95f26cbe4e63f9ce99cc82ac6f90bb30d4cfc029`。
- 工程假設：可在五秒交易截止內，從 mutable source 一致地讀取公開輸入，釋放來源後再寫 immutable artifact；公開歷史及排名讀取不再要求把整個私人 DB 凍結。
- 狀態：隔離研究分支，未部署或設定排程。沒有新模型候選、訓練、holdout、LL／Brier／ROI 判決。十五個 REJECT_DEV 及 frozen tennis-v1 不變。

## 實作與界線

`research_public_capture.py` 只選取 players、player_match_history、player 類型 provider_entities、player_aliases、rankings_history 及兩個既有 Elo cache。欄位清單來自 code 的 native schema；來源新增／移除未審核欄位直接拒絕。每個來源交易用 mode=ro、100ms busy timeout、最多五秒 cooperative SQLite progress deadline；中斷會 rollback／close，沒有 destination。這不是作業系統 I/O 的硬即時保證。

一個明示交易把上述表複製到 memory main，確保 WAL writer 在期間提交也不混合兩個來源版本。COMMIT／DETACH 後才 backup **只有公開資料的 memory main**，從來沒有 backup 整個 live DB。檔案 exclusive create、0400封存、SHA256、實際 captured／durable available 時計及來源 dev/inode 都記錄；外置目的地須確實掛載。

只為被公開表引用的 raw ID 保存 id/provider/endpoint/fetched/created 的整體 hash 和 missing flag，**不保存標頭明文、response body、fixtures、odds、predictions、ledger 或 feature snapshots**。原始 body 不曾在這次 capture 被讀取／驗證；缺失 ID 不會被標合格。這不是可移植 raw-ID catalog 或完整 wire receipt。

indexed builder 可以接受這種已封存的 capture，將 rankings 也固定在 revision。舊兩版 Elo cache 只放在 `generation_input_legacy_elo`／`generation_input_shadow_elo` 證據表，不能重新灌入 cold replay。frozen-source 舊路徑仍要求原 size/mtime/inode 和 read-only 不變；hot-source 分支只容許原 inode 上的新資料，進出 native_scope 均核對已引用 raw header hashes。header 改變、raw 消失或檔案替換會拒絕，來源新增未引用資料不影響已固定公開輸入。

`run-daily --shadow-public-input-dir <已存在目錄>` 是**預設關閉**的研究入口：在 ingestion／identity／slate audit 後、feature snapshots 前，完成 capture、cold revision、小型 shadow registry activation 及 receipt。失敗會在建立 features／predictions 前停止。這個 activation 只屬該目錄的研究 registry；不是 Central、production model 或下注 activation。

此入口沒有把 production feature/pricing 全流程改用 native_scope；正式 baseline 仍會讀 mutable source。因此「已在預測前保存公開輸入」不等於完整 runtime parity、完整 prediction evidence 或 qualified forward。研究 snapshot 仍強制 `UNQUALIFIED_RESEARCH_ONLY`／invalid／score 0；header 不變但 body 被改也不能靠本工具發現，相關限制保留。

## 實際唯讀擷取

外置根：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/public-hot-capture-v1/`。開始前內置可用22GiB、外置786GiB，確認真實掛載。第一個 sandbox 寫入未授權而失敗，未建立 artifact；通過自動審批後只匯出上述公開表及 hash，沒有重試先前被拒的私人 payload 匯出。

來源：`/Users/imac/Antigravity-repo/tennis-wong-choi/tennis_wc.db`，mode=ro。UTC 起點 `2026-11-01T23:33:14.440290+00:00`；captured `23:33:17.682900`；來源交易 **3.240170625秒**；封存／SHA 完成 available `23:33:22.535589`。不能把 captured 或 event date 當成 durable availability。

| 公開輸入 | rows |
|---|---:|
| players | 26293 |
| history | 427117 |
| player provider mapping | 18922 |
| aliases | 18346 |
| rankings | 257373 |
| legacy Elo | 394139 |
| shadow v2 Elo | 393033 |
| referenced raw header hashes | 621 |

missing optional tables=0、missing referenced headers=0。`public.sqlite` 約128MiB，SHA256 `c24ca5f19deb21f8f29f59fee16351431d4929bcfecf2730c1268367d82573c6`。0 missing header 只代表這621個 ID 的標頭存在，不代表原文／身份／PIT／整批特徵已合格。

## 全量 shadow 建置與 native pricing 診斷

同一 capture 建成約341MiB revision，未改任何身份／mapping。SHA256 `e337495ddb2714e89acd2f157061dfd1ece67637dee932439fcbf65e1269cb64`，build `2026-11-01T23:35:42.009700+00:00` 至 metadata available `23:39:36.473142`，registry register／activation 完成後 `knowledge_at=23:39:51.878632`。legacy／v2 舊 cache 另保留394139／393033行；冷重播不把它們重新寫回。

以**當刻來源全部**涉及2110或19626的5個 fixture ID 做唯讀診斷，不挑成功子集。5363、19533、22100成功 assemble 並呼叫 pure `price_match_snapshot`；三個 snapshot 均 invalid／unqualified。22221與22287均被現有 DISPUTED guard拒絕。沒有 store_prediction、feature writer、settlement 或下注動作。這是今日版本對歷史 fixture 的診斷，不是原決策重建或 fresh forward；也沒有對照／accuracy 結果。

完整 features／quotes／pricing 只在記憶體；外置只保存5個ID／狀態／snapshot與pricing hash。第一份結果把未加 `main.` 的查詢誤標為 artifact private table counts：raw／retention 實際解析到來源 TEMP views，回報26104／14。保留原件，`native-pricing-trial-v2.json` 明示更名 `scope_visible_counts_including_source_views`，並以直接 RO artifact connection 的 `main.<table>` 另驗真正儲存內容；七個私人／raw／retention表實際全部0。這個更正不改任何來源或 pricing。

全量建置啟動後，最終 code 把附加證據表的 input hash 排序由前兩欄收緊到全欄，另加 builder 端欄位白名單，拒絕偽造 capture 夾帶新欄位；上面大檔保留該次實際 input hash，不覆寫或冒稱最終重建 hash。cold replay／輸出數學未變；最終 code 的完整 capture／producer／scope 路徑另由測試核對，`final-source-v2/` 保存最終版本（`final-source/`保留加builder欄位白名單前的中途版本）。

## 驗證及未完成項目

針對測試包含 SQL authorizer 阻止任何 live 私人表／raw body 欄位讀取、byte scan 無私人 sentinel、單一 WAL snapshot、超時和 locked source 後可再次取得 exclusive lock、schema 漂移／缺表拒絕、新 destination 保護、來源 replacement、hot-source rank pinning、header 變更拒絕，以及 CLI capture-before-features／預設關閉／失敗停止。另有明示負例：只改 body 而不改 header 不會被此工具偵測，輸出持續 unqualified。

36項針對測試（19新增 capture／producer，加17既有 indexed tests）通過。初次 WAL 測試在關閉唯一 writer 後，macOS SQLite 的 RO attach 無法打開尚未建立 sidecar 的 WAL DB；保留 writer 連線並確實建立 WAL 後測得 concurrent writer／snapshot 一致性。沒有把失敗當成 PASS 或改來源權限。

最終 quick 通過。第一輪 full 在 sandbox 內 exit1：NBA relocation四項因 `ps` 被拒、APFS compression一項在sandbox內失敗；該輪Tennis1150項通過。原始失敗log保留；只用所需系統權限重跑兩組17項全部通過，沒有改其他平台code或tests。

隨後以同一最終code、所需系統權限重跑完整 `./檢查.sh`：**exit0、16 suites全過、unit suites814秒，Tennis1150 passed／28.35秒**。最終source freeze SHA在重跑前固定，封存時再次全部核對；不是把局部重跑當full PASS。此後只更新文件結果，程式與測試未改。

下一步是完整預測／市場／所有特徵的當刻證據合約、來源身份資格、實際 shadow pricing 的同版本接線及事前登記。新資料未過整批資格與 sample/power 要求前，不重開十五個失敗候選，也不宣稱準確度提升。

## 封存及重播入口

上述外置根 `artifact_manifest.json` 綁22個檔案，SHA256 `14ef9108bd25082b47054a53e37d520eae097b1dcd9cec3c98ea8cc820729c6a`。包括兩個public SQLite、唯讀封存registry、實際clock receipts、v1/v2診斷及script、兩版source、final code freeze，以及針對／quick／full成功和sandbox失敗／系統重查logs。原大檔及code hash封存後再核對；沒有把模型輸出值或私人payload加入manifest。

repo root以package context可用 `PYTHONPATH=tennis-wong-choi/src python -m tennis_wc.research_public_capture --help` 查看獨立唯讀capture入口；`--source`及全新`--destination`必填。`prepare_public_shadow(existing_parent, source=...)`才包含cold build／registry／receipt。`run-daily --help`已顯示opt-in flag，但本輪只用mock確認pre-feature順序／失敗停止，沒有對live執行整個run-daily或開啟排程。重播必須用全新目錄，不能覆蓋本輪封存件。
