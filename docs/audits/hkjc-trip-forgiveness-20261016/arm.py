"""Fixed, dated prior-trip forgiveness; research patch only."""
import copy
import datetime as dt
import os
import re


def eligible(part, target, arm, engine):
    if not re.search(r'消耗=(?:極高|高)消耗(?:,|，|$)', part):
        return False
    wide = re.search(r'XW=\((\d+W(?:\d+W)*)\)', part)
    if not wide or max(map(int, re.findall(r'(\d+)W', wide.group(1)))) < 3:
        return False
    date_match = re.search(r'第\d+仗\((\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})', part)
    try:
        text = date_match.group(1) if date_match else ''
        day = dt.datetime.strptime(text, '%d/%m/%Y' if '/' in text else '%Y-%m-%d').date()
        cutoff = dt.date.fromisoformat(str(target))
    except ValueError:
        return False
    if day >= cutoff:
        return False
    finish = re.search(r'名次=(\d+)(?:,|，|$)', part)
    if not finish:
        return False
    rank = int(finish.group(1))
    if rank == 1:
        return True
    if arm == 'winner' or rank not in (2, 3):
        return False
    margin = re.search(r'距離=([^,，|]+)', part)
    value = engine._margin_to_float(margin.group(1)) if margin else None
    return value is not None and 0 <= value <= 3


def transformed(engine, arm):
    text = engine._clean(engine._value('position_window') or '')
    if not engine._is_sha_tin_context() or engine._is_debut():
        return text, 0
    parts = text.split('|')
    changed = 0
    for i, part in enumerate(parts[:3]):
        if arm == 'neutral_trip':
            updated = re.sub(r'消耗=(?:極高消耗|高消耗|中等消耗|中低消耗|低消耗)', '消耗=中等消耗', part)
        elif eligible(part, engine.race_context.get('race_date'), arm, engine):
            updated = re.sub(r'消耗=(?:極高|高)消耗', '消耗=中等消耗', part)
        else:
            updated = part
        changed += updated != part
        parts[i] = updated
    return '|'.join(parts), changed


def score_trip(engine, arm, original):
    if arm == 'neutral_trip' and engine._is_sha_tin_context() and not engine._is_debut():
        return 60.0, '研究：沙田消耗分設中性60'
    text, count = transformed(engine, arm)
    if not count:
        return original(engine)
    horse = copy.deepcopy(engine.horse_data)
    horse.setdefault('_data', {})['position_window'] = text
    if 'position_window' in horse:
        horse['position_window'] = text
    alternate = type(engine)(horse, engine.race_context)
    return original(alternate)


def apply():
    from hkjc_racing_engine.engine_core import RacingEngine
    original = RacingEngine._trip_consumption_score
    arm = os.environ['WC_TRIP_STUDY_ARM']
    RacingEngine._trip_consumption_score = lambda self: score_trip(self, arm, original)
