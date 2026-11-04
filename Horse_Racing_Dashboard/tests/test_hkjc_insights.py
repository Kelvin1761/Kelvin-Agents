"""HKJC 即場形勢 tables: placings only, parsed from the saved full-day results."""
import json
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from services.hkjc_insights import build_insights, run_style, draw_bucket


def runner(pos, jockey, trainer, draw, running):
    return {'pos': pos, 'horse_name': f'馬{draw}(A{draw:03d})', 'jockey': jockey, 'trainer': trainer,
            'draw': str(draw), 'running_positions': running}


def meeting(root, day, venue, races):
    folder = root / 'hkjc results 2026 27' / day
    folder.mkdir(parents=True)
    payload = {str(n): {'racedate': day, 'race_no': n, 'venue': venue, 'results': rows,
                        'sectional_times': [['第 1 場'], ['第四班 - 1200米 - (60-40)', '場地狀況 :', '好地'],
                                            ['讓賽', '賽道 :', '草地 - "C+3" 賽道']]}
               for n, rows in enumerate(races, 1)}
    (folder / 'full_day_results.json').write_text(json.dumps(payload, ensure_ascii=False))


def test_race_day_standings_rank_by_placings_and_ignore_withdrawn(tmp_path):
    meeting(tmp_path, '2026-10-25', '沙田', [[runner('1', '舊', 'T9', 1, '1 1 1')]])
    meeting(tmp_path, '2026-10-28', '跑馬地', [
        [runner('1', '甲', 'T1', 1, '1 1 1'), runner('2', '乙', 'T2', 5, '4 3 2'),
         runner('3', '丙', 'T1', 10, '9 8 3'), runner('WV', '丁', 'T2', 2, '')],
        [runner('1', '乙', 'T2', 9, '8 6 1'), runner('2', '甲', 'T1', 2, '2 2 2'), runner('PU', '丙', 'T1', 3, '3 9')],
    ])
    data = build_insights(tmp_path, today=date(2026, 10, 28))
    day = data['meetings'][0]
    assert data['latest_is_today'] and day['day'] == '2026-10-28' and day['venue'] == 'HV'
    assert [m['day'] for m in data['meetings']] == ['2026-10-28', '2026-10-25']
    # Only that day counts: 舊's win on 10-25 is not in 10-28's table.
    assert all(r['name'] != '舊' for r in day['jockeys'])
    # 甲 and 乙 both 1 冠 1 亞 from 2 starts; 丙 only a 季, so last; 丁 withdrew.
    assert sorted(r['name'] for r in day['jockeys'][:2]) == ['乙', '甲'] and day['jockeys'][2]['name'] == '丙'
    assert day['jockeys'][0]['w'] == [1, 1, 0, 0] and day['jockeys'][2]['starts'] == 2
    assert all(r['name'] != '丁' for r in day['jockeys'])
    assert next(r for r in day['combos'] if r['name'] == ['甲', 'T1'])['w'][:2] == [1, 1]
    assert day['bias']['draw']['inner']['w'][0] == 1 and day['bias']['draw']['outer']['w'][0] == 1
    assert day['bias']['style']['front']['w'][0] == 1 and day['bias']['style']['back']['w'][0] == 1
    assert [r['race'] for r in day['races']] == [1, 2] and day['races'][0]['distance'] == 1200 and day['races'][0]['rail'] == 'C+3'
    assert 'win_odds' not in json.dumps(data) and 'profit' not in json.dumps(data)


def test_style_and_draw_buckets():
    assert run_style(2, 12) == 'front' and run_style(9, 12) == 'back' and run_style(6, 12) == 'middle'
    assert run_style(None, 12) is None
    assert draw_bucket(4) == 'inner' and draw_bucket(5) == 'middle' and draw_bucket(9) == 'outer' and draw_bucket(None) is None


def test_missing_database_is_unavailable(tmp_path):
    assert build_insights(tmp_path)['status'] == 'unavailable'
