"""初出馬試閘時間（EXP-20261124-17）。
β=4.36 為 2026/27 walk-forward；MU=0.122 為 2019/20–2025/26 初出馬最後試閘 tf 平均。
研究回放六季初出馬 Δlog-loss −0.00163、dev −0.00055、holdout −0.00051。
ENABLED=False 退回；只用賽日前紀錄。
"""
from __future__ import annotations
import bisect
from collections import defaultdict
import json
import re
import sys
from pathlib import Path
from . import debut_trainer
from .market_history import horse_code

ENABLED = True
BETA = 4.36
MU = 0.122
_CACHE = None


def margin_lengths(text):
    raw = str(text or '').strip()
    if not raw:
        return 0.0
    u = raw.upper().rstrip('L').strip()
    abbr = {'SH': .1, 'S/H': .1, 'N': .05, 'NOSE': .05, 'HD': .2, 'NECK': .3, 'DH': 0.0}
    if u in abbr:
        return abbr[u]
    for word, value in (('短馬頭位', .1), ('SHORT HEAD', .1), ('馬頭位', .2), ('頭位', .2), ('HEAD', .2), ('鼻位', .05), ('NOSE', .05), ('頸位', .3), ('NECK', .3)):
        if word in u:
            return value
    m = re.fullmatch(r'(\d+)(?:[ -](\d+)/(\d+))?|(\d+)/(\d+)', u)
    if not m:
        return None
    try:
        return int(m[4]) / int(m[5]) if m[4] else int(m[1]) + (int(m[2]) / int(m[3]) if m[2] else 0.0)
    except ZeroDivisionError:
        return None


def parse_trial_page(html):
    scripts = Path(__file__).resolve().parents[3] / 'hkjc_race_extractor' / 'scripts'
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from extract_trackwork import TableParser
    parser = TableParser()
    parser.feed(html)
    groups = []
    for row in parser.rows:
        cells = row.get('cells') or []
        if not cells:
            continue
        if re.search(r'第\s*\d+\s*組', cells[0]) and len(cells) <= 2:
            h = re.search(r'第\s*\d+\s*組\s*-\s*(.+?)\s*-\s*(\d+)\s*米', cells[0])
            groups.append({'group': cells[0], 'track': h[1].strip() if h else '', 'dist': int(h[2]) if h else None, 'going': '', 'splits': [], 'rows': []})
            continue
        if groups and not groups[-1]['rows']:
            joined = ' '.join(cells)
            g = re.search(r'場地狀況[:：]\s*(\S+)', joined)
            if g:
                groups[-1]['going'] = g[1]
            split = re.search(r'分段時間[:：]\s*([\d.\s]+)', joined)
            if split:
                groups[-1]['splits'] = [float(v) for v in split[1].split() if re.fullmatch(r'\d+(\.\d+)?', v)]
                continue
        match = re.search(r'\(([A-Z]\d{3})\)', cells[0])
        if groups and match and len(cells) >= 9:
            t = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', cells[7].strip())
            seconds = int(t[1]) * 60 + int(t[2]) + int(t[3]) / 100 if t else None
            groups[-1]['rows'].append({'code': match[1], 'margin': margin_lengths(cells[5]), 'time': seconds})
    return groups


def load_table(path=None):
    if path is None:
        import wongchoi_paths
        path = Path(wongchoi_paths.HK_RACING) / 'HKJC_Sections' / 'barrier_trials.json'
    p = Path(path)
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def last_trial(code, race_date, table):
    past = [row for row in (table or {}).get('trials', {}).get(code, []) if row[0] < race_date]
    return tuple(max(past, key=lambda row: row[0])) if past else None


