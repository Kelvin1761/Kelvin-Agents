# EXP-20261104-04：明示 tour 入庫接線及交易防護

2026-11-04 Sydney。工程候選：來源／原生對照及110項針對測試通過，正式full／交付待Central結果。未量亦未證實模型準確度或ROI改善。接續[全39人tour診斷](EXP-20261104-03-tennis-target-tour-lineage.md)。

## 來源診斷及事前協議

固定原39人，primary只讀、query_only、100ms busy及5秒deadline；每body上限2MiB、總量8MiB，關閉連線後才分析。原私人book資料留記憶體，只輸出公開ID、hash、計數及flags。

- 39個own-provider key全部由姓名slug產生，mapping名稱均吻合；這些key不是獨立人物認證。
- 38人的current raw pointer指向normalized odds list，1人屬其他回應/provider；共2份body、124820 bytes。
- 入庫用competition經分類器計算tour。odds list本來未必有top-level tour，因此EXP-03的「raw沒有tour」不等於上游缺gender資料。
- 直接沿38個pointer對應名字：原早期分類全UNKNOWN；相同來源文字經現有later enrichment，可辨識20人，18人未知。來源版本男14、女7、無標記18、矛盾0；版本數不是獨立人物數。
- 原39人read-only resolver比較，20個明示tour候選沒有身份ID移動；不等於全庫或未來樣本身份parity。

改code前封存`player-source-lineage-v1-20261104/`，10檔／59004 bytes；manifest `47f8b7091e4f67872c447c6404818a622ce24892cff6eb863a9a083f2229a30b`。候選協議SHA `69af9b559190eea67fc129869d284a8ab13953f6246b0aa466e6f295f8eb2c91`；baseline classifier SHA `f55d68851d1d4b0112027f6880fc26eba0001b9c39d76e2f6733bf62a693b551`。

## 候選與來源計數更正

只在舊prefix路徑得到UNKNOWN時，讀當前competition明示的men／women／ladies／ATP／WTA標記，重用既有`sportsbet_name_competition_meta`。須只有一種gender，而且既有helper支援該level及單打；無標記、矛盾、雙打不在此fallback補值。原curated dates、已知prefix、level／surface／indoor／MVP資格及reason不變。不從球員名或城市猜性別，不default ATP。

第一次native在固定20人的assert停下，未進入native寫入。完整同一份odds list其實另有公開target26414的同名明示tour記錄；其current pointer已指向其他回應，pointer-only盤點漏算。literal及casefold均為21，原20人沒有缺少。

原scope已包括全39人及完整來源。另行登記source-count amendment才重跑，沒有重抓、換窗、移除未知人或按賽果選樣；foreign receipt本身沒有當odds使用。保留原v1程式、protocol、assert失敗及診斷。這是來源reference判讀更正，沒有修改模型統計門檻、ownership或舊forward資格。

## 同批原生記憶體對照

E0用frozen舊classifier，E1用候選；每臂新建完整SQLite `:memory:` schema，seed相同39個公開名字／ID／UNKNOWN tour及name-derived mappings。兩臂使用相同requested-date filter、來源順序及原生provisional helper。原私人fixture只在記憶體；所有新SQLite連線只准`:memory:`，沒有DB／dump／payload匯出。

| 指標 | E0 | E1 |
|---|---:|---:|
| 同一receipt來源／native attempts | 60／60 | 60／60 |
| players／provider_entities／matches | 118／136／60 | 118／136／60 |
| 原39人ATP／WTA／UNKNOWN | 0／0／39 | 13／8／18 |
| tournaments／tournament_levels | 18／18 | 18／18 |

完整來源分類：UNKNOWN→ATP10筆、UNKNOWN→WTA6筆、ATP→ATP14筆、UNKNOWN→UNKNOWN30筆。受影響target共21，18人維持UNKNOWN；沒有把21人改成合格評估cohort。

除tour及執行時計外，players、provider mappings、match配對和其他tournament欄位逐欄相同，兩臂projection SHA均`4f24de58ea28fc7a13593adaaf3c1f96691c56b5aad9a213585aa1ee27a36c8b`。quick_check=ok；history／prediction／ledger／兩類odds表全0。沒有複製live history、aliases、cache或其他人物closure，所以不是production identity或pricing parity，也沒有評估準確度。

## 交易失敗修正

兩個紅測試證實：第二位球員身份衝突，或fixture寫入故障，原helper已分別commit球員／tournament，會留下第一位或兩位WTA更新；只有raise不足以證明rollback。

現在同一connection／transaction覆蓋雙側player與mapping、tournament／level及fixture；`upsert_tournament`新增可選connection，其他caller維持原用法。兩種失敗完整回滾，110項相關測試通過。native v3兩臂均用同一交易修正，只比較classifier；v2原交易對照另留存，沒有把兩個工程效果算成模型改善。

## 證據、界線及下一步

根目錄：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/`。

`book-tour-ingest-candidate-v1-20261104/`，27檔／132246 bytes，manifest SHA `3e93abec4d9bb531c5cd9b21a85818d4d9f8a814aaf4345bc1a1f84e32de3240`。三版native程式／protocol／結果、20人assert失敗與更正、三檔實際source、測試、75／110綠log及兩個原交易紅log都保留。私人body及nativeDB從未匯出；重驗需獲授權讀取原immutable receipt並先驗相同hash，不能冒稱完整私有資料可移植重播包。

正式full、immutable SHA、main及activation待gate。之後驗正常新receipt是否實際更新tour，以及identity／Elo lineage是否仍不合格；18人UNKNOWN不猜補。本研究未寫production DB、未改舊history／cache／alias／prediction／registry。原15個REJECT_DEV、tennis-v1、holdout、整批card及Sportsbet獨立forward保持；其他book只按training-only協議。
