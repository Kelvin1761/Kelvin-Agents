# Tennis：身份合併目標檢查及排名批次留置

2026-10-29 Sydney；接續統一研究 F00。**資料／入庫正確性修正，未證實概率準確度或 ROI 改善。** 15 個研究候選維持 REJECT_DEV，模型權重、ruler、shadow 起點及判決不變。

## 現役問題及原始依據

Native daily log 連續回報 composite `uts:52300`：Aleksandr／Alexander Shevchenko；low-tier 來源 `KE64`：Toby Samuel／Stefan Kozlov。唯讀核對顯示兩者性質不同，不能用放寬 fuzzy threshold 一併解決。

- ATP `/rankings` 原始 receipt **25287** 有 2,160 行。原版寫到 77 行，第一個姓名異寫拋錯後整批停止，後面其餘球員亦冇更新。
- `sportsbet/player-stefan-kozlov` 指向 18527（Stefan Kozlov），其 merge pointer 指向 1180，現名 Toby Samuel。原 guard 只檢查 18527；之後直接返回 1180，將另一個姓名嘅 canonical ID 交出去。固定資料上已重現原版返回 1180；修正後拒絕，交易內屬性／映射不變。
- 同份來源嘅 `uts:50944`（Joao Lucas Reis Da Silva，401）及 `uts:32981`（Joao Silva，1512）均聲稱 canonical 471。不同來源身份未驗為同一人；不能按讀取先後／較佳排名選一個並覆蓋另一個。

全表盤點：16,527 個 player provider keys，244 個同 terminal 顯示姓名不相容，涉及 162 個 terminal IDs。**呢個係 review 清單，唔係 162 個已證實錯合併**；包括中間名／譯寫差異，亦唔證明其他 keys 已安全。

1180 涉及 534 行 ACTIVE history sides（含自己／對手兩邊，唔係 534 場獨立比賽）。可由保存 raw reference 讀出嘅 ACTIVE sides 包括：28 行 Sackmann Stefan、389 行 TML Stefan、71 行 TML Toby、17 行 TML Cannon Kingsley，另 2 行來源以 `KE64` 配 Alex Marti Pujolras。原始來源自己亦有矛盾，唔可以單靠改顯示名／移動全部舊賽績作修復；其餘未解 references 仍留未驗。

外部交叉參考保留：[ATP Toby／S0TM 比賽資料](https://www.atptour.com/en/scores/current-challenger/winnipeg/7542/results)、[ATP Stefan／KE64 賽事資料](https://www.atptour.com/es/scores/stats-centre/live/2025/637/MS001)、[ATP Inaki／M0NL 賽事資料](https://www.atptour.com/en/scores/current-challenger/plovdiv/3149/results)。Profile URL 部分 403，無冒充成功擷取，亦無用搜尋標題直接修寫身份。

## 修正

1. 保留原 provider-name／tour guard，抽出同一個既有選擇政策供唯讀預檢及實際寫入共用；返回 ID 前再驗 terminal 名稱／tour、斷鏈及未終止指針。失敗為具體 `PlayerIdentityConflict`，交易 rollback，唔自動改 canonical pointer。
2. 既有合併目標可省略中間名，但完整首／尾 token 必須相同、短名所有 tokens 按序存在。Tim／Taylor、不同中間名、不同姓氏仍拒絕。呢個係相容性檢查，唔係同名真人身份認證。
3. 排名寫入前檢查同日／同 tour 嘅 provider key、完整正規化姓名及 resolved canonical ID 重複聲稱；碰撞成組留置，唔揀先後。實際寫入仍重跑 identity guard。
4. 預先可識別嘅衝突及寫入時 `PlayerIdentityConflict` 留置該行，繼續其他可解析行；其他 DB／程式錯誤照拋，唔吞掉。
5. 原 `/rankings` receipt 保留**全部**行；另存 `/rankings/identity-holds`（206），連原 raw ID、輸入／已入庫數及全部留置原因。最後拋 `RankingIdentityHoldError`，令現有 CLI 照記來源錯誤，唔冒充全量成功或 cached success。

## 固定輸入 A/B

一份 **18,784,256 bytes** 唯讀投影：25,506 players、16,527 player provider keys、423,631 history identity rows及原排名 receipt。只保留 resolver 需要嘅 history ID/status 欄，唔係完整模型語料；無賽果選擇、無概率／ROI 評估。SHA256 `3a123fec42dc22172977225af1bd342ae03d23d481a32df7bdc5ed65dc7c6460`。原 DB 連線 mode=ro／query_only／一致 read transaction；兩邊只寫隔離 scratch，一個 arm 完成即刪工作副本。

| 同一 2,160 行來源 | 原版 974cc564 | 最終修正 v3 |
|---|---:|---:|
| 實際新增排名 rows | 77 | 2,153 |
| 明確留置 source rows | 第一個錯誤後中止 | 7 |
| 入庫＋留置完整流水 | 未處理尾段 | 2,153＋7＝2,160 |

七個保留 IDs：`uts:52300`、`uts:11550`、`uts:51226`、`uts:45169`、`uts:50944`、`uts:52408`、`uts:32981`。三個姓名異寫亦未強行白名單化，真正身份矛盾仍在；Joao 兩邊完整留置。來源整體仍為 partial／error。呢個結果證明尾段排名可被處理，**唔係命中率提升證據或新增合格 forward 樣本**。

錯誤迭代照保存：v1 嚴格 terminal 全名檢查造成 33 行留置，包括 28 個中間名差異；v2 加中間名後報處理 2,155 行，實際只有 2,154 rows，資料守恆 assert 揭露 Joao 覆蓋。v3 加批次碰撞檢查，實際 2,153 rows＋7 held 通過。三版 protocol、源碼、結果及 v2 失敗原樣保存；無用賽果調門檻。

## 驗證、交付及未完成事項

44 個相關測試、quick gate 通過，包含跨 tour／錯 terminal／斷鏈／cycle／有效鏈、中間名正負例、rollback、衝突後尾段仍更新、全部留置、未預期 DB 錯誤不吞、Joao 順序互換與新身份重複不建立。最終 immutable full gate／merge／activation 以 Central release manifest 為準。

證據根：原 external run 下 `player-source-integrity/`，包括 source projection、全表 review、三版 replay／lock、merge-pointer probe及原 receipt hashes。固定 projection／source SHA 在每輪前後核對。今次冇對 live DB 做 replay、補寫歷史、unmerge、重建 Elo、重發正式 card 或改舊預測／settlement。

下一個正常 run 須驗真實 `/rankings/identity-holds`、原 raw coverage、partial source error 及已入庫行數。Live legacy 身份／history／Elo 仍待逐項核對及有備份嘅 exact-plan 修復；244 review keys 唔准直接批量合併／隔離。Low-tier `KE64` ingestion conflict 亦未消失，不能因此聲稱歷史資料整體已乾淨。
