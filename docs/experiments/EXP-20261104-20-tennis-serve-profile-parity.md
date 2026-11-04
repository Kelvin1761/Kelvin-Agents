# EXP-20261104-20 Tennis 原發球 profile 重播

2026-11-04。固定使用 [EXP-18](EXP-20261104-18-tennis-prop-point-source-coverage.md) 已記錄嘅 96 筆雙方所有引用對到點數嘅 prop rows，共 9 場，沿用同一份唯讀 SQLite 同 source-groups。以保存嘅 history ID 同原順序重算聚合，用現有清洗器、欄位清單及平均函數。逐欄容差 1e-9，缺值要完全一致。

18 份獨立 profile、183 個 profile／履歷引用全部通過。包括發球及接發聚合、破發點比率同對手 Elo 平均值。96 筆兩側全部對上。今輪重算固定輸入清單，未證明重跑原選樣器會選相同窗口。

按 F05 曝光定義，另用同一清單算「總贏分 ÷ 總點數」，同原每場等權平均比較。以下只係輸入差異，百分點。

| 特徵 | 最小差 | 最大差 | 平均絕對差 |
|---|---:|---:|---:|
| 一發贏分率 | −3.324 | +2.091 | 0.783 |
| 二發贏分率 | −3.112 | +4.550 | 1.060 |

F05 原分母及時間切分維持。呢 9 場係可追溯性工作清單，未有逐場完場證據，未重跑原市場定價、未用結果調參或比較準確度，新增合資格樣本 0。

## 重現

從 repo 根以 `PYTHONPATH=tennis-wong-choi/src PYTHONDONTWRITEBYTECODE=1 python3` 執行以下程式，傳統一研究外置根目錄為唯一參數。只輸出聚合。

```python
import json
import math
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from tennis_wc.features import serve_return as sr
from tennis_wc.features.history_values import clean_history_row

root = Path(sys.argv[1])
db = root / 'ranking-date-contract/source.sqlite'
groups = root / 'kernel-f02-rules-20261101/point-input-crossprovider-v3-20261104/source-groups.jsonl'
conn = sqlite3.connect(db.as_uri() + '?mode=ro&immutable=1', uri=True)
conn.row_factory = sqlite3.Row
conn.execute('PRAGMA query_only=ON')
points_by_id = {}
for row in map(json.loads, groups.open()):
    if row['held'] or not row['complete']:
        continue
    sides = row['points']
    if len(sides) == 2 and all(len(side) == 5 and all(isinstance(x, int) for x in side[:4]) and
                              0 < side[0] and 0 <= side[2] <= side[1] <= side[0] and
                              0 <= side[3] <= side[0]-side[1] for side in sides):
        for i in row['history_ids']:
            points_by_id[i] = sides

def same(a, b):
    if a is None or b is None:
        return a is b
    return math.isclose(a, b, abs_tol=1e-9, rel_tol=0)

counts = Counter()
mismatches = Counter()
match_set = set()
match_pair_pass = set()
unique_profiles = {}
shifts = {1: [], 2: []}
for match, blob in conn.execute('SELECT match_id,pricing_evidence_json FROM prop_tracker WHERE pricing_evidence_json IS NOT NULL'):
    sides = list(json.loads(blob).get('profiles', {}).get('serve_return', {}).values())
    if len(sides) != 2 or not all(p['history_ids'] and set(p['history_ids']) <= points_by_id.keys() for p in sides):
        continue
    counts['props'] += 1
    match_set.add(match)
    passes = []
    for profile in sides:
        key = json.dumps(profile, sort_keys=True)
        if key in unique_profiles:
            passes.append(unique_profiles[key])
            continue
        refs = profile['history_ids']
        rows = [clean_history_row(conn.execute('SELECT * FROM player_match_history WHERE id=?', (ref,)).fetchone()) for ref in refs]
        counts['distinct_saved_profiles'] += 1
        counts['distinct_profile_history_refs'] += len(rows)
        assert len(rows) == profile['matches']
        assert all(row['player_id'] == profile['player_id'] for row in rows)
        results = {k: sr._mean(row[k] for row in rows) for k in (*sr._SERVE_COLUMNS, *sr._RETURN_COLUMNS, 'opponent_elo')}
        for dst, num, denom in (
            ('break_point_save_rate','break_points_saved','break_points_faced'),
            ('break_point_conversion_rate','break_points_converted','break_points_chances'),
        ):
            a,b=results[num],results[denom]
            results[dst]=a/b if b and a is not None and b>0 else None
        saved = {**profile['serve'], **profile['returning'], 'opponent_elo': profile['opponent_elo_mean']}
        assert saved.keys() == results.keys()
        exposures = [points_by_id[row['id']][0 if row['won'] else 1] for row in rows]
        first_den = sum(v[1] for v in exposures)
        second_den = sum(v[0] - v[1] for v in exposures)
        shifts[1].append(sum(v[2] for v in exposures) / first_den - saved['first_serve_points_won_pct'])
        shifts[2].append(sum(v[3] for v in exposures) / second_den - saved['second_serve_points_won_pct'])
        different = {k for k in results if not same(results[k], saved[k])}
        mismatches.update(different)
        parity = not different
        counts['profile_full_parity'] += parity
        counts['profile_parity_excluding_derived_elo'] += not (different - {'opponent_elo'})
        unique_profiles[key] = parity
        passes.append(parity)
    if all(passes):
        counts['props_both_full_parity'] += 1
        match_pair_pass.add(match)
assert counts['props'] == 96 and len(match_set) == 9
print(json.dumps(dict(exposure_shift_pp={k: {'min': min(v)*100, 'max': max(v)*100, 'mean_abs': sum(map(abs,v))*100/len(v)} for k,v in shifts.items()}, counts=counts, mismatches=mismatches, matches=len(match_set), matches_pair_parity=len(match_pair_pass)),indent=2))
```
