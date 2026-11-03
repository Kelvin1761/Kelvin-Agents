# EXP-20261104-02：TE 來源分類與 history 寫入防護

2026-11-04 Sydney。公開資料隔離驗證完成；`5ff76919` full gate exit0、已合併及Tennis activation成功，見[正式交付補證](../audits/tennis-source-classification-release-20261104.md)。**未評估亦未證實模型準確度提升。**

## 問題、規格及範圍

接續 [獨立來源規格更正](EXP-20261104-01-tennis-header-source-correction.md)，每個當前 head 重設 URL／icon／label，以明示來源判 ATP／WTA；draw 由雙側 actor namespace 判定。icon-only 不捏造 URL；未知、矛盾或沿用前 head 的資料不得寫 history。結果 API 原比分與 winner 保留。

history 只收單打；未知／相反 target tour、拒絕解析的既有相近名字、同一 canonical player 對賽、既有 history 事實或狀態衝突皆留置。雙側 player／alias／history 以同一 savepoint 寫入，第二側失敗不得留半場或孤兒。原文 receipt 先獨立保存，留置原因按日／raw ID 計數回報。不回填原文前的 summary，不改舊 history、cache、球員 tour、權重、評分、ruler 或十五個 REJECT_DEV。

### fixture 歧義及修正

v2 寫入量為 11,358 個來源版本／22,716 次 upsert，但實際只有 22,714 行、11,357 canonical keys。逐一追查發現 2026-10-28 Spasova／Yashina 的同一來源對手、日期、比分對應兩個 detail ID：3361187／3360223。兩份公開詳情分別寫 main round／qualification；不能證明係兩場實體比賽，也不能自行判定哪份正確。兩筆位於同一主結果表，並非 sidebar 混入。

v3 保留 optional `match_source_ref`；history 必須有唯一官方 detail ID。同一當前來源 context／actor pair 對應不同 ID，或同 ID 對應不同 actor pair，一律整組留置；比分互相矛盾亦整組留置。相同 ID／相同事實仍可 idempotent upsert。未改 canonical key namespace，未做跨日或跨 provider 獨立賽事證明；這些仍是後續資料資格工作。

## 固定輸入及消融

同一公開 source manifest `ace4fb34d970f1f26c43291052a534216d64efb5d5dbd60b4205525f8d7ba0d1`，全部 34 版本／33 日，沒有重抓或按結果選樣。baseline parser 綁 6d3fd8c2；來源規格獨立綁 1605d038。舊 URL-only failed matrix、取消 full terminal143，以及 v2 歧義結果照保留。

| 分類臂 | 來源版本數 | 相對 legacy tour 不同 |
|---|---:|---:|
| C 原結果／原 tour | 14,325 | — |
| D 只留來源單打／原 tour | 11,783 | — |
| T 全結果／明示 tour | 14,325 | 6,215 |
| DT 來源單打／明示 tour | 11,783 | 5,116 |

全部原始 dataclass 欄位、winner、score payload 與 baseline 完全相同；分類 warnings 0，parse skipped 319。2,542 雙打版本在結果 API 保留。這是分類消融與資料 parity，並非準確度／ROI 消融，版本數不當獨立比賽樣本量。

## 原生隔離入庫

另按原協議取全部33日每一天最新 completed-day receipt；抓取 UTC 日須晚於來源日，所以排除一份同日未完 Nov1 的76場研究版，沒有改上述34版矩陣。只建全新本機DB，seed同一39位公開名字／ID／UNKNOWN tour；不複製 live history、cache、alias、fixture、prediction、賠率或 ledger。SQLite connector 限定唯一隔離路徑。

- parse 14,249 版本，parse skipped316；接受11,356版本，實際22,712 history／observation rows，11,356 canonical keys。
- 留置2,893：雙打2,537、未知target tour144、相反target tour150、既有名字未解決59、同一resolved player1、fixture歧義2。
- 5,380新players／aliases；全部39位UNKNOWN seed的history仍0，不能以23個來源全名吻合當獨立ownership。
- 每key恰好雙側、sum(won)=1、自賽0、SQLite quick_check=ok。六個私人業務表全部0。
- v3相對v2新增 semantic rows0，只移除歧義key的雙側2行；所有其餘姓名／tour／日期／勝負／來源／tournament事實一致。canonical keys 仍未證明獨立實體賽事。

只讀 primary 的 `_ExistingHistory` 快取 query 探針：Nov1 1,062行約0.754秒、Nov2 846行約0.089秒；query_only／100ms busy timeout／5秒deadline，不代表整體入庫SLA。正式DB本研究寫入0；完整production hold率未量。

## 驗證、封存及重現

71項 TE parser／history／receipt／classification 針對測試通過；quick通過。曾錯寫不存在的測試檔名，該次no-tests不算pass，已以實際四檔重跑。正式single-clean full gate在5ff76919通過（exit0，785.905秒），merged及activation_succeeded事件已核實；原暫存gate log已清除，不另聲稱逐suite數目。之前取消的full不能冒用。

公開證據包：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/kernel-f02-rules-20261101/classification-repair-v3-20261104/`；49檔／105,176,557 bytes，全部hash重驗並設唯讀。manifest SHA256 `35c895bc1372e27966df49a45594922adb3845d4815de2ac75495490706e8bdf`。包內保存v2 source／DB／歧義詳情與失敗資格、v3完整source／protocol／DB／diff、全34版比較、獨立detail-ID audit及測試log；無私人fixture、賠率、投注payload。

重播：對封存包先核對manifest及原source manifest；將各run.py複製到全新輸出目錄，設定其work路徑到與candidate-source逐檔SHA相同的checkout，再以本機venv Python及 `PYTHONDONTWRITEBYTECODE=1` 執行。native harness拒絕已有DB、檢查外置碟／內置空間、在執行前寫protocol並於結尾重驗程式hash。不能以舊result當新候選結果。

結論：來源工程驗證通過，準確度與ownership仍未通過。正式gate／activation已驗；啟用後尚無新TE history receipt，下一步驗實際新receipt留置，再處理 source-owned身份及可重建 Elo generation，維持原時間切分與Sportsbet獨立forward；其他book只按既定training-only協議使用。
