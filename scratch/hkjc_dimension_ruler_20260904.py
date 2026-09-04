#!/usr/bin/env python3
"""EXP-20260904-03 —— 維度顯示尺嘅量度同核實（唯讀）。

印出：七個維度嘅原始分佈、band 可達性、嘉應高昇三個數嘅百分位、
校正後嘅 band 分佈，同「排序有冇變」嘅逐場核實。
"""
import json, sys, statistics as st
from collections import Counter
from pathlib import Path
R = Path('/Users/imac/Antigravity-repo')
sys.path.insert(0, str(R / '.agents/skills/shared_racing/scripts'))
sys.path.insert(0, str(R / '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'))
import corpus_paths as cp
from hkjc_racing_engine.engine_core import RacingEngine
from hkjc_racing_engine.scoring import MATRIX_WEIGHTS, score_band, to_dimension_display

ROOT = '/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing'
LBL = {'stability': '狀態與穩定性', 'trainer_signal': '騎練訊號', 'sectional': '段速表現',
       'race_shape': '檔位與走位', 'horse_health': '馬匹健康', 'form_line': '賽績線',
       'class_advantage': '級數優勢'}
ORDER = ['✅✅', '✅', '➖', '❌', '❌❌']

raw = {d: [] for d in MATRIX_WEIGHTS}
disp = {d: [] for d in MATRIX_WEIGHTS}
bands_raw = {d: Counter() for d in MATRIX_WEIGHTS}
bands_new = {d: Counter() for d in MATRIX_WEIGHTS}
n = mismatches = 0
for f in cp.logic_files(ROOT):
    doc = json.load(open(f))
    ctx = doc.get('race_analysis') or {}
    field = []
    for num, h in (doc.get('horses') or {}).items():
        if not isinstance(h, dict):
            continue
        try:
            a = RacingEngine(h, ctx).analyze_horse()
        except Exception:
            continue
        n += 1
        field.append((num, a['ability_score'], a['ability_score_raw']))
        for d, v in a['matrix_scores'].items():
            raw[d].append(float(v)); bands_raw[d][score_band(float(v))] += 1
        for d, v in a['matrix_scores_display'].items():
            disp[d].append(float(v)); bands_new[d][score_band(float(v))] += 1
    key = lambda t: (int(t[0]) if t[0].isdigit() else 999)
    if field and ([x[0] for x in sorted(field, key=lambda t: (-t[1], key(t)))]
                  != [x[0] for x in sorted(field, key=lambda t: (-t[2], key(t)))]):
        mismatches += 1

print('runners %d   排序唔同嘅場次: %d  ← 一定要 0\n' % (n, mismatches))
print('%-14s %6s %6s %6s %7s  | %s' % ('維度', 'min', '中位', 'max', 'SD', '原始尺出唔到嘅 band'))
for d in sorted(MATRIX_WEIGHTS, key=lambda x: -MATRIX_WEIGHTS[x]):
    v = sorted(raw[d])
    never = ' '.join(b for b in ORDER if not bands_raw[d][b]) or '—'
    print('%-14s %6.1f %6.1f %6.1f %7.2f  | %s'
          % (LBL[d], v[0], st.median(v), v[-1], st.pstdev(v), never))

print('\n嘉應高昇（2026-09-06 R3）:')
for d, x in (('class_advantage', 60.0), ('horse_health', 61.33), ('race_shape', 69.42),
             ('trainer_signal', 76.74), ('form_line', 94.0)):
    v = sorted(raw[d]); pct = 100 * sum(1 for y in v if y < x) / len(v)
    y = to_dimension_display(d, x)
    print('  %-14s 原始 %5.1f（第 %2.0f 百分位）%s → 顯示 %5.1f %s'
          % (LBL[d], x, pct, score_band(x), y, score_band(y)))

print('\n校正後 band 分佈:')
print('%-14s %s' % ('維度', ''.join('%8s' % b for b in ORDER)))
for d in sorted(MATRIX_WEIGHTS, key=lambda x: -MATRIX_WEIGHTS[x]):
    print('%-14s %s' % (LBL[d], ''.join('%7.1f%%' % (100 * bands_new[d][b] / n) for b in ORDER)))
