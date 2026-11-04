# EXP-20261104-22 Tennis 舊履歷收據重連機制

2026-11-04。沿用 [EXP-21](EXP-20261104-21-tennis-terminal-receipt-clocks.md) 固定 9 場。126 個倒序引用對應 116 個獨立履歷 ID，涉及全部 9 場。Sackmann 104 個，TML 12 個。116 個全為 ACTIVE、無 canonical event key、無 append-only observation。用現存原文可核對當前版本同已保存 profile 嘅數值，但冇同一 ID 嘅觀測記錄可以直接還原最初綁定。

檢查 `git show 8e0a2385^:tennis-wong-choi/src/tennis_wc/ingestion/ingest_sackmann.py`。當時同一 `source_provider, provider_match_id, player_id` 衝突時，`ON CONFLICT` 原地覆寫發球、接發統計同 `raw_response_id`，保留 `created_at`。同一 writer 路徑服務 Sackmann 同 TML。現有 `history_observations.py` 對變動事實建新 ID 及留原版，舊資料未因此獲得歷史觀測。前者可產生實見時鐘倒序，單靠封存未能逐行歸因至某次舊匯入。兩個時鐘各有用途，現存關聯收據早過原定價嘅實見結論維持。

呢個結果支持舊版本以具體收據同原文驗證，唔採用 created_at 作原文版本時間。未識別最初收據，無新增合資格舊樣本或模型準確度結果。

## 重現

在 EXP-21 程式末尾附加以下段落。輸出只包含數目及狀態。

```python
affected={i for _,_,i in links if dt(versions[i][3])<dt(versions[i][2])}
counts=Counter()
for i in affected:
    row=conn.execute("""
    SELECT h.source_provider,h.canonical_event_key,h.history_status,
           (SELECT count(*) FROM history_observations o WHERE o.history_id=h.id) AS obs,
           (SELECT count(*) FROM history_observations o WHERE o.history_id=h.id AND o.observation_kind='CREATED') AS created_obs,
           (SELECT count(*) FROM history_observations o WHERE o.history_id=h.id AND o.raw_response_id<>h.raw_response_id) AS other_receipt
    FROM player_match_history h WHERE h.id=?
    """,(i,)).fetchone()
    counts[(row['source_provider'],bool(row['canonical_event_key']),row['history_status'],bool(row['obs']),bool(row['created_obs']),bool(row['other_receipt']))]+=1
print(json.dumps(dict(affected_unique_history=len(affected),affected_matches=len({m for m,_,i in links if i in affected}),breakdown=[[*k,v] for k,v in sorted(counts.items())]),indent=2))
```
