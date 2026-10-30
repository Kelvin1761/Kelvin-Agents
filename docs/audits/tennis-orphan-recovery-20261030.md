# Tennis 缺失賽事 context：舊備份原文追查

2026-10-30（Australia/Sydney），只讀調查[排名日期修正審計](tennis-ranking-date-fix-20261029.md)中 153 筆缺少 match context 的 prediction。原凍結 DB SHA-256 `fb5638c6ad30476ea0a4d5aceb5462f20c271d6c9ee0ebc0f8a00b273f90f9fe`，以保存的全部 unresolved prediction 為起點，不猜配對、不改 live DB。

153 筆 prediction 對應 63 個不同 missing match ID。這 63 個 ID 均有 feature snapshot，共 330 行：126 行 inline 仍有內文；204 行 inline 空白，使用 `read_payload` 確認沒有可讀 retention receipt。原快照對這 63 個 ID 沒有 match result、fixture observation、odds snapshot、market prediction 或 prop tracker；feature provenance 引用的三個 raw ID 指向 `/mock/odds`，不能把這些當真實賽事資料或市場時鐘。

## 備份調查與原文保存

逐筆對照五份較舊備份的 snapshot ID、match ID、player ID、feature-set version 和建立時間：2026-08-26 `tennis_wc_pre_pit_20260826.db` 包含全部 204 行的非空內文。其後兩份 2026-08-27、2026-08-29 快照及一份 2026-09-03 backup，這 204 行已為空；另核對 2026-10-28 `warehouse.db` 亦為空。六份所查備份均沒有這 63 個 match ID；不代表其他備份不存在。

2026-08-26 來源備份 SQLite `quick_check=ok`，讀取前後 SHA-256 一致，為 `37446fb2a27319f8344879c015d1f5bec3d13d9a93352147ffab2f6fad9d79db`；204 行完整原文 JSONL 的 SHA-256 為 `d0d4c2a942806499cfa793a6953c9c4a16fbdee8964b17f72dd731193d25e554`。已將可逐行驗證的舊備份原文、每份 body SHA、完整來源備份 SHA／SQLite `quick_check` 和讀取腳本留在外置 `WongChoi-Archive/scratch/tennis-unified-20261028/ranking-date-contract/orphan-context-followup-v1/recovered-feature-evidence/`；其他五份備份的逐筆比對與其局限亦保存於同一 followup 目錄。這是恢復研究證據，不是修改正式 SQLite 或證明樣本合格。

## 後續

先尋找可獨立驗證的歷史 fixture、原始賽果及當時來源時鐘，核對球員身份、賽事、日期和 source ID；未找到前，63 個 missing matches 仍保持 unresolved，153 筆 prediction 不進準確率／ROI 評估。204 份原文亦不自動成為 point-in-time、真實比賽或新 forward 證據。
