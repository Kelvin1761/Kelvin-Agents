# EXP-20261101-28：身份雙側 generation 的記憶體遷移與回退

狀態：**隔離研究機制完成；未修 live DB、未接 reader／pricing、未證明準確度改善。** 延續 [EXP-27](EXP-20261101-27-tennis-source-owner-repair-readiness.md)，不是把較小工程成果當作統一研究目標完成。

## 新增研究 API

`tennis-wong-choi/src/tennis_wc/research_identity_repair.py` 提供 `propose_split`、`apply_split`、`rollback_split`。入口拒絕有檔案路徑的 main／attached SQLite，另檢查 memory journal mode，拒絕預設磁碟暫存 connection；測試包括三種拒絕情況。這是記憶體研究工具，沒有 live CLI、scheduler、ingestion 或 pricing caller。

proposal 綁原雙側完整 before-images、目標 player metadata、完整 raw body SHA、來源 winner／loser external IDs 和 names、policy 及 proposal digest。只接受同一 response 的唯一相反視角、ACTIVE reciprocal pair、明確 tour、與來源標籤相符的非 merged target；UNKNOWN tour、額外視角、重複 source event、self-pair 或可疑已有 target event 都停止。collision 檢查在本次記憶體輸入內進行，**不是全 live DB／所有 alias、fixture、mapping 或跨來源 event 身份認證**。

apply 重新建立 proposal 比對，於 savepoint 內退役兩個舊行、新建兩個 generation、寫 supersedes 及實際修正時鐘。保留 existing upsert 的 CREATED receipt，另外追加最終 supersedes 已連接的 LINKED receipt；舊 before-images 及整批 proposal／after-images 亦有 append-only observations。caller 已開 transaction 時不替它 commit。

重跑 apply 驗 after-images、target metadata 及 raw hash 後返回原 receipt，不新增行。rollback 在驗 after-images／source evidence 後退役新行、完整還原舊行並追加觀察；不刪新 generation 或既有 observations。rollback 可重跑，但已 rollback 的同一 proposal 不准再 apply。來源／metadata／history 改動會停止，不覆蓋其他寫入。

**qualification 固定為 `SOURCE_LABEL_POLICY_ONLY_NOT_LIVE_AUTHORITY`。** 姓名／tour policy、來源 external ID 及 hash 都不是獨立人物身份證明；工具沒有修 provider mappings、merge graph、rankings、Elo、fixtures、immutable predictions 或 ledger。

## 測試及固定真實來源 pair

28 個 targeted tests 通過，涵蓋 dry-run 無寫入、雙側數目及 reciprocal IDs、supersedes／clock、冪等 apply／rollback、append-only、proposal 篡改、來源／target／history 變動、缺側／多側／錯 source role／未知 tour／merged target／錯名／no-op／self-pair／重複 raw、第二側失敗整批回退、caller transaction、三種非 memory connection 拒絕。

另從 EXP-27 的相同 frozen DB 只讀取 history 24211／24212、所需少量 players 及原始 response，複製到 `:memory:`。raw archive payload 解碼後保持完整 body；假設 target 仍為 19626，不把 exact-name leaf 升格為已審批 live 身份。結果：

| 檢查 | 結果 |
|---|---|
| proposal dry-run | 無新增寫入 |
| apply 後 ACTIVE 行 | **2**；原兩行退役，沒有 EXP-27 的 2→4 ACTIVE 問題 |
| supersedes | 新兩行分別指向 24211／24212 |
| 重跑 apply／rollback | 不新增寫入 |
| rollback | 原兩行逐欄相同；新 generation 留為 SUPERSEDED |
| 保留 append-only observation 行 | 12 |
| live DB／模型訓練／評分改動 | 無 |

proposal ID：`3d3815cb8b7de4c2421ffe974c5e2712ad6a5c132ae46e5e88d14563954b28c1`。
raw body SHA：`305a1f6320d09f714e2096d8cb452139033a7462de0853184751910fce5ff2c9`。

## 正式整合仍被阻擋：歷史 reader 的身份修正時鐘

同一隔離 DB 中，修正 generation 是本輪才新建；再用既有 `serve_return_profile` 以 `2025-01-01T00:00:00Z` cutoff 讀 2021 年那場，**仍讀到 1 行**。現行 `history_asof.guard_clause` 對超出 13 天的歷史行只靠 match_date，沒有一律按新 identity generation 的可用時鐘擋住。

這是具體反例，不能以「created_at 已填今日」聲稱未來資訊安全。它不等於整份歷史預測都已證實受影響，亦不是實際當年 prediction／bet 使用證據。**本工具不得接 live reader；先獨立定義、驗證並評估身份 generation 的歷史可用性合約，再修全範圍 mapping／fixture closure。** 不能為讓修補通過而順便改 frozen ruler、歷史窗或 holdout。

下一步是來源身份證明及 reader availability 合約；之後才可建立全 live proposal、核對完整 collision／回退範圍及實際 baseline/candidate 比較。所有 15 個 REJECT_DEV 和原 publication-clock FLAG 維持。內置約 6.4GiB，沒有新大型 A/B、DB 複本或 fit。

## 可重現證據

`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/memory-identity-split-v1/` 保存執行前 protocol、source.py、當時 module-source.py、proposal、apply／rollback receipts、result、artifact-manifest。

原命令：repo 根目錄，`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tennis-wong-choi/src /Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python /private/tmp/tennis-memory-identity-split-20261101.py`。原 frozen DB SHA 沿用 EXP-26／27 的已驗證來源，不倒填新 live 狀態。重播須改為新輸出目錄；來源兩行及假設 target 固定，不按預測勝負或 ROI 揀樣本。

真實 pair 重播驗的是遷移機制，target/source-label 判斷沿用現有 policy，不能當新增獨立人物 oracle；28 個合成測試亦不代表準確度增益。

驗證：`./檢查.sh --quick` 通過；`./檢查.sh` 完整通過（all suites，851 秒，Tennis 1093 passed）。程式未接現役，連同本文先保存研究分支 `codex-tennis-point-input-delivery-20261101`；不是模型 release／promotion。完整 gate log 原位 `/private/tmp/tennis-identity-repair-full-20261101.log`，另連同 quick log 複製到外置證據根的 `memory-identity-split-verification-v1/`。
