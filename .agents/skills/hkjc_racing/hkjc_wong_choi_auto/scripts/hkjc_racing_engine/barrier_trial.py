"""HKJC 試閘結果：唯一一份 parser 同本機表讀取（唔入分）。

Kelvin 2026-11-24：試閘輸距版入分（EXP-20261124-16 TR1）唔上 ——「輸距冇乜嘢好睇，初出馬試閘最多睇段速同時間」。
所以呢度只保留數據層：`extract_barrier_trials.py` 每日更新 `HK_Racing/HKJC_Sections/barrier_trials.json`，
供之後試閘時間／步速研究用。入分版 code 喺分支 `codex-hkjc-barrier-trial-20261124`（未發佈）。
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path


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
            groups.append({'group': cells[0], 'rows': []})
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