def trial_figures(table):
    global _CACHE
    if _CACHE is not None and _CACHE[0] is table:
        return _CACHE[1]
    days = defaultdict(list)
    for code, records in (table or {}).get('trials', {}).items():
        for row in records:
            if len(row) >= 6 and row[2] and isinstance(row[3], (int, float)) and row[3] > 0 and isinstance(row[5], (int, float)):
                days[row[0]].append((code, row))
    pools, result = defaultdict(list), defaultdict(list)
    for day in sorted(days):
        for code, row in days[day]:
            _, _, track, dist, going, t = row[:6]
            values = pools[(track, dist, going)]
            if len(values) < 30:
                values = pools[(track, dist)]
            std = values[len(values) // 2] if len(values) >= 30 else None
            tf = (std - min(t, std + 3)) / (dist / 1000) if std is not None else None
            result[code].append((day, tf))
        for _, row in days[day]:
            _, _, track, dist, going, t = row[:6]
            bisect.insort(pools[(track, dist, going)], t)
            bisect.insort(pools[(track, dist)], t)
    _CACHE = (table, dict(result))
    return _CACHE[1]


def last_trial_figure(code, race_date, table):
    # The latest trial remains the latest even when it has no usable time.
    rows = [r for r in (table or {}).get('trials', {}).get(code, []) if r[0] < race_date]
    if not rows:
        return None
    # 同日如果有舊 2 欄紀錄（未升級嘅抓取寫入）同 v2 紀錄，揀 v2。
    row = sorted(rows, key=lambda r: (r[0], len(r) >= 6))[-1]
    figures = trial_figures(table).get(code, [])
    # Same-day trials preserve table insertion order.
    same_day = [tf for day, tf in figures if day == row[0]]
    tf = same_day[-1] if len(row) >= 6 and same_day and row[2] and row[3] and row[5] is not None else None
    return (row[0], tf, row[2] if len(row) >= 6 else None, row[3] if len(row) >= 6 else None)


def adjustments(horses, race_date, table):
    zs, infos = {}, {}
    for key, horse in horses.items():
        info = last_trial_figure(horse_code(horse), race_date, table) if debut_trainer.is_debut(horse) else None
        infos[key] = info
        zs[key] = float(info[1]) - MU if info and info[1] is not None else 0.0
    mean = sum(zs.values()) / len(zs) if zs else 0
    return {key: (BETA * (z - mean), infos[key]) for key, z in zs.items()}


def apply(horses, race_context=None):
    if not ENABLED:
        return 0
    from .scoring import compute_grade, to_display_scale
    race_date = str((race_context or {}).get('race_date') or '')[:10]
    scored = {k: h for k, h in horses.items() if isinstance(h, dict) and isinstance(h.get('python_auto'), dict) and h['python_auto'].get('ability_score_raw') is not None}
    if not scored or not race_date or not any(debut_trainer.is_debut(h) for h in scored.values()):
        return 0
    table = load_table()
    if table is None:
        return 0
    n = 0
    for key, (add, info) in adjustments(scored, race_date, table).items():
        auto = scored[key]['python_auto']
        add = round(add, 4)
        if info:
            auto['trial_time'] = dict(zip(('date', 'tf', 'track', 'dist'), info))
        raw = round(float(auto['ability_score_raw']) + add, 4)
        auto['ability_score_raw'] = raw
        auto['ability_score'] = round(to_display_scale(raw), 2)
        auto['grade'] = compute_grade(auto['ability_score'])
        auto['trial_time_delta'] = add
        for shadow in (auto.get('shadow_profiles') or {}).values():
            try:
                s_raw = round(float(shadow.get('ability_score_raw')) + add, 4)
            except (TypeError, ValueError):
                continue
            s_score = round(to_display_scale(s_raw), 2)
            shadow.update(ability_score_raw=s_raw, ability_score=s_score, grade=compute_grade(s_score), ability_delta=round(s_score - auto['ability_score'], 2))
            shadow.setdefault('sip_flags', []).append({'reason': 'trial_time', 'boost': add, 'boost_scale': 'raw'})
        n += abs(add) > 1e-9
    return n
