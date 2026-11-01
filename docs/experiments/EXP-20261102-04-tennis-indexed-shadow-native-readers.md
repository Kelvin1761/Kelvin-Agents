# EXP-20261102-04：持久化公開版本及 native forecast 讀取接線

- **平台／日期**：Tennis，2026-11-02。
- **工程假設**：同一個封存版本可以同時供正式 feature builder、serve、ace、double-fault及games純讀取器使用；caller傳入原DB connection也不能混入另一份history。
- **舊紀錄／baseline**：[EXP02](EXP-20261102-02-tennis-identity-elo-cache.md)、[EXP03](EXP-20261102-03-tennis-memory-elo-generations.md)；研究checkpoint `fb5c1b83511176a9850160f1dfe3ba2c9e3645a5`。沒有新權重、fit、holdout或原15個REJECT_DEV重試。
- **狀態**：研究分支工程；未接live ingestion、沒有promotion／部署／實盤。LL／Brier／accuracy／ROI均未測。

## 實作及保護範圍

`research_indexed_generations.py`建立新的native-schema SQLite revision，保留真正history/player/date與Elo索引。只複製公開players、history、player provider registry、aliases；另保存原cache欄位供input追溯，再用共用原算法建cold legacy及shadow v2。unrated current Elo清空，缺as-of rating禁止回讀mutable current／rank seed。每個revision封成read-only，綁SHA、source identity、實際available時鐘、input及model hash。

獨立小型registry以application ID識別，只接受已封存revision；revision與activation表有append-only trigger。register同一路徑冪等；新activation或rollback只追加實際時間event。這不是跨路徑重建／儲存去重機制，也不是Central production activation。原tennis DB不可作registry目的地，未知、被替換或遺失registry不會被寫入或自動重建。

明示的`native_scope`按knowledge cutoff選版本，連接原來源只用mode=ro；source必須仍是同一凍結檔案。ContextVar把八組feature helper、player payload、rest days及兩版Elo讀取固定在同一revision；borrowed handle的close不會提前關閉外層版本。另四個接受conn的pure reader（serve_return_profile／player_ace_profile／count_profile／combined_hold）在scope內改用同一revision，foreign source直接拒絕。scope外沿用原connection；校準fit及賽後settlement不屬此forecast scope，沒有改動它們。

完整profile snapshot標記`+unqualified-generation`及`UNQUALIFIED_RESEARCH_ONLY`，data_quality強制invalid／0分；persist_derived／feature writer被拒絕。原raw／rank receipt不複製，RankingReader只經read-only TEMP view取原source（包括已retained的payload）。沒有移除既有warning來製造資格。

## 全量資料及原算法核對

凍結source SHA `fb5638c6ad30476ea0a4d5aceb5462f20c271d6c9ee0ebc0f8a00b273f90f9fe`，前後完整核對不變。兩個版本均有：

| 公開表 | rows |
|---|---:|
| player_match_history | 424823 |
| players | 25564 |
| player provider registry | 16527 |
| player_aliases | 18029 |

control不修身份；candidate只假設改既有八行2110→19626及兩個provider mapping，Jumpei alias保留。source與beforeimage不符會停止。canonical event key／正式supersession未改，所以依然不是可直接apply的repair。

三個Elo來源的401046行子集，兩版本各自的legacy、v2、20372位對照players、history opponent Elo，與EXP02相對應cold結果全數一致。每個revision約279MiB，建置於已確認掛載的外置碟；未複製2GB原DB。

實際revision內的matches、odds_snapshots、raw_api_responses、predictions、bet_ledger、feature_snapshots及retained_payload_blobs全為0；builder另查所有非allowlist表，不能有資料。沒有把私人fixture、quote、ledger或原文搬進公開revision。

## 正式 feature builder 的完整有界重播

選取**凍結DB全部**涉及2110／19626的4個fixture，四臂（原native warm cache、control cold、candidate cold、rollback）一律保留去向。各3個可組裝；22221在四臂均因既有DISPUTED guard拒絕，沒有改fixture或繞過guard。這不是Nov1 live bounded capture的5場範圍，不能把兩者混算。

