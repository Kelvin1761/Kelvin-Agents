#!/usr/bin/env python3
"""EXP-20260904-08 —— 評估語料上限同源材料盤點（唯讀）。

為咩今日所有候選都判唔到：193 場之下 `good` 一個標準誤 = 3.11pp = 6 場，
而所有候選嘅差距只有 1.0-1.6pp（2-3 場）。個閘睇唔到，唔係否決。
"""
import math
import re
import sys
from pathlib import Path
sys.path.insert(0, '/Users/imac/Antigravity-repo/.agents/skills/shared_racing/scripts')
import corpus_paths as cp

N = 193
print('193 場之下嘅標準誤：')
for metric, p in (('gold', 0.0674), ('good', 0.2487), ('champion', 0.2591)):
    se = math.sqrt(p * (1 - p) / N)
    print('  %-9s baseline %5.2f%%   1 SE = %.2fpp   候選差距 1.3pp = %.2f SE'
          % (metric, 100 * p, 100 * se, 0.013 / se))
print('  1 場 = %.2fpp\n' % (100 / N))

root = Path('/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing')
db = root / 'HKJC_Race_Results_Database'
res = set()
for pat in ('full_day_results.json', '*全日賽果.json'):
    for f in db.rglob(pat):
        m = re.search(r'20\d{2}-\d{2}-\d{2}', str(f))
        if m:
            res.add(m.group(0))
scored = {d.name[:10] for d in cp.meeting_dirs(root) if list(d.glob('Race_*_Logic.json'))}
folders = {}
for d in root.iterdir():
    if d.is_dir() and re.match(r'20\d{2}-\d{2}-\d{2}', d.name):
        folders.setdefault(d.name[:10], []).append(d)

buckets = {'已有 Facts': 0, '有排位表+賽績': 0, '只有一樣': 0, '完全冇源材料': 0}
for day in sorted(res - scored):
    ds = folders.get(day, [])
    card = sum(len(list(x.glob('*排位表.md'))) for x in ds)
    form = sum(len(list(x.glob('*賽績.md'))) for x in ds)
    facts = sum(len(list(x.glob('*Facts.md'))) for x in ds)
    if facts:
        buckets['已有 Facts'] += 1
    elif card and form:
        buckets['有排位表+賽績'] += 1
    elif card or form:
        buckets['只有一樣'] += 1
    else:
        buckets['完全冇源材料'] += 1

print('有賽果嘅賽日        : %d' % len(res))
print('有評分 (Logic) 嘅賽日 : %d   ← 評估語料只用到 %.0f%%' % (len(scored), 100 * len(scored) / len(res)))
print('有賽果但冇評分       : %d\n' % len(res - scored))
for k, v in buckets.items():
    print('  %-16s %d' % (k, v))
print('\n本地補得返: %d 個賽日（約 +%d 場）；其餘要重新抽取賽前資料。'
      % (buckets['已有 Facts'] + buckets['有排位表+賽績'],
         10 * (buckets['已有 Facts'] + buckets['有排位表+賽績'])))
