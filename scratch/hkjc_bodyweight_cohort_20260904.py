#!/usr/bin/env python3
"""EXP-20260904-08 —— 體重變幅 × 休賽長度 對上名率（唯讀）+ bootstrap CI。

結論：長休 >75 日「回來重咗」係**正面**訊號（+7.9pp, CI [+2.1,+13.7]）；
短休冇訊號（CI 跨零）；長休本身嘅罰分係啱嘅（−3.7pp, CI 不跨零）。
"""
import random, sys
from pathlib import Path
R = Path('/Users/imac/Antigravity-repo')
for p in ('.agents/skills/hkjc_racing/hkjc_reflector/scripts', '.agents/scripts',
          '.agents/skills/shared_racing/scripts'):
    sys.path.insert(0, str(R / p))
import pandas as pd
import pit_backtest as pb

d = pb.load_all_rows().copy()
for c in ('HorseWt', 'Rank'):
    d[c] = pd.to_numeric(d[c], errors='coerce')
d = d.dropna(subset=['HorseWt', 'Rank', 'Date', 'Horse']).sort_values(['Horse', 'Date'])
d['prev_wt'] = d.groupby('Horse')['HorseWt'].shift(1)
d['prev_date'] = d.groupby('Horse')['Date'].shift(1)
d = d.dropna(subset=['prev_wt', 'prev_date'])
d['dwt'] = d['HorseWt'] - d['prev_wt']
d['gap'] = (pd.to_datetime(d['Date']) - pd.to_datetime(d['prev_date'])).dt.days
d['placed'] = (d['Rank'] <= 3).astype(int)
print('runner-starts with a previous weight: %d\n' % len(d))

for lo, hi, lab in ((0, 75, '短休 ≤75 日'), (75, 10 ** 6, '長休 >75 日')):
    sub = d[(d['gap'] > lo) & (d['gap'] <= hi)]
    sub = sub.assign(b=pd.cut(sub['dwt'], [-999, -15, -5, 5, 15, 25, 999]))
    t = sub.groupby('b', observed=True).agg(n=('placed', 'size'), place=('placed', 'mean'))
    t['place'] = (100 * t['place']).round(1)
    print('%s  (n=%d)\n%s\n' % (lab, len(sub), t.to_string()))


def ci(a, b, label, n=6000):
    random.seed(11)
    A, B = list(a), list(b)
    diffs = []
    for _ in range(n):
        sa = [A[random.randrange(len(A))] for _ in range(len(A))]
        sb = [B[random.randrange(len(B))] for _ in range(len(B))]
        diffs.append(sum(sa) / len(sa) - sum(sb) / len(sb))
    diffs.sort()
    m = sum(A) / len(A) - sum(B) / len(B)
    lo, hi = diffs[int(.025 * n)], diffs[int(.975 * n)]
    print('%s: %+.1fpp  95%% CI [%+.1f, %+.1f]  (n=%d vs %d)  %s'
          % (label, 100 * m, 100 * lo, 100 * hi, len(A), len(B),
             'CI 不跨零' if lo * hi > 0 else 'CI 跨零'))


L = d[d['gap'] > 75]
S = d[d['gap'] <= 75]
ci(L[L['dwt'] > 5]['placed'], L[L['dwt'] < -5]['placed'], '長休 >75 日：重咗 − 輕咗   ')
ci(S[S['dwt'] > 5]['placed'], S[S['dwt'] < -5]['placed'], '短休 ≤75 日：重咗 − 輕咗   ')
mid = d[(d['gap'] > 20) & (d['gap'] <= 75)]['placed']
ci(d[d['gap'] > 75]['placed'], mid, '長休 >75 日 − 正常 21-75 日')
ci(d[d['gap'] <= 20]['placed'], mid, '急放 ≤20 日 − 正常 21-75 日')
