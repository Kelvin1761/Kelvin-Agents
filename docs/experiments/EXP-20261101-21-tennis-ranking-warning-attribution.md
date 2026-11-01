# EXP-20261101-21：排名所選來源與被拒候選警告歸屬

狀態：研究候選，未部署。來源正確性比較通過；完整專案 gate／下游決策影響仍待完成，未證實準確度或 ROI 改善。

## 問題與事前固定

`RankingReader.select` 會累積被跳過來源的 issue，再將它們掛到之後選中的新鮮、來源日期已驗證 published ranking。這不能解讀為被選中 PDF 的來源日期未驗證。

在所有已保存 diagnostics 的 271 個 published-ranking 點，逐筆確認原始 receipt 與保留 live raw row 完全一致；既有 RankingReader receipt/PDF 驗證全部通過，但 123 個所選官方 ATP PDF 點仍掛 `ranking_source_date_unverified`。只證明所選來源與警告歸屬錯配，沒有重建原歷史排名選取，也不追認原 observation 的整體資格。

改 code 前於一次唯讀 live transaction 凍結全部 26,272 players、257,373 rankings_history，以及 184 份所引用的原始排名 receipt／ATP PDF captures。原始 archived body 經無損 accessor 核對還原；raw export 只含安全六欄，不複製 request credentials。玩家及歷史逐欄／ID順序 SHA 一致，沒有 missing raw ID。固定 cutoff `2026-11-01` exclusive、staleness 168h；這是當前排名資料固定選取比較，不是假扮歷史預測重播。

證據目錄：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/selected-ranking-source-audit-20261101/`。`full-selection-input/protocol.json` 及 boundary addendum 在最終候選重播前保存。第一輪 candidate 因補齊未知 receipt 日期／擷取邊界而中止，其紀錄保留，不當完成結果。

## 單一候選

只對所選來源是 fresh published 且 receipt 內確切 source date 已獨立驗證為所選 effective date，才將被拒來源 issues 移到 `selection_diagnostics.rejected_sources`。每條保留 history ID、`rejected_raw_response_id`、provider、原始日期及 issue。`feature_builder` 將此診斷帶入所選排名 provenance。

被拒 ID 不能冒充所選 `raw_response_id`，亦不自動成為 priced input 令每張 card 重複擷取所有棄用 body。原始 raw 仍保留。真正選中來源的問題、無法證實 source date、損壞 capture、舊 historical fallback、missing/stale 結果仍保留原行為；不以 mutable players.current_rank 繞過歷史。沒有改來源 registry、選取排序、rank 值、權重或資格規則。

## 全量比較

基線：26,272 玩家中 5,029 有所選排名、21,243 無排名；3,812 選到 fresh valid published row，其中 1,445 帶被拒候選的警告。

候選：26,272 行逐欄比較，所選 rank／row ID／raw ID／date 等數值欄零變化；1,445 個警告結果重新歸屬，保留 3,029 條 rejected-source 記錄。每條 issue 重新由原生 receipt validator 核對，issue 集合與原警告完全相同。其餘 24,827 行 warning 結果一致。輸入檔 SHA 不變。

針對性測試 46 passed，涵蓋有效 PDF 選取與診斷保留、損壞 PDF 回退仍警告、只有 publication label 但沒有可驗證日期時不可清警告，以及 rejected-source ID 不變成實際 capture input。快速 gate 通過；完整 `./檢查.sh` 在 `/private/tmp/tennis-ranking-selection-full.log` 運行，結果尚未宣告。

## 交付前仍需完成

- 完整專案 gate；記錄最終候選 SHA。
- 核對新 provenance 是否改變 data-quality／投注篩選、capture coverage 或報告行為；排名值不變不等於所有 decision／stake 不變。
- 不改原始歷史 observation，不將單筆診斷變正式 forward，不更改十五個 REJECT_DEV、holdout 或 frozen tennis-v1。
- 若判決或下注受影響，按原證據紀律量度並明示；沒有結果前只保存研究分支，不自動聲稱可提升準確率或部署模型。

`result.json` SHA-256：`8845575c46317fda9d8febee8ae7b8ed072fb807f3ecc31bc59b663792c6e90e`。

`full-selection-input/protocol.json` SHA-256：`6d1f53b1fb13434a94d1e274b01d457c1afcee93e4b1af7974da5a6acab43298`。

`full-selection-input/input-proof.json` SHA-256：`961d4b37d466f6f315a7a5ab7980e18ca1653f5fad6d7ca5e87ae50d07ddd3ab`。

`full-selection-input/baseline/result.json` SHA-256：`645c7d9de9dd944cd952c24d89cffe0ab399567aeae4da572b59055ebce49a4d`。

`full-selection-input/candidate-v2/result.json` SHA-256：`22706d42076509107be97b90e69a5fb901a53148a47a5ae71ae85288d6a3c1e9`。
