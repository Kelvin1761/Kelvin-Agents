# EXP-20261104-17 Tennis 已保存 props 發球履歷時鐘

2026-11-04 06:43 UTC。承接 [13 日日期閘反例](EXP-20261104-16-tennis-history-date-guard-boundary.md)。只讀 `ranking-date-contract/source.sqlite`，沿用原封存 SHA256 `fb5638c6ad30476ea0a4d5aceb5462f20c271d6c9ee0ebc0f8a00b273f90f9fe`。全量固定 `prop_tracker`，按保存嘅 `profiles.serve_return.*.history_ids` 對履歷同原始來源 receipt。每個 prop 同一個 history ID 只數一次，唔將不同 market rows 當獨立比賽。

| 結果 | 數量 |
|---|---:|
| 全部 prop rows | 27,411 |
| 有 serve profile object | 1,111 |
| 有整數 history ID | 1,025 |
| 有引用嘅 distinct match IDs | 79 |
| prop／history ID 配對 | 41,295 |
| 有引用而 `is_point_in_time=1` 嘅 prop rows | 844 |
| 有引用而定價早過現存 fixture start 嘅 prop rows | 844 |
| 缺現存 history、定價、入庫或來源抓取時鐘嘅引用 | 0 |
| 現存入庫或來源抓取時間等於或晚過定價嘅引用 | 0 |
| 有 append-only observation 嘅引用 | 53 |
| 首個 append-only observation 等於或晚過定價嘅引用 | 0 |

已保存引用未見 13 日 bypass 嘅實例。呢次只檢查留低引用嘅 1,025 筆，約佔全表 3.7%。現存時鐘亦未證明原來用到嘅欄位版本、完場時間或者計算結果。兩個 844 分別係旗標同時鐘篩查嘅獨立計數。F02 下一步可喺呢 79 場先對來源原文、完場同版本身份，原固定開發及 holdout 分母維持。新增合資格樣本 0，未重跑定價、未量度準確度。

## 重現 SQL

用 `sqlite3` 開封存 DB，URI 加 `?mode=ro&immutable=1`。查詢只輸出 aggregate。

```sql
WITH p AS (
 SELECT p.id,p.match_id,p.match_date,p.priced_at,p.is_point_in_time,m.start_time_utc,
        CASE WHEN json_valid(p.pricing_evidence_json)
          THEN json_extract(p.pricing_evidence_json,'$.profiles.serve_return') END AS profiles
 FROM prop_tracker p LEFT JOIN matches m ON m.id=p.match_id
), refs AS (
 SELECT DISTINCT p.id,p.match_id,p.match_date,p.priced_at,p.is_point_in_time,p.start_time_utc,j.value AS hid
 FROM p,json_each(p.profiles) s,json_each(s.value,'$.history_ids') j
 WHERE j.type='integer'
), clocks AS (
 SELECT refs.*,h.id AS found,h.match_date AS history_day,julianday(h.created_at) AS created,
        julianday((SELECT min(o.observed_at) FROM history_observations o WHERE o.history_id=h.id)) AS observed, julianday(r.fetched_at) AS fetched,julianday(refs.priced_at) AS price,
        julianday(refs.start_time_utc) AS start
 FROM refs LEFT JOIN player_match_history h ON h.id=refs.hid
 LEFT JOIN raw_api_responses r ON r.id=h.raw_response_id
)
SELECT
 (SELECT count(*) FROM p) AS all_props,
 (SELECT count(*) FROM p WHERE json_type(profiles)='object') AS serve_objects,
 count(DISTINCT id) AS props_with_refs,
 count(DISTINCT match_id) AS matches_with_refs,
 count(*) AS prop_history_refs,
 count(DISTINCT CASE WHEN is_point_in_time=1 THEN id END) AS props_flagged_pit,
 count(DISTINCT CASE WHEN price<start THEN id END) AS props_before_current_start,
 count(*) FILTER(WHERE found IS NULL) AS missing_history,
 count(*) FILTER(WHERE price IS NULL OR created IS NULL) AS missing_price_or_created,
 count(*) FILTER(WHERE observed IS NULL) AS missing_observation,
 count(*) FILTER(WHERE observed>=price) AS first_observation_at_or_after_price,
 count(*) FILTER(WHERE fetched IS NULL) AS missing_fetch,
 count(*) FILTER(WHERE created>=price) AS current_created_at_or_after_price,
 count(*) FILTER(WHERE fetched>=price) AS current_receipt_at_or_after_price,
 count(*) FILTER(WHERE created>=price AND history_day<date(match_date,'-13 days')) AS late_created_old_date,
 count(DISTINCT CASE WHEN created>=price AND history_day<date(match_date,'-13 days') THEN id END) AS props_late_created_old_date,
 count(DISTINCT CASE WHEN created>=price AND history_day<date(match_date,'-13 days') THEN match_id END) AS matches_late_created_old_date
FROM clocks;
```
