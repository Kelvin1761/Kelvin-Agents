"""Locked draw-only study; replay downstream production rounding, SIP and cap."""
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
for path in (REPO, REPO / '.agents/skills/hkjc_racing/hkjc_reflector/scripts',
             REPO / '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts',
             REPO / '.agents/skills/shared_racing'):
    sys.path.insert(0, str(path))
import hkjc_auto_orchestrator as orch
from eval_metrics import race_metrics
from hkjc_racing_engine import scoring
from hkjc_racing_engine.engine_core import RacingEngine
from hkjc_racing_engine.rail_draw_context import DATASET, rail_draw_context_adjustment
from model_evaluation_decision import evaluate_full_record, holm_adjust

ARMS = ('percentile', 'pit_group', 'pit_hierarchy', 'pit_ridge')
METRICS = ('gold', 'good_positional', 'top3_capture_at5', 'ndcg_at5',
           'competitive_recall_at5', 'mean_top3_model_rank')


def read(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def integer(value):
    m = re.search(r'\d+', str(value or ''))
    return int(m.group()) if m else 0


def field_bucket(n):
    return 'le8' if n <= 8 else '9_10' if n <= 10 else '11_12' if n <= 12 else '13plus'


def identity(ctx):
    v = str(ctx.get('venue') or ctx.get('course') or ctx.get('racecourse') or '')
    low = v.lower().replace(' ', '')
    venue = '沙田' if '沙田' in v or 'shatin' in low or v == 'ST' else (
        '跑馬地' if '跑馬地' in v or 'happyvalley' in low or v == 'HV' else '')
    text = ' '.join(str(ctx.get(k) or '') for k in ('venue', 'track', 'surface', 'track_type')).upper()
    track = 'AWT' if any(x in text for x in ('AWT', 'DIRT', '泥', '全天候', 'ALL WEATHER')) else 'Turf'
    return venue, track, integer(ctx.get('distance'))


def load_history():
    frame = pd.read_csv(DATASET)
    frame = frame[frame.Date.astype(str).lt('2026-10-11')].copy()
    for col in ('Draw', 'Distance', 'FieldSize', 'Pos', 'Place'):
        frame[col] = pd.to_numeric(frame[col], errors='coerce')
    frame = frame[frame.Venue.isin(['沙田', '跑馬地']) & frame.Track.isin(['Turf', 'AWT'])
                  & frame.Draw.between(1, 16) & frame.FieldSize.ge(4)
                  & frame.Pos.ge(1) & frame.Pos.le(frame.FieldSize) & frame.Distance.gt(0)].copy()
    keys = ['Date', 'Venue', 'RaceNo']
    if frame.duplicated(keys + ['HorseNo']).any():
        raise ValueError('duplicate training runners')
    groups = frame.groupby(keys)
    frame['maxdraw'] = groups.Draw.transform('max')
    frame['x'] = (frame.Draw - 1) / (frame.maxdraw - 1).clip(lower=1)
    frame['x2'] = frame.x ** 2
    frame['z1'] = frame.x - frame.groupby(keys).x.transform('mean')
    frame['z2'] = frame.x2 - frame.groupby(keys).x2.transform('mean')
    frame['r'] = frame.Place - 3 / frame.FieldSize
    frame['third'] = np.minimum(2, (frame.x * 3).astype(int))
    frame['bucket'] = frame.FieldSize.map(field_bucket)
    frame['raceid'] = frame[keys].astype(str).agg('|'.join, axis=1)
    frame['Rail'] = frame.Rail.fillna('').astype(str)
    return frame


def draw_prediction(arm, horse, ctx, draws, history):
    old = float(horse['python_auto']['feature_scores']['draw_score'])
    eng = RacingEngine(horse, ctx)
    draw = integer(horse.get('barrier') or horse.get('draw'))
    ident = identity(ctx)
    if eng._is_debut() or not ident[0] or not draw or max(draws, default=0) <= 1:
        return old, False, 0
    x = (draw - 1) / (max(draws) - 1)
    if arm == 'percentile':
        straight = ident == ('沙田', 'Turf', 1000)
        adjustment = rail_draw_context_adjustment(ctx, draw)['adjustment']
        return float(np.clip((50 + 25*x if straight else 75 - 25*x) + adjustment, 0, 100)), True, 0
    prior = history[(history.Venue == ident[0]) & (history.Track == ident[1])
                    & (history.Distance == ident[2])]
    if len(prior) < 100 or prior.raceid.nunique() < 20:
        return old, False, len(prior)
    third = min(2, int(x * 3))
    group = prior[prior.third == third]
    e = float(group.r.sum()) / (len(group) + 60)
    if arm == 'pit_hierarchy':
        cell = prior[(prior.Draw == draw) & (prior.bucket == field_bucket(len(draws)))]
        e = (float(cell.r.sum()) + 60*e) / (len(cell) + 60)
        rail = str(ctx.get('rail') or ctx.get('course_rail') or ctx.get('course_config') or '').strip().upper()
        if rail in {'A', 'A+3', 'B', 'B+2', 'C', 'C+3'}:
            sub = cell[cell.Rail == rail]
            e = (float(sub.r.sum()) + 100*e) / (len(sub) + 100)
    elif arm == 'pit_ridge':
        X = prior[['z1', 'z2']].to_numpy()
        beta = np.linalg.solve(X.T @ X + 60*np.eye(2), X.T @ prior.r.to_numpy())
        xx = np.array([(d - 1)/(max(draws)-1) for d in draws])
        e = float(np.array([x - xx.mean(), x*x - np.mean(xx*xx)]) @ beta)
    return float(np.clip(65 + 100*e, 45, 85)), True, len(prior)


def prepare(ev):
    horses = {}
    for number, rec in ev['horses'].items():
        horse = copy.deepcopy(rec['input'])
        auto = copy.deepcopy(rec['auto'])
        robust = auto.get('race_shape_robustness') or {}
        if 'base_race_shape' in robust:
            auto['matrix_scores']['race_shape'] = robust['base_race_shape']
        horse['python_auto'] = auto
        horses[number] = horse
    return horses


def score(horses):
    for horse in horses.values():
        auto = horse['python_auto']
        raw = round(RacingEngine(horse, {})._ability_score(auto['matrix_scores']), 2)
        auto.update(ability_score_raw=raw, ability_score=round(scoring.to_display_scale(raw), 2))
        auto['grade'] = scoring.compute_grade(auto['ability_score'])
        auto.pop('sip_flags', None)
    orch._apply_sip_enhancements(horses)
    orch.HKJCAutoOrchestrator._apply_mainline_shape_robustness(horses)
    return horses


def ranked(horses):
    return [int(n) for n in sorted(horses, key=lambda n: (-horses[n]['python_auto']['ability_score_raw'], int(n)))]


def row_for(base, horses, arm):
    picks = ranked(horses)
    pos = {h['n']: h['pos'] for h in base['horses'] if h.get('pos')}
    metrics = race_metrics(picks, [n for n, p in pos.items() if p <= 3], actual_pos=pos)
    metrics['mean_top3_model_rank'] = metrics.get('top3_mean_model_rank')
    return {**{k: v for k, v in base.items() if k != 'horses'},
            **{k: metrics.get(k) for k in METRICS}, 'picks': picks, 'arm': arm}


def screen(base, candidate, mode):
    return evaluate_full_record(domain='hkjc', mode=mode, dates=[r['date'] for r in base],
                                baseline_rows=base, candidate_rows=candidate,
                                leakage_audit_passed=True, ranking_metrics=METRICS[2:])


def main():
    baseline_path, evidence_path, output = sys.argv[1:]
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    locked = {tuple(key) for key in json.loads(Path(__file__).with_name('canonical_keys.json').read_text())}
    bases = [r for r in read(baseline_path) if (r['meeting'], r['race']) in locked]
    if len(bases) != len(locked) or any('error' in r for r in bases):
        raise ValueError('fresh replay changed canonical race coverage')
    evs = {(r['meeting'], r['race']): r for r in read(evidence_path)}
    history = load_history()
    rows = {arm: [] for arm in ('aa', 'neutral_shape', *ARMS)}
    coverage = Counter()
    checkpoints, predictions = [], []
    for i, base in enumerate(bases):
        ev = evs[(base['meeting'], base['race'])]
        ctx = ev['context']
        ident = identity(ctx)
        horses = prepare(ev)
        aa = score(copy.deepcopy(horses))
        if ranked(aa) != base['picks'] or any(abs(aa[n]['python_auto']['ability_score_raw'] -
                ev['horses'][n]['auto']['ability_score_raw']) > 1e-6 for n in aa):
            raise ValueError(f'A/A differs at {base["meeting"]} R{base["race"]}')
        base['venue'] = ident[0]
        base['awt'] = ident[1] == 'AWT'
        base['distance'] = ident[2]
        base['has_debut'] = any(RacingEngine(h, ctx)._is_debut() for h in horses.values())
        base['going'] = str(ctx.get('going') or ctx.get('track_condition') or 'unknown')
        rows['aa'].append(row_for(base, aa, 'aa'))
        neutral = copy.deepcopy(horses)
        for h in neutral.values():
            h['python_auto']['matrix_scores']['race_shape'] = 60.0
        rows['neutral_shape'].append(row_for(base, score(neutral), 'neutral_shape'))
    power = screen(bases, rows['neutral_shape'], 'fixed_rule')
    aa_screen = screen(bases, rows['aa'], 'fixed_rule')
    assert aa_screen['verdict'] == 'REJECT'
    (out/'power_before_candidates.json').write_text(json.dumps({'budget': power, 'aa': aa_screen}, indent=2))
    for i, base in enumerate(bases):
        ev = evs[(base['meeting'], base['race'])]
        ctx = ev['context']
        prior = history[history.Date.astype(str) < base['date']]
        assert prior.empty or prior.Date.max() < base['date']
        checkpoints.append({'date': base['date'], 'latest_training_date': None if prior.empty else prior.Date.max(),
                            'training_runners': len(prior)})
        horses = prepare(ev)
        draws = [integer(h.get('barrier') or h.get('draw')) for h in horses.values()]
        draws = [d for d in draws if d > 0]
        coverage['races'] += 1
        coverage['unknown_venue_races'] += not bool(identity(ctx)[0])
        for arm in ARMS:
            work = copy.deepcopy(horses)
            for n, horse in work.items():
                old = float(horse['python_auto']['feature_scores']['draw_score'])
                new, eligible, prior_n = draw_prediction(arm, horse, ctx, draws, prior)
                coverage[arm + '_eligible_runners'] += eligible
                predictions.append({'arm': arm, 'meeting': base['meeting'], 'race': base['race'],
                                    'n': n, 'old': old, 'new': new, 'prior_n': prior_n, 'eligible': eligible})
                if not eligible or new == old:
                    continue
                auto = horse['python_auto']
                features = dict(auto['feature_scores'])
                features['draw_score'] = new
                new_shape = RacingEngine(horse, ctx)._race_shape_context_score(features)[0]
                auto['matrix_scores']['race_shape'] = round(new_shape, 2)
                auto['feature_scores']['draw_score'] = round(new, 2)
            rows[arm].append(row_for(base, score(work), arm))
        if i % 50 == 0:
            print(f'candidate replay {i}/{len(bases)}', flush=True)
    reports, pvalues = {}, {}
    tests = {'ST_turf': lambda r: r['venue'] == '沙田' and not r['awt'],
             'HV_turf': lambda r: r['venue'] == '跑馬地' and not r['awt'],
             'AWT': lambda r: r['awt'], 'unknown_venue': lambda r: not r['venue'],
             'straight1000': lambda r: r['venue'] == '沙田' and not r['awt'] and r['distance'] == 1000,
             'sprint': lambda r: r['distance'] <= 1200, 'middle': lambda r: 1200 < r['distance'] <= 1650,
             'route': lambda r: r['distance'] > 1650, 'with_debut': lambda r: r['has_debut']}
    for bucket in ('le8', '9_10', '11_12', '13plus'):
        tests['field_' + bucket] = lambda r, bucket=bucket: field_bucket(r['field']) == bucket
    for arm in ARMS:
        report = screen(bases, rows[arm], 'fixed_rule' if arm == 'percentile' else 'walk_forward_oos')
        for block in ('primary', 'ranking'):
            for name, metric in report['detail'][block].items():
                pvalues[arm + ':' + name] = metric['p_value']
        cohorts = {}
        for label, test in tests.items():
            ix = [i for i, r in enumerate(bases) if test(r)]
            if ix:
                cohorts[label] = {'races': len(ix), 'metrics': {k: {
                    'baseline': float(np.mean([float(bases[i][k]) for i in ix])),
                    'candidate': float(np.mean([float(rows[arm][i][k]) for i in ix])),
                    'delta': float(np.mean([float(rows[arm][i][k])-float(bases[i][k]) for i in ix]))}
                    for k in METRICS}}
        reports[arm] = {'statistical_screen_only': report, 'cohorts': cohorts,
                        'changed_races': sum(b['picks'] != c['picks'] for b, c in zip(bases, rows[arm]))}
    for arm, rr in rows.items():
        (out/(arm + '.jsonl')).write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rr))
    (out/'predictions.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in predictions))
    result = {'baseline_commit': '2d7ec14c09a3d6fa0bc5733406a730f7dff344ff',
              'aa_exact': True, 'races': len(bases), 'runner_appearances': sum(len(r['horses']) for r in bases),
              'dates': sorted({r['date'] for r in bases}), 'coverage': dict(coverage),
              'baseline': {k: float(np.mean([r[k] for r in bases])) for k in METRICS},
              'training_rows': len(history), 'training_races': history.raceid.nunique(),
              'checkpoints': checkpoints, 'holm': holm_adjust(pvalues), 'arms': reports,
              'sha256': {str(p): hashlib.sha256(Path(p).read_bytes()).hexdigest()
                         for p in (DATASET, baseline_path, evidence_path)},
              'promotion': 'NONE: historical artifact availability and starter-denominator provenance not certified; forward remains closed'}
    (out/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'races': len(bases), 'coverage': dict(coverage), 'results': {
        a: {k: v['delta'] for group in ('primary', 'ranking') for k, v in
            reports[a]['statistical_screen_only']['detail'][group].items()} for a in ARMS}}, indent=2))


if __name__ == '__main__':
    main()
