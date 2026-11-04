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
    # Only the newest meeting is kept: 10-25 is gone, not just a second page.
    assert [m['day'] for m in data['meetings']] == ['2026-10-28']
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


def test_live_capture_feeds_tonight_and_canonical_wins_per_race(tmp_path):
    meeting(tmp_path, '2026-11-04', '跑馬地', [[runner('1', '正式', 'T1', 1, '1 1 1'), runner('2', '乙', 'T2', 5, '4 3 2'), runner('3', '丙', 'T1', 9, '9 8 3')]])
    live = tmp_path / '_live'
    live.mkdir()
    race = lambda n, winner: {'racedate': '2026-11-04', 'race_no': n, 'venue': '跑馬地', 'results': [
        runner('1', winner, 'T1', 2, '2 2 1'), runner('2', '乙', 'T2', 6, '5 4 2'), runner('3', '丙', 'T1', 10, '10 9 3')]}
    (live / '2026-11-04.json').write_text(json.dumps({'1': race(1, '即場版'), '2': race(2, '即場'), }, ensure_ascii=False))
    (live / '2026-11-04.state.json').write_text('{"1": {"captured_at": "x"}}')
    day = build_insights(tmp_path, today=date(2026, 11, 4))['meetings'][0]
    assert [r['race'] for r in day['races']] == [1, 2]
    names = {r['name'] for r in day['jockeys']}
    assert '正式' in names and '即場' in names and '即場版' not in names


def card(root, folder, rows):
    path = root / folder
    path.mkdir(parents=True)
    lines = ['race_number,horse_number,horse_name,jockey,trainer,rank'] + [f'{r},{i},馬{i},{j},{t},1' for i, (r, j, t) in enumerate(rows, 1)]
    (path / 'HKJC_Auto_Scoring.csv').write_text('\n'.join(lines), encoding='utf-8')


def test_analysed_meeting_shows_at_zero_before_any_result(tmp_path):
    results, racing = tmp_path / 'db', tmp_path / 'racing'
    meeting(results, '2026-11-01', '跑馬地', [[runner('1', '舊', 'T9', 1, '1 1 1')]])
    card(racing, '2026-11-04_HappyValley', [(1, '甲', 'T1'), (1, '乙', 'T2'), (2, '甲', 'T2')])
    (racing / '2026-11-05_ShaTin').mkdir()  # facts only, analysis not made yet
    data = build_insights(results, card_root=racing, today=date(2026, 11, 4))
    # The analysed card replaces 11-01's results; 11-05 has facts but no analysis, so it does not.
    assert [m['day'] for m in data['meetings']] == ['2026-11-04'] and data['latest_is_today']
    day = data['meetings'][0]
    assert day['venue'] == 'HV' and day['scheduled'] == 2 and day['races'] == []
    assert [(r['name'], r['w'], r['starts'], r['rides']) for r in day['jockeys']] == [('甲', [0, 0, 0, 0], 0, 2), ('乙', [0, 0, 0, 0], 0, 1)]
    assert {tuple(r['name']) for r in day['combos']} == {('甲', 'T1'), ('乙', 'T2'), ('甲', 'T2')}
    assert day['bias']['draw']['inner']['starts'] == 0


def test_results_replace_the_card_race_by_race(tmp_path):
    results, racing = tmp_path / 'db', tmp_path / 'racing'
    meeting(results, '2026-11-04', '跑馬地', [[runner('1', '甲', 'T1', 1, '1 1 1'), runner('2', '乙', 'T2', 5, '4 3 2')]])
    card(racing, '2026-11-04_HappyValley', [(1, '甲', 'T1'), (1, '乙', 'T2'), (1, '退出', 'T3'), (2, '甲', 'T2'), (2, '丙', 'T3')])
    day = build_insights(results, card_root=racing, today=date(2026, 11, 4))['meetings'][0]
    assert day['scheduled'] == 2 and [r['race'] for r in day['races']] == [1]
    jockeys = {r['name']: r for r in day['jockeys']}
    # 甲 won race 1 and still rides race 2; 丙 only rides race 2; race 1's scratched name drops out.
    assert jockeys['甲']['w'] == [1, 0, 0, 0] and jockeys['甲']['starts'] == 1 and jockeys['甲']['rides'] == 2
    assert jockeys['丙']['starts'] == 0 and '退出' not in jockeys
    assert [r['name'] for r in day['jockeys']] == ['甲', '乙', '丙']
