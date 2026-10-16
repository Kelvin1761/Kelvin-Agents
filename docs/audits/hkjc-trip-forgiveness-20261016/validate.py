"""Direct production parity and prior-window safety checks."""
import contextlib
import io
import json
import os
from pathlib import Path

os.environ['WC_DISABLE_HKJC_PROFILE_ENRICH'] = '1'
os.environ['WC_DISABLE_POST_SUCCESS_DEPLOY'] = '1'
import arm
import replay as r
import study
import pit_backtest
from wongchoi_paths import HK_RACING


def safety():
    eng = r.RacingEngine({}, {'race_date': '2026-10-07', 'venue': '沙田'})
    pattern = '第1仗(01/10/2026 沙田 1200): XW=(3W4W), 消耗=高消耗, 名次={}, 距離={}'
    tests = [(pattern.format(1, '8'), 'winner', True),
             (pattern.format(2, '3'), 'close_top3', True),
             (pattern.format(3, '3-1/4'), 'close_top3', False),
             (pattern.format(3, '2-3/4'), 'close_top3', True),
             (pattern.format(4, '1/2'), 'close_top3', False),
             (pattern.format(2, 'N/A'), 'close_top3', False),
             (pattern.format(1, '1').replace('01/10/2026', '07/10/2026'), 'winner', False),
             (pattern.format(1, '1').replace('01/10/2026', '08/10/2026'), 'winner', False),
             (pattern.format(1, '1').replace('(3W4W)', '-'), 'winner', False)]
    for text, name, expected in tests:
        assert arm.eligible(text, '2026-10-07', name, eng) == expected
    return len(tests)


def main():
    result = json.loads((study.OUT/'summary.json').read_text())
    aa = r.read(study.OUT/'aa.jsonl')
    original = r.RacingEngine._trip_consumption_score
    r.orch._atomic_write_json = lambda *a, **k: None
    r.orch.write_prepared_race_outputs = lambda *a, **k: (Path('replay.md'), Path('replay.csv'))
    r.orch.HKJCAutoOrchestrator._emit_event = lambda *a, **k: None
    all_rows = pit_backtest.load_all_rows()
    checks = []
    for name in study.ARMS:
        predictions = {(x['meeting'], x['race']): x for x in r.read(study.OUT/(name+'.jsonl'))}
        targets = [tuple(x) for x in result['targets'][name][:5]]
        for test in (lambda b: b['venue'] == '跑馬地', lambda b: not b['venue'], lambda b: b['has_debut']):
            base = next(b for b in aa if test(b))
            target = (base['meeting'], base['race'])
            if target not in targets:
                targets.append(target)
        for meeting, race in targets:
            pit_backtest.inject_as_of(all_rows, meeting[:10])
            r.RacingEngine._trip_consumption_score = lambda self, name=name: arm.score_trip(self, name, original)
            md = Path(HK_RACING)/meeting
            with contextlib.redirect_stdout(io.StringIO()):
                actual = r.orch.HKJCAutoOrchestrator(md).score_race(md/f'Race_{race}_Logic.json')
            expected = predictions[(meeting, race)]
            delta = max(abs(actual['horses'][n]['python_auto']['ability_score_raw']-v) for n, v in expected['raw_scores'].items())
            assert delta < 1e-6, (meeting, race, name, delta)
            assert r.ranked(actual['horses']) == expected['picks']
            checks.append({'arm': name, 'meeting': meeting, 'race': race, 'max_raw_delta': delta})
        print(f'{name}: {len(targets)} production parity races', flush=True)
    r.RacingEngine._trip_consumption_score = original
    output = {'exact': True, 'parser_safety_checks': safety(), 'production_checks': checks}
    (study.OUT/'validation.json').write_text(json.dumps(output, indent=2)+'\n')


if __name__ == '__main__':
    main()
