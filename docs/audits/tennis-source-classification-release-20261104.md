# Tennis 來源分類修正：正式交付補證

2026-11-04 Sydney。對應 [EXP-20261104-02](../experiments/EXP-20261104-02-tennis-te-classification-repair.md)。工程修正已交付；身份ownership／準確度目標仍未完成。

## 不可變發佈證據

- commit `5ff7691954cfafdf1603ff2fa830be7c249bafea`：七檔exact-scope、push exit0，現origin/main包含此commit。
- Central manifest記錄single-clean **full gate exit0**、785.905秒；scope與同一SHA綁定。原暫存gate log已被系統清除，所以不能再核對逐suite數目，本補證不聲稱Tennis總test數。71項針對測試及其完整log仍在原外置證據包。
- append-only事件：2026-11-03T16:00:10.826809 UTC merged；16:00:13.124843 UTC activation_succeeded，Tennis runtime由95c70ff0切到5ff76919並aligned。manifest本體的初始activation=not_started不是最後狀態，須合讀事件。
- 本次capture `2026-11-03T23:49:41.619797+00:00`：runtime HEAD `2cdee5f2b2fbcb91465ad4b1fd6a6d059b06b68f` 已包含其他後續發佈，兩個Tennis改動檔與5ff76919逐byte一致。

## 實際安裝及新來源

四份已安裝Tennis launchd plist均指向runtime，明示DATABASE_URL為原primary DB；四個label經launchctl print均loaded。這只證明載入／路徑，不能冒充每個run成功。

primary只讀／query_only／100ms busy／5秒deadline，掃描最新8份TE results receipts，最新ID26463。按activation時計，啟用後新receipt **0**；所以目前沒有新history row-flow／hold率證據，待下一次正常daily review。不手動回填舊receipt，不把隔離33日結果當實際production效果；qualified forward及準確度本輪未新增證據。

## 證據耐久與限制

原/private/tmp工作目錄及gate log在續跑前被系統清走；程式已由Central提交合併，所以不重建另一份release。原始49檔公開來源／隔離DB包與13檔tour-lineage包重新逐檔核hash成功，分別105176557及49346 bytes。未提交的tour文字由已封存notes／protocol／result恢復，沒有用記憶當新測量。

交付補證包：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/source-classification-delivery-proof-v1-20261104`；11檔／20585 bytes，manifest SHA256 `f946052d31963c4d01bdf88f476ccff7299a54eb388cbc4303e11fe64f07cdf5`。包含release manifest／events、兩個runtime source hashes、installed plist flags／loaded checks、兩包重驗結果及新receipt只讀診斷；無私人fixture／價格／投注payload，無正式DB寫入。

舊failed URL-only matrix／取消full143仍保留，這次full0屬不同候選SHA。沒有修改模型registry、既有評分或舊十五個REJECT_DEV；[全39人tour接線診斷](../experiments/EXP-20261104-03-tennis-target-tour-lineage.md)只提供下一步查資料線索。
