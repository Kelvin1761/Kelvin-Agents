"""Closing-price comparison (CLV) for frozen 大細盤精選 picks — display only, never a bet or a score.

The one live definition of featured-pick CLV (AGENTS.md: one standard per concept). The research
script docs/experiments/patches/nba_featured_clv/clv.py (EXP-20261124-71) is the frozen record it was
checked against: our side's proportional de-vigged probability at the last pre-tip quote of the same
O/U line captured after publication, minus `p_fair` at the pick; if that line is gone, where the most
balanced line closed."""
import json
from datetime import datetime, timezone
from pathlib import Path


def _time(value):
    dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def day_quotes(path):
    latest = {}
    try:
        with Path(path).open(encoding='utf-8') as stream:
            for line in stream:
                if '"ou_two_way"' not in line:
                    continue
                try:
                    row = json.loads(line)
                    if row.get('post_tip') or row.get('tip_unknown') or not row.get('tip_off'):
                        continue
                    captured = _time(row['captured_at'])
                    if captured >= _time(row['tip_off']):
                        continue
                    side = row['side']
                    if side not in ('over', 'under'):
                        continue
                    over, under = (row['price'], row['complement_price']) if side == 'over' else (row['complement_price'], row['price'])
                    over, under = float(over), float(under)
                    if over <= 1 or under <= 1:
                        continue
                    value = row.get('ou_line') if row.get('ou_line') is not None else row.get('line')
                    key = (row['game_tag'], row['player'], row['market'], float(value))
                    if key not in latest or captured > latest[key][0]:
                        latest[key] = (captured, over, under)
                except (ValueError, TypeError, KeyError, OverflowError):
                    continue
    except OSError:
        pass
    return {json.dumps(key): [value[0].isoformat(), value[1], value[2]] for key, value in latest.items()}


def quotes(ledger_root, days, cache_dir):
    cache_path = Path(cache_dir) / 'nba-featured-clv-cache.json'
    try:
        cache = json.loads(cache_path.read_text(encoding='utf-8'))
        if not isinstance(cache, dict):
            cache = {}
    except (OSError, ValueError):
        cache = {}
    fresh = dict(cache)
    result = {}
    for day in set(days):
        path = Path(ledger_root) / (day + '.jsonl')
        try:
            stat = path.stat()
            signature = [stat.st_size, stat.st_mtime_ns]
        except OSError:
            signature = None
        entry = cache.get(day)
        if not isinstance(entry, dict) or entry.get('signature') != signature or 'quotes' not in entry:
            entry = {'signature': signature, 'quotes': day_quotes(path)}
        fresh[day] = entry
        result[day] = entry['quotes']
    if fresh != cache:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(fresh), encoding='utf-8')
        except OSError:
            pass
    return result


def clv_for(pick, day_q, now_utc):
    if _time(pick['start_time_utc']) > _time(now_utc):
        return {'status': 'pending'}
    line = float(pick['ou_line'])
    # Only quotes captured after the pick was published can be its close: when a line is pulled
    # after 21:00, its last pre-tip quote is the 21:00 one itself, which would read as a 0pp CLV.
    after = _time(pick['published_at']) if pick.get('published_at') else None
    matches = [json.loads(k) + v for k, v in day_q.items()
               if json.loads(k)[:3] == [pick['game_tag'], pick['player'], pick['market']]
               and (after is None or _time(v[0]) > after)]
    same = next((q for q in matches if q[3] == line), None)
    if same:
        over, under = same[5:7]
        fair_over = (1 / over) / (1 / over + 1 / under)
        fair_close = fair_over if pick['side'] == 'over' else 1 - fair_over
        fair_pick = float(pick['p_fair'])
        return {'status': 'same_line', 'close_over': over, 'close_under': under,
                'fair_close': fair_close, 'fair_pick': fair_pick, 'pp': 100 * (fair_close - fair_pick)}
    if matches:
        close = min(matches, key=lambda q: (abs(1 / q[5] - 1 / q[6]), q[3]))
        move = close[3] - line
        return {'status': 'line_moved', 'close_line': close[3], 'line_move': move,
                'our_way': move > 0 if pick['side'] == 'under' else move < 0}
    return {'status': 'unavailable'}


def annotate(records, ledger_root, cache_dir, now_utc=None):
    try:
        by_day = quotes(ledger_root, [r['day'] for r in records if r.get('day')], cache_dir)
        now = now_utc or datetime.now(timezone.utc)
        for record in records:
            try:
                pick = {**record, **record['legs'][0]}
                record['clv'] = clv_for(pick, by_day.get(record['day'], {}), now)
            except Exception:
                continue
    except Exception:
        pass


def summary(records):
    items = [r.get('clv') or {} for r in records]
    same = [c['pp'] for c in items if c.get('status') == 'same_line']
    moved = [c for c in items if c.get('status') == 'line_moved']
    return {'n': len(same), 'mean_pp': sum(same) / len(same) if same else None,
            'our_way': sum(bool(c['our_way']) for c in moved),
            'against': sum(not c['our_way'] for c in moved),
            'unavailable': sum(c.get('status') == 'unavailable' for c in items),
            'pending': sum(c.get('status') == 'pending' for c in items)}
