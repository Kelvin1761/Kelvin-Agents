# Tennis：ATP 排名有效日期錯配（唯讀診斷）

2026-10-29 Sydney。**已重現來源日期錯配；本文件無修寫資料或更改模型，未證實準確率影響。** 同日排名入庫數量嘅改善，只證明處理完整，唔代表來源新鮮。

## 原始證據

- [UTS 排名頁](https://www.ultimatetennisstatistics.com/rankingsTable) 實際擷取 HTML 標題為 `ATP Rankings Table 30-12-2024`，距本次觀察日 668 日。唔係只讀搜尋摘要；已保存 29,900 bytes 原頁、URL、UTC fetch clock 及 SHA256。
- 用現役 `_fetch_atp_uts` 相同參數（`current=1`、`rowCount=4000`、日期空白）讀取 `/rankingsTableTable`。450,584 bytes 原 JSON：total=2,161、rows=2,161，頂層只有 current／rowCount／rows／total，冇排名發布日期。
- 對原 JSON 行現役 `_parse_atp_uts_rankings(payload, '2026-10-30')` 得 2,160 行，**全部等同**今晚正常排程保存嘅 native raw receipt **25437**。其 `fetched_at=2026-10-29T07:21:30Z`，全部 normalized `ranking_date=2026-10-30`。
- 現役 parser 直接以 requested date／today 當 ranking_date；HTML 所示日期並未讀取或驗證。下一日分析要求被寫成來源日期，不能當已驗證嘅歷史發布時間。

來源頁日期同完整 transport 對照係強烈過期證據；JSON 本身未帶 effective-date receipt，**唔將 HTML 日期直接補寫到全部既有歷史 rows**，亦唔用今日官方排名去重建當時預測。

## 尚待獨立修正

1. 排名 adapter 必須保存並驗證真正來源有效日期及其原文；無日期／過期來源要明示失敗或降級，不能只換個 requested date。
2. 檢查 exception 後 cached fallback 及 `players.current_rank`，避免已錯標新鮮嘅舊 rows 繼續被當成通過日期檢查。`_rank_as_of` 只查 ranking_date 先後，唔會自行察覺其值係捏造。
3. 唯讀盤點受影響 receipts／rankings／features，先有完整備份及逐項 exact-plan 再修 live；不覆寫已保存預測、原始 receipts 或 graded 結果。
4. 新來源／日期修正與模型候選分開評估；舊 15 個 REJECT_DEV、frozen ruler 及 forward 標準保持不變。未量度前不能稱為準確率改善。

證據根：`/Volumes/Kelvin Hardisk 1/WongChoi-Archive/scratch/tennis-unified-20261028/rankings-effective-date/`；五份原始／對照檔及 `checkpoint.json`，checkpoint SHA256 `3bfe2db820fd92cdc3732ca0d987484d0158f62aa8518aa992bc89d2fbec8871`。只讀 live SQLite，無更新、重新分析或發送 card。
