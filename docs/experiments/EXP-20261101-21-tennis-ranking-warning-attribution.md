# EXP-20261101-21：排名所選來源與被拒候選警告歸屬

狀態：研究候選，未部署。來源正確性比較通過；完整專案 gate 尚待完成；已完成下游固定輸入敏感度比較，未證實準確度或 ROI 改善。

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

## 259 份保留輸入的下游影響（2026-11-01）

另在改動前固定 protocol，對全部 259 份原樣 diagnostic observations，以每份原 prediction_created_at 固定 data-quality 時計；只對原始 receipt 已逐筆驗證的 fresh published current_rank 點作警告歸屬的反事實診斷。123 個點、73 份 observation 受影響。每份前後都以同一現役 model/pricing/filter code 重新計算，不拿兩個不同版本互相比。

全份 pricing payload 前後完全相同；decision、stake_units、confidence、risk、hard_no_bet_reasons、risk_adjustments 及 quality score 均零變化，前後均 17 BET／242 NO_BET。73 份 filter payload 的差異只在警告內容。這不保證未來任何輸入均不改 decision：目前的 warning penalty cap／其他 gate 也可遮住差異。

不以當前排名資料假扮過去原生 Reader 執行、不捏造原始 rejected history ID、不修改 canonical observation 或認列新樣本；這是已保存記憶體輸入上的局部影響隔離，非整條歷史 pipeline 重建，未使用 outcomes／ROI。第一版 trace 有一個欄位誤名（實際比 pricing 卻叫 filter），完整紀錄保留並另存 v2 更正；主要配對比較結果一致。

證據：同一外置來源審計目錄的 `downstream-warning-sensitivity-v2/`。完整專案 gate 仍以運行中的 log／最終結果為準；尚未部署此排名候選。

`downstream-warning-sensitivity-v2/protocol.json` SHA-256：`4860c6df83aa5ded4d492904c5b731a0d5fce784359249edfbce689afacb76f8`。

`downstream-warning-sensitivity-v2/result.json` SHA-256：`45ea62a55f4d45072887a3b47afb437acfc87886774ef9340a52a6a600f5bef3`。

`downstream-warning-sensitivity-v2/all-observation-comparisons.jsonl.gz` SHA-256：`635e358bfe15211002adb234b68bf46c916164ca3b2178cd9192c108091b99d8`。

**完整測試更新**：`./檢查.sh` 已全數通過，Tennis 989 passed。正式 immutable release gate 及 activation 仍需另查最終 manifest；未以此宣告已部署。

**正式交付**：`6b01f07f51bc6fbdd6f50af44a74a79240d21483` full immutable gate 通過（813.6s）、自動合併／activation completed。已直接讀取 `/Users/imac/wongchoi-scheduler` HEAD核對同SHA；排名值不變／下游配對結果不等於準確率改善。
