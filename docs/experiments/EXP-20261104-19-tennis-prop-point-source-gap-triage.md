# EXP-20261104-19 Tennis props 未對上點數原因

2026-11-04。以 [EXP-18](EXP-20261104-18-tennis-prop-point-source-coverage.md) 同一份 SQLite 同來源組為準。將 162 個未入組 ID 全部對到封存 point inventory，manifest `cd3179fd349413d4ee723c5320ff4eb78834f5b4488d1f615a4e613f7f32f92d`。全部已曾審核並留置，涉及 21 個 receipt IDs。原因按互斥組列出。

| 留置組 | 履歷 ID | Prop 引用 |
|---|---:|---:|
| Provider canonical pair 衝突 | 63 | 1,709 |
| 不完整或未支援比分 | 57 | 1,301 |
| 同時有身份衝突同比分問題 | 1 | 37 |
| 日期或賽事版本衝突 | 1 | 32 |
| 原文不可用或無效，無唯一 raw match key | 40 | 665 |
| 合計 | 162 | 3,744 |

58 個比分相關 ID 對到 56 個獨立 receipt／source match key。其中 54 組原比分有退賽標記，餘下 2 組係未支援比分形狀。補原文嘅 40 個 ID 全部屬 TML。身份衝突保留原 pair 同原留置規則，退賽點數可另開帶退賽標籤嘅研究，目前唔混入完整比賽 exposure。無新增合資格樣本，無改正式資料或原研究分母。

## 重現

把以下附加至 EXP-18 重跑程式，從 repo 根以 `PYTHONPATH=tennis-wong-choi/src PYTHONDONTWRITEBYTECODE=1 python3` 執行。只輸出聚合。

```python
gaps=wanted-states.keys()
inventory={}
for entry in map(json.loads,(groups.parent.parent/'point-input-public-history-v1/rows.jsonl').open()):
    if entry['history_id'] in gaps:
        inventory[entry['history_id']]=entry
counts=Counter()
refs_by_category=Counter()
receipt_ids=set()
for i in gaps:
    h=conn.execute('SELECT source_provider,history_status,raw_response_id FROM player_match_history WHERE id=?',(i,)).fetchone()
    entry=inventory.get(i)
    category=tuple(sorted(entry['issues'])) if entry else ('outside_inventory',h[1])
    counts[(h[0],category)]+=1
    refs_by_category[category]+=sum(i in side for _,_,sides in profiles for side in sides)
    receipt_ids.add(h[2])
assert sum(counts.values())==162
assert sum(refs_by_category.values())==3744
print('receipt_count',len(receipt_ids))
print('provider_and_reason',sorted(counts.items()))
print('references_by_reason',sorted(refs_by_category.items()))
from tennis_wc.database.payload_archive import read_payload
import re
score_ids={i for i,row in inventory.items() if 'partial_or_unsupported_score' in row['issues']}
by_receipt={}
for i in score_ids:
    row=conn.execute('SELECT raw_response_id,source_match_ref,provider_match_id,tour FROM player_match_history WHERE id=?',(i,)).fetchone()
    by_receipt.setdefault(row[0],set()).add((row[3],(row[1] or row[2]).rsplit('-',1)[0]))
score_kinds=Counter()
for rid,keys in by_receipt.items():
    body,=conn.execute('SELECT response_json FROM raw_api_responses WHERE id=?',(rid,)).fetchone()
    data=json.loads(read_payload(conn,'raw_response',rid,body))
    index={f"{tour}-{row.get('tourney_id')}-{row.get('match_num')}": row for tour in {t for t,_ in keys} for row in data if isinstance(row,dict)}
    for _,key in keys:
        row=index[key]
        score=str(row.get('score') or '').upper().strip()
        if re.search(r'\bRET(?:IRED)?\b',score):
            kind='retirement_marker'
        elif re.search(r'\b(?:W/O|WO|DEF|ABD)\b',score):
            kind='other_non_completion_marker'
        elif str(row.get('best_of')) not in ('3','5'):
            kind='unsupported_format'
        else:
            kind='other_score_shape'
        score_kinds[kind]+=1
print('score_gap_ids',len(score_ids),'distinct_source_groups',sum(map(len,by_receipt.values())),'score_kinds',dict(score_kinds))
```
