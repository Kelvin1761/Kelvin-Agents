#!/usr/bin/env python3
"""Season-restricted, horse-level engine replay; no production code is changed."""
import argparse
import json
import sys
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
PATCH = Path(__file__).resolve().parent
REF = ROOT / '.agents/skills/hkjc_racing/hkjc_reflector/scripts'
for p in (ROOT, ROOT / '.agents/skills/shared_racing', REF, PATCH):
    sys.path.insert(0, str(p))
import hkjc_surface_shape_ml as surface
import hkjc_race_shape_v2_ab as metrics
from build_hkjc_ranking_dataset import RacingEngine
from hkjc_racing_engine._leaves import LeafScores

ARMS = ('st_no_trip', 'st_surface_replaces_trip', 'st_draw_only', 'st_draw_surface')
ORIGINAL = LeafScores._race_shape_context_score

@contextmanager
def shape_patch(arm, surface_score, eligible):
    def patched(engine, features):
        result = ORIGINAL(engine, features)
        if not eligible or not engine._is_sha_tin_context() or engine._is_debut():
            return result
        draw = float(features.get('draw_score', 60))
        fit = engine._draw_position_fit_score()[0]
        if arm == 'st_no_trip':
            score = .55 * draw + .25 * fit + .20 * 60
        elif arm == 'st_surface_replaces_trip':
            score = .55 * draw + .25 * fit + .20 * surface_score
        elif arm == 'st_draw_only':
            score = .55 * draw + .45 * 60
        else:
            score = .55 * draw + .45 * surface_score
        return max(0., min(100., score)), result[1], result[2]
    LeafScores._race_shape_context_score = patched
    try:
        yield
    finally:
        LeafScores._race_shape_context_score = ORIGINAL

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    df = pd.read_csv(args.dataset)
    df = df.loc[df.date.astype(str) >= '2026-09-01'].copy().reset_index(drop=True)
    if df.empty:
        raise ValueError('No eligible season rows')
    df = surface._add_surface_features(df, surface._load_prior_runs())
    df['surface_score'] = (60 + 40 * df.surface_quality).clip(40, 80)
    scores = {name: [] for name in ('live', *ARMS)}
    cache = {}
    for row in df.itertuples():
        key = (row.meeting, int(row.race_number))
        if key not in cache:
            path = Path(row.meeting) / f'Race_{row.race_number}_Logic.json'
            logic = json.loads(path.read_text(encoding='utf-8'))
            context = dict(logic.get('race_analysis', {}))
            context.setdefault('race_date', row.date)
            cache[key] = logic['horses'], context
        horses, context = cache[key]
        horse = horses[str(row.horse_number)]
        def replay():
            return float(RacingEngine(deepcopy(horse), dict(context)).analyze_horse()['ability_score'])
        scores['live'].append(replay())
    delta = np.abs(np.asarray(scores['live']) - df.current_live_recomputed_ability.to_numpy(dtype=float))
    baseline = {'horses': len(df), 'max_abs_delta': float(delta.max()), 'mismatches_ge_0_01': int((delta >= .01).sum())}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not np.isfinite(delta).all() or delta.max() >= .01:
        output.write_text(json.dumps({'baseline': baseline, 'stopped': True}, indent=2))
        raise SystemExit('Baseline failed: ' + str(baseline))
    print('Baseline:', baseline, flush=True)
    for row in df.itertuples():
        horses, context = cache[(row.meeting, int(row.race_number))]
        if row.surface_key != 'ST_TURF' or RacingEngine(deepcopy(horses[str(row.horse_number)]), dict(context))._is_debut():
            for arm in ARMS:
                scores[arm].append(scores['live'][row.Index])
            continue
        for arm in ARMS:
            with shape_patch(arm, row.surface_score, row.surface_key == 'ST_TURF'):
                scores[arm].append(float(RacingEngine(deepcopy(horses[str(row.horse_number)]), dict(context)).analyze_horse()['ability_score']))
    for name, values in scores.items():
        df['score_' + name] = values
    tables = {}
    for period, subset in [('season', df), ('post_2026_09_28', df[df.date.astype(str) > '2026-09-28'])]:
        tables[period] = {}
        for key in ('ST_TURF', 'ST_AWT', 'HV_TURF'):
            part = subset[subset.surface_key == key]
            flags = {name: [] for name in scores}
            for _, race in part.groupby(['meeting', 'race_number'], sort=False):
                actual = dict(zip(race.horse_number.astype(int), race.finish_pos.astype(int)))
                for name in scores:
                    flags[name].append(metrics._ranking_flags(metrics._model_record(race, 'score_' + name), actual))
            tables[period][key] = {'races': len(flags['live']), 'live': metrics._summary(flags['live']), 'arms': {name: metrics._paired(flags[name], flags['live']) for name in ARMS} if flags['live'] else {}}
    report = {'baseline': baseline, 'date_min': str(df.date.min()), 'date_max': str(df.date.max()), 'races': int(df.groupby(['meeting', 'race_number']).ngroups), 'tables': tables}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'baseline': baseline, 'races': report['races'], 'date_min': report['date_min'], 'date_max': report['date_max']}))

if __name__ == '__main__':
    main()