- 三個可組裝fixture：warm→cold控制均有Elo欄位改變。
- 同cold政策比較identity-only，三個都有Elo／avg_opponent_elo等欄位改變；其他變動路徑全存結果，沒有把cache政策影響當成身份改善。
- rollback後完整numeric player feature值與control相同；較早knowledge cutoff仍返回candidate視圖；2025 cutoff沒有版本，不能回讀當前DB頂替。
- 所有完整snapshots只在記憶體使用；只匯出ID、row-flow、差異欄位、hash及error frame，沒有匯出市場／注碼／私人body。

這是以**今日code及今日才建立的版本**對舊fixture做counterfactual診斷。不是原prediction重建、歷史PIT、untouched forward、受影響注單數或準確度提升。

## 四個額外forecast reader的SQL核對

重用上述兩個封存revision及registry，完全不修改舊artifact。三個成功fixture的原numeric feature hash均與前輪一致。把caller原source connection直接傳給四個pure reader，source history SELECT數在control／candidate／rollback都為0；generation查詢數分別151／124／151。原native路徑為source32、generation0。

三個成功fixture的2110 profile，在serve／aces／double faults三路皆由control的4場變candidate的1場；固定identity修正分走其中3筆。剩餘1場仍低於各模型可用樣本要求，沒有提高資格或當成預測改善。

查詢數**包括驗證回傳history ID屬於該player的額外SELECT**，不能拿151與32比較速度或樣本數。所有回傳history ID的owner在所選版本核對通過，rollback全部profile輸出還原。fixture22221在此重播仍相同guard拒絕。

## 測試及未完成項目

17個新持久化／native／純reader測試通過，含受控6場→5場身份轉移、combined hold 1.35→1.30、雙時計、回退、source/revision更改拒絕、foreign DB、registry遺失不重建、無私人payload及只讀scope。初輪7個測試因mock bootstrap沒有alias表失敗；現時明示missing_optional_tables並在新revision初始化alias schema，並不追認完整身份來源。一次package測試因cwd缺scripts import而未collect，已在正確package context重跑。

第一次完整check為補齊額外forecast讀取路徑而中止（exit143），不當PASS；最終完整`./檢查.sh` exit0、16個suite全過，unit suites806秒，Tennis1131 passed；最終quick亦通過。測試後程式沒有再改，只補本文件實際結果。最後的純reader測試指令曾有相對路徑錯誤，修正後17項全過；未改模型參數遷就結果。

下一步仍是：安全的hot-source public capture／live ingestion producer、實際預測前保存generation receipt與全部inputs、來源／身份及整批feature資格、固定規則的fresh shadow／準確度實驗。目前builder刻意只接受read-only frozen source，不能直接指向live DB；inode／size／mtime pinning亦未取代production source catalog／portable raw-ID合約。完整forecast生成／定價／canonical evidence寫入及自動排程尚未接線。

## 證據及重播

外置根`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/`：

- `indexed-native-generations-full-v1/`：protocol、兩個public SQLite、registry、全Elo parity、所有fixture row-flow／差異欄位／result、執行script及source。manifest SHA `b6a7e7c16b631f0c8191d9934f4a17cbf7c834f97959f5cedc1b5b1803e1dee9`。
- `indexed-native-props-replay-v1/`：最終conn-pinning source、SQL route counts、profile hashes／owner檢查／全部去向。manifest SHA `211d2f44307dd9ffab65c558600f2b51870e571604bf060abdb47941cebda8ea`。此處記錄新helper之後的source SHA；前件DB module尚未有該新增helper，但原feature及四路Elo輸出已再驗相同。
- 在本輪source版本repo root，以`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tennis-wong-choi/src /Users/imac/Antigravity-repo/tennis-wong-choi/.venv/bin/python <artifact>/source.py`重播；OUT改為全新目錄，不覆蓋原件。props replay用舊registry唯讀，不重新activate。
