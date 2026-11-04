# EXP-20261104-18 Tennis 已存 props 發球點數原文覆蓋

2026-11-04。固定 [EXP-17](EXP-20261104-17-tennis-recorded-prop-history-clocks.md) 全 27,411 筆 props，同一份唯讀 SQLite。以保存嘅 history ID 精確連接 [EXP-14](EXP-20261104-14-tennis-cross-provider-point-overlap.md) source-groups，manifest `e6dbf1f4a0a63ef007c58f5431488d58a555a7790412046582e6fbb7cb969a61`。要有兩側完整組、無 owner hold，同時兩側符合發球總分正數、一發入唔多於總分、贏一發／二發唔多於各自分母。發球局數唔納入點數檢查。

| 原文狀態 | prop 引用 | 不重複 history ID |
|---|---:|---:|
| 有合格式雙側點數 tuple | 37,305 | 1,664 |
| 組別留置 | 209 | 23 |
| 組別不完整 | 37 | 1 |
| 未入已核對來源組 | 3,744 | 162 |
| 合計 | 41,295 | 1,850 |

未入組嘅 162 個 ID 喺現存表分屬 TML 96、Sackmann 66，值得查兩個 provider 原始 receipt 點解未對上。1,025 筆有履歷引用嘅 props 中，860 筆／44 場至少有一筆雙側各自對到點數嘅 profile，當中 33 場有 `is_point_in_time=1` 嘅對應 prop。96 筆／9 場至少有一個雙側 profile 所有已引用 ID 都對到點數，9 場都有對應 PIT 旗標。兩側係目標 fixture 嘅兩位球員嘅歷史 profile。

9 場係可逐筆驗證嘅工作清單。PIT 旗標、入庫時鐘同 tuple 均未提供逐場完場時間，也未重現完整原 profile 數值。保留 79 場全分母，唔以 9 場篩選結果做模型比較。今輪無定價重跑，新增合資格樣本 0。

## 重現

將以下程式以統一研究外置根目錄作唯一參數執行，只會輸出聚合數字。

```python
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

root = Path(sys.argv[1])
db = root / 'ranking-date-contract/source.sqlite'
groups = root / 'kernel-f02-rules-20261101/point-input-crossprovider-v3-20261104/source-groups.jsonl'
conn = sqlite3.connect(db.as_uri() + '?mode=ro&immutable=1', uri=True)
conn.execute('PRAGMA query_only=ON')
profiles = []
for match, pit, blob in conn.execute('SELECT match_id,is_point_in_time,pricing_evidence_json FROM prop_tracker WHERE pricing_evidence_json IS NOT NULL'):
    sides = json.loads(blob).get('profiles', {}).get('serve_return', {})
    sides = [set(side.get('history_ids', [])) for side in sides.values()]
    if any(sides):
        profiles.append((match,pit,sides))
wanted = set().union(*(side for _,_,sides in profiles for side in sides))
states = {}
for row in map(json.loads, groups.open()):
    ids = set(row.get('history_ids', [])) & wanted
    if not ids:
        continue
    if not row['complete']:
        label = 'incomplete_group'
    elif row['held']:
        label = 'held_group'
    elif len(row.get('points', [])) != 2 or any(len(side) != 5 or any(not isinstance(v, int) for v in side[:4]) for side in row['points']):
        label = 'missing_points'
    elif any(not (0 < t and 0 <= w1 <= a <= t and 0 <= w2 <= t-a) for t,a,w1,w2,_ in row['points']):
        label = 'invalid_points'
    else:
        label = 'source_tuple'
    for i in ids:
        assert i not in states
        states[i] = label
counts=Counter()
match_both=set()
match_all=set()
pit_match_all=set()
pit_match_both=set()
for match,pit,sides in profiles:
    coverage = []
    for side in sides:
        c = Counter(states.get(i,'outside_audited_source_groups') for i in side)
        counts.update(c)
        coverage.append(c['source_tuple'])
    if len(sides)==2 and min(coverage)>0:
        counts['props_both_sides_at_least_one_tuple']+=1
        match_both.add(match)
        if pit==1:
            pit_match_both.add(match)
    if len(sides)==2 and min(coverage)>0 and coverage==list(map(len,sides)):
        counts['props_all_ids_both_sides_have_tuple']+=1
        match_all.add(match)
        if pit==1:
            pit_match_all.add(match)
assert sum(counts[k] for k in set(states.values()) | {'outside_audited_source_groups'})==41295
outside = Counter()
for history_id in wanted - states.keys():
    provider, = conn.execute('SELECT source_provider FROM player_match_history WHERE id=?', (history_id,)).fetchone()
    outside[provider] += 1
print(json.dumps(dict(counts=counts,unique_history_ids=len(wanted),unique_states=Counter(states.get(i,'outside_audited_source_groups') for i in wanted),matches_both=len(match_both),pit_matches_both=len(pit_match_both),matches_all=len(match_all), pit_matches_all=len(pit_match_all), outside_by_provider=outside, qualified=0),indent=2))
```
