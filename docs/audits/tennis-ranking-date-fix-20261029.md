# Tennis 排名來源日期與官方 ATP 榜：資料正確性審計

研究日期：2026-10-29 至 2026-10-30（Australia/Sydney）。這是輸入資料修正，不是準確度或 ROI 改善的證明。原有 15 個 `REJECT_DEV` 判決、frozen ruler、下注政策及既有 shadow 均不因這次修正而改變。

## 原因與來源

UTS 的排名資料原本用要求的分析日期代替來源日期。其獨立日期端點回報 2024-12-30，不能當作 2026 年的新排名；[原始診斷](tennis-ranking-effective-date-20261029.md)保存了實際來源及比對。現時先讀來源日期、將它帶入排名請求，並對過期、未來、缺日期及不一致的回應明確拒絕；保留原文和拒絕原因。WTA 與其他 fallback 亦使用來源實際日期，不再以要求日期補缺。

ATP 新增 [官方完整單打排名 PDF](https://www.protennislive.com/posting/ramr/singles_entry_numerical.pdf)。2026-10-29 捕獲的原始檔 SHA-256 為 `7d3871c0f10df7997f46284e8b896edd62306128fce89b1085e01c9ea4855864`：45 頁、2,295 行，來源排名日 2026-10-26。解析器核對每頁日期、頁碼及總頁數、排名序列、積分和、並列排名及欄位；缺國籍保持空值。PDF 原文及 SHA 綁定至新入庫的正規化 receipt；讀取時會核對來源、日期及原文 SHA，不能把一個任意 receipt 當官方來源。固定 `pdfplumber==0.11.8`，以 native Python 3.9 環境實際解析；安裝只新增依賴，沒有更換或刪除既有套件。

新實際來源用獨立 `source_provider` namespace，避免同日蓋過舊 composite 記錄。身份採用既有 canonical 規則；有衝突就留置，不做模糊猜測。只讀預檢 2,295 行：1,674 已對應現有 canonical，615 未能直接對應，6 留置；未對應不等於確定是新球員。原始頁面、來源日期回應、PDF、逐行預檢與 SHA 留於已掛載外置碟 `WongChoi-Archive/scratch/tennis-unified-20261028/ranking-date-contract/`。

讀取器統一處理 compact 日期、來源 receipt、freshness 與舊 UTS 錯標；新鮮官方榜可優先於較後但非發布日的賽事報名排名。有效替代來源保留，無有效來源時返回缺值及警告。歷史上不能證實發布時鐘的其他資料仍標為 historical/unverified，不因此成為合格 point-in-time 樣本。current rank provenance 指向實際選用的原始紀錄及日期；對手排名使用同一讀取守則。日期只有日精度，賽事同日的新榜不能僅憑日期證明當時已發布。新排名不覆蓋真正 Elo；可明確認出由錯標來源初始化的 mutable rank seed 在沒有真實 as-of Elo 時不再繞過攔截。

## 凍結語料與反事實輸入比較

完整原生 DB 以 SQLite 一致備份凍結，baseline `501867847af0ac0a1d51c80c1134ecce7f6e3eab`，SHA-256 `fb5638c6ad30476ea0a4d5aceb5462f20c271d6c9ee0ebc0f8a00b273f90f9fe`；來源及 live DB 不因重現而改寫。固定語料有 253,561 筆排名歷史，其中 997 筆 compact 日期、149,313 筆舊 UTS receipt 欠真實來源日期；其餘 104,248 筆只代表沒有發現這個已知 UTS 缺陷，不等於已證實全部合格。

15,896 筆 prediction 中，15,743 有可對應 match context；153 筆缺 match context，完整保留並列作 unresolved，沒有猜測或悄悄丟掉。對已能連接的 prediction，共有 12,832 個獨立球員／日期輸入；另外完整檢查 320,801 個 active history 對手／日期輸入。重建使用的是凍結時 DB，包括後來寫入的資料，**不是**當時原預測或已合格 point-in-time 回測。

四個預先列明的比較是原版、只正規化日期、只作來源守衛／fallback、以及兩者組合；逐項與完整 row-flow 證據保存於外置碟 `selector-replay-v3/` 和 `selector-replay-v4/`。原版 8,021 個球員／日期案例有排名；組合版 7,813 個，2,838 個數值／缺值狀態不同：402 由有變無、194 由無變有、2,242 有值但數字不同。對手資料有 14,936 個排名值及 5,813 個排名 bucket 不同。186 個可辨認的錯標 mutable rank seed 被攔截，9,524 個真實 as-of Elo 保持可用。這些是輸入敏感度，並非 2,838 場預測，也沒有使用賽果判定模型表現。

V1 因研究腳本 AST 位置資料不完整而在處理資料前失敗；V2 發現 153 筆缺 match context，故沒有當作完整回測；V3 保留所有 unresolved 原紀錄後完成全案例比較。V4 用完整相同凍結來源重跑，數值及 row-flow 與 V3 一致；因搜尋新鮮官方來源時檢查更多較舊 receipt，`ranking_source_date_unverified` 警告由 2,640 增至 3,119。V4 的讀取、特徵及日期檔案 SHA 與最終候選一致；其後只改入庫 transaction，並另以故障測試及 native 入庫驗證。新官方 PDF 的 native 入庫證據另存外置實驗目錄，不覆蓋上述失敗記錄。

獨立 native 入庫重現的第一次嘗試遇到 `database is locked`，當時有另一個只讀進度查詢，可能造成爭鎖；原因沒有以鎖追蹤獨立證實。工作副本保存了 98 筆新排名、99 個受更新球員、來源原文及完整錯誤，沒有改 live DB。這暴露單筆球員更新與排名寫入原先不是同一 transaction：現已改為每個球員更新、身份映射及該筆排名一起 commit 或回滾，並以注入排名寫入失敗測試驗證；整批不是原子 transaction，較早成功的行仍可保留，整批失敗不能標作成功。第二次重現不並行查詢工作副本。

第二次在同一完整快照、原始官方 PDF 及 native ingestion 完成，2,295 行中 2,289 行入庫、6 行按原身份規則留置，結果正確標記 `partial_identity_holds`。入庫前後逐筆指紋證明原有 25,300 份來源 response、253,561 筆排名、9,974 場賽事、15,896 筆 prediction、424,823 筆球員歷史不變；快照 SHA 前後一致。新鮮 ATP cache 由 62 個增加至 2,289 個獨立球員記錄。固定 2026-10-29／30 賽程中的 66 個 ATP 球員記錄由 36 個有可選排名增至 37 個；37 個使用官方 PDF。當中 14 個名稱含 `/`、看似雙打組合，不是經驗證的正式類別；其餘 52 個名稱不含 `/`，其中 37 個有排名。15 個未有排名的非斜線名稱中，有 3 個與官方榜姓名吻合但現有球員 tour 為 `UNKNOWN`，未按名稱猜測合併；其餘 12 個沒有找到相同正規化姓名。這是固定日期快照的覆蓋診斷，不代表其他日期或全部資料的覆蓋率，更不是準確率。

## 限制及後續

- 新來源是否改善預測，仍須事先登記並以具來源及決策時鐘的樣本外資料、同一 baseline、時間切分、適當消融與獨立 forward 驗證；新合格 forward 樣本目前仍為零。
- 過往 canonical 混合身份、153 筆缺 context、部分 legacy receipt 已缺原文，以及 raw pointer 已被後續流程覆蓋的 Elo lineage 尚未完整修復，不能推斷已經全部解決。
- 當官方來源整批存在身份衝突，安全行可處理，但衝突需保留並回報 partial；不能將成功入庫數當成來源完整或準確率證據。
- 現役 `run_daily` 會將 `RankingIdentityHoldError` 記為 `rankings_atp` source error，然後繼續其他階段；在該六個身份仍衝突、而來源仍包含他們時，應預期該來源繼續報 partial/error。`rankings_atp` 目前不是 `CRITICAL_SOURCES`；本修正不更改 readiness gate，也不宣稱排程整體健康。
- 其他莊家歷史賠率與逐場賽果可按既有研究協議使用；缺報價時鐘的歷史 ROI 不當成可執行或 Sportsbet forward 收益。
