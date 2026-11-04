# EXP-20261104-21 Tennis 完成比分收據時間

2026-11-04。沿用 [EXP-20](EXP-20261104-20-tennis-serve-profile-parity.md) 9 場／96 prop rows。對每個 distinct match／定價時鐘／history ID 精確連接現存 raw response ID 同 source match key。讀取公開 season-file receipt 原文，要求來源相同、HTTP 200、match_history、key 唯一。完成比分及點數篩選沿用 EXP-18 封存。呢度量嘅係已捕捉到完成比分嘅最遲上限，來源完場時刻依然未知。

| 核對項 | 結果 |
|---|---:|
| 去重 match／定價時鐘／履歷引用 | 198 |
| 履歷 ID | 167 |
| 原文收據 | 16 |
| 收據／source match key 組 | 164 |
| 抓取早於定價 | 198／198 |
| 最短抓取至定價間隔 | 270 秒 |
| 現存履歷 created_at 早於現存關聯收據 fetched_at | 126／198 |
| 上項最大間隔 | 9,193,257 秒，約 106.4 日 |

164 組都有 tourney_date，162 組有 minutes。掃描所有列嘅欄名只見呢兩類時間相關欄位。賽事日期同時長未足以推算實際完場 UTC。

抓取時間可為完成比分已出現提供上限。126 個倒序引用表示現存履歷建立時鐘唔可以當成現存關聯收據版本嘅首次知悉時間。今次未確定倒序係邊個程序造成。F05 固定候選嘅原判決維持。C14 仍欠逐場結束時計，F10 仍欠合資格驗證分母，新增合資格樣本 0。

## 重現

同 EXP-20 嘅命令及固定輸入。以下 unified diff 套用到 EXP-20 程式後，會追加本輪嘅聚合輸出。

```diff
--- exp20.py
+++ exp21.py
@@ -4,0 +5,2 @@
+from datetime import datetime
+from tennis_wc.database.payload_archive import read_payload
@@ -39 +41,2 @@
-for match, blob in conn.execute('SELECT match_id,pricing_evidence_json FROM prop_tracker WHERE pricing_evidence_json IS NOT NULL'):
+links=set()
+for match, priced, blob in conn.execute('SELECT match_id,priced_at,pricing_evidence_json FROM prop_tracker WHERE pricing_evidence_json IS NOT NULL'):
@@ -46,0 +50 @@
+        links.update((match, priced, i) for i in profile['history_ids'])
@@ -82,0 +87,44 @@
+from collections import defaultdict
+
+versions = {}
+receipts = defaultdict(set)
+for history_id in {i for _,_,i in links}:
+    r=conn.execute("""
+    SELECT h.source_provider,h.tour,h.source_match_ref,h.provider_match_id,
+           h.created_at,h.raw_response_id,r.provider_name,r.fetched_at,r.status_code,r.entity_type
+    FROM player_match_history h JOIN raw_api_responses r ON r.id=h.raw_response_id WHERE h.id=?
+    """,(history_id,)).fetchone()
+    assert r['source_provider']==r['provider_name'] and r['status_code']==200 and r['entity_type']=='match_history'
+    key=(r['source_match_ref'] or r['provider_match_id']).rsplit('-',1)[0]
+    receipts[r['raw_response_id']].add((r['tour'],key))
+    versions[history_id]=(r['raw_response_id'], key, r['fetched_at'], r['created_at'])
+source_clock_fields=Counter()
+source_group_count=0
+time_like_columns=set()
+for rid,keys in receipts.items():
+    body,=conn.execute('SELECT response_json FROM raw_api_responses WHERE id=?',(rid,)).fetchone()
+    raw=json.loads(read_payload(conn,'raw_response',rid,body))
+    for tour,key in keys:
+        hits=[row for row in raw if isinstance(row,dict) and f"{tour}-{row.get('tourney_id')}-{row.get('match_num')}"==key]
+        assert len(hits)==1
+        row=hits[0]
+        source_group_count+=1
+        time_like_columns.update(k for k in row if any(word in k.lower() for word in ("date", "time", "start", "end", "minute", "finish", "complete")))
+        for name in ('match_date','tourney_date','start_time','start_time_utc','end_time','end_time_utc','completed_at','finished_at','minutes'):
+            if row.get(name) not in (None,''):
+                source_clock_fields[name]+=1
+def dt(s):
+    d=datetime.fromisoformat(s.replace('Z','+00:00'))
+    assert d.tzinfo
+    return d
+gaps=[]
+inverted=0
+relink_gaps=[]
+for _,priced,history_id in links:
+    _,_,fetch,created=versions[history_id]
+    gaps.append((dt(priced)-dt(fetch)).total_seconds())
+    inverted+=dt(created)<dt(fetch)
+    if dt(created)<dt(fetch):
+        relink_gaps.append((dt(fetch)-dt(created)).total_seconds())
+assert min(gaps)>0
+print(json.dumps(dict(distinct_match_price_history_links=len(links),unique_history_ids=len(versions),receipts=len(receipts),source_groups=source_group_count,nonempty_source_fields=source_clock_fields,fetch_to_pricing_min_seconds=min(gaps),created_before_fetch_links=inverted, max_fetch_after_created_seconds=max(relink_gaps,default=0), time_like_columns=sorted(time_like_columns)),indent=2))
```
