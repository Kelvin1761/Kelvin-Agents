"""Cross-check bounded replay against direct production calls; no archive writes."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path

os.environ['WC_DISABLE_HKJC_PROFILE_ENRICH'] = '1'
os.environ['WC_DISABLE_POST_SUCCESS_DEPLOY'] = '1'
import study
import pit_backtest
from hkjc_racing_engine.engine_core import DrawScorer
from wongchoi_paths import HK_RACING


def main():
    root = Path('/private/tmp/hkjc-draw-20261016-study')
    bases = study.read(root/'aa.jsonl')
    evs = {(r['meeting'], r['race']): r for r in study.read('/private/tmp/hkjc-draw-20261016-evidence.jsonl')}
    history = study.load_history()
    selected = []
    for test in (lambda r: r['venue'] == '沙田' and r['distance'] == 1000,
                 lambda r: r['venue'] == '沙田' and not r['awt'] and r['distance'] > 1000,
                 lambda r: r['venue'] == '跑馬地', lambda r: r['awt'],
                 lambda r: not r['venue'], lambda r: r['has_debut'] and bool(r['venue'])):
        match = next(r for r in bases if test(r))
        if match not in selected:
            selected.append(match)
    original_align = study.orch._align_runner_headers
    original_draw = DrawScorer.compute
    current = {'arm': 'percentile'}

    def align(path, ctx, horses):
        result = original_align(path, ctx, horses)
        ctx['_study_declared_draws'] = [study.integer(h.get('barrier') or h.get('draw')) for h in horses.values()]
        return result

    def draw(self):
        old, note = original_draw(self)
        proxy = copy.deepcopy(self.horse_data)
        proxy['python_auto'] = {'feature_scores': {'draw_score': old}}
        prior = history[history.Date.astype(str) < str(self.race_context['race_date'])]
        new, _, _ = study.draw_prediction(current['arm'], proxy, self.race_context,
                                          self.race_context['_study_declared_draws'], prior)
        return new, note

    study.orch._align_runner_headers = align
    DrawScorer.compute = draw
    study.orch._atomic_write_json = lambda *a, **k: None
    study.orch.write_prepared_race_outputs = lambda *a, **k: (Path('replay.md'), Path('replay.csv'))
    study.orch.HKJCAutoOrchestrator._emit_event = lambda *a, **k: None
    all_rows = pit_backtest.load_all_rows()
    checks = []
    for base in selected:
        pit_backtest.inject_as_of(all_rows, base['date'])
        md = Path(HK_RACING)/base['meeting']
        ev = evs[(base['meeting'], base['race'])]
        for arm in study.ARMS:
            current['arm'] = arm
            with contextlib.redirect_stdout(io.StringIO()):
                logic = study.orch.HKJCAutoOrchestrator(md).score_race(md/f'Race_{base["race"]}_Logic.json')
            expected = study.prepare(ev)
            draws = [study.integer(h.get('barrier') or h.get('draw')) for h in expected.values()]
            prior = history[history.Date.astype(str) < base['date']]
            for horse in expected.values():
                new, eligible, _ = study.draw_prediction(arm, horse, ev['context'], draws, prior)
                auto = horse['python_auto']
                if eligible and new != auto['feature_scores']['draw_score']:
                    f = dict(auto['feature_scores'], draw_score=new)
                    auto['matrix_scores']['race_shape'] = round(study.RacingEngine(horse, ev['context'])._race_shape_context_score(f)[0], 2)
                    auto['feature_scores']['draw_score'] = round(new, 2)
            study.score(expected)
            actual = logic['horses']
            delta = max(abs(expected[n]['python_auto']['ability_score_raw'] - actual[n]['python_auto']['ability_score_raw']) for n in expected)
            if delta > 1e-6 or study.ranked(expected) != study.ranked(actual):
                (root/'parity_mismatch.json').write_text(json.dumps({'base': base, 'arm': arm,
                    'context': logic['race_analysis'], 'expected': expected, 'actual': actual}, ensure_ascii=False))
                raise ValueError(f'production mismatch {base["meeting"]} R{base["race"]} {arm}: {delta}')
            checks.append({'meeting': base['meeting'], 'race': base['race'], 'arm': arm, 'max_raw_delta': delta})
        print(f'production parity: {base["meeting"]} R{base["race"]}', flush=True)
    result = {'exact': True, 'checks': checks}
    (root/'production_parity.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
