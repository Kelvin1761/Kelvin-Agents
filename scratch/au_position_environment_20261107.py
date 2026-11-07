#!/usr/bin/env python3
"""EXP-20261107-01 research only; protocol fixes candidates before evaluation."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / '.agents/skills/au_racing/au_wong_choi_auto/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / '.agents/skills/shared_racing'))

from au_racing_engine import speed  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402
from au_walkforward_refit import (  # noqa: E402
    RANKING_METRICS, arm_metric_rows, arm_races, exact_score, procedure_hash)
from au_eval import _counts, _stage4_metric_rows  # noqa: E402
from model_evaluation_decision import (  # noqa: E402
    _full_record_metric, evaluate_full_record, evaluate_with_refit_arms, holm_adjust)
from au_position_l600_eval_20261101 import features, fit, horse_values  # noqa: E402


def read(path):
    return json.loads(Path(path).read_text())


def write(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def metric_rows(races):
    return _stage4_metric_rows(races, lambda r: r['ability'])


def candidate_field_scores(field):
    """Exactly constant evidence has no spread, including float summation noise."""
    scores = speed.field_scores(field)
    for n, s in scores.items():
        values = [getattr(h, s.basis) for h in field.values() if getattr(h, s.basis) is not None]
        if values and len(set(values)) == 1:
            scores[n] = speed.SpeedScore(60.0, 'no_spread', s.basis, s.value, values[0], 0.0)
    return scores


def evidence(base, cand, dates, metrics):
    return {k: vars(_full_record_metric(
        [r.get(k) for r in base], [r.get(k) for r in cand], dates,
        higher_is_better=True, blocks=6, bootstrap=2000, seed=7)) for k in metrics}


def build(args):
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    races = [r for r in read(args.dump)['races'] if '2026-08-05' <= r['date'] <= '2026-11-06'
             and sum(x['pos'] <= 3 for x in r['rows']) >= 3 and any(x['pos'] == 1 for x in r['rows'])]
    races.sort(key=lambda r: (r['date'], r['meeting'], r['race']))
    keys = [(r['date'], r['meeting'], r['race']) for r in races]
    assert len(keys) == len(set(keys)), 'duplicate race keys'
    max_gap = 0.0
    pf_gap = rank_gap = 0
    for race in races:
        race['rows'].sort(key=lambda r: r['n'])
        for n, runs in race['pf_field'].items():
            assert all(r.get('run_date') and r['run_date'] < race['date'] for r in runs), (keys, n)
        for row in race['rows']:
            max_gap = max(max_gap, abs(exact_score(row, MATRIX_WEIGHTS) - row['ability']))
            pf_gap += abs(row['pf_new'] - row['features']['pace_figure_score']) > 1e-6
        original = sorted(race['rows'], key=lambda r: (-r['ability'], r['n']))
        exact = sorted(race['rows'], key=lambda r: (-exact_score(r, MATRIX_WEIGHTS), r['n']))
        rank_gap += [r['n'] for r in original] != [r['n'] for r in exact]
    assert max_gap < 1.01e-4 and pf_gap == 0 and rank_gap == 0, (max_gap, pf_gap, rank_gap)
    base = []
    for race in races:
        rows = [{k: v for k, v in row.items() if k not in ('fq', 'cls')} for row in race['rows']]
        for row in rows:
            row['ability'] = exact_score(row, MATRIX_WEIGHTS)
        base.append({k: v for k, v in race.items() if k not in ('rows', 'pf_field', 'fq_field')} | {'rows': rows})
    neutral = []
    for race in base:
        rows = []
        for row in race['rows']:
            r = {**row, 'features': {**row['features'], 'pace_figure_score': 60.0}}
            r['ability'] = exact_score(r, MATRIX_WEIGHTS)
            rows.append(r)
        neutral.append({**race, 'rows': rows})
    # Power is frozen and written before any P/E/EP performance metrics exist.
    dates = [r['date'] for r in base]
    oos_start = sorted(set(dates))[30]
    power_base = [r for r in base if r['date'] >= oos_start]
    power_neutral = [r for r in neutral if r['date'] >= oos_start]
    budget = evidence(metric_rows(power_base), metric_rows(power_neutral),
                      [r['date'] for r in power_base], RANKING_METRICS)
    power = {k: {**v, 'budget': abs(v['delta']), 'mde': (v['ci_high'] - v['ci_low']) / 2,
                 'informative': abs(v['delta']) >= (v['ci_high'] - v['ci_low']) / 2}
             for k, v in budget.items()}
    write(out / 'power.json', power)
    print('A/A', max_gap, pf_gap, rank_gap, 'power', power, flush=True)
    train = [r for r in read(args.training) if features(r) is not None]
    import numpy as np
    errors = {'current': [], 'position': []}
    for date in sorted({r['date'] for r in train if r['date'] >= '2026-01-01'}):
        prior = [r for r in train if r['date'] < date]
        if len(prior) < 2000:
            continue
        beta = fit(prior)
        for r in train:
            if r['date'] == date:
                errors['current'].append(0.17 * r['margin'] - r['y'])
                errors['position'].append(float(np.array(features(r)) @ beta) - r['y'])
    accuracy = {k: {'n': len(v), 'mae_seconds': float(np.mean(np.abs(v))),
                    'rmse_seconds': float(np.sqrt(np.mean(np.square(v))))} for k, v in errors.items()}
    betas, counts = {}, {}
    for date in sorted(set(dates)):
        prior = [r for r in train if r['date'] < date]
        counts[date] = len(prior)
        betas[date] = fit(prior) if len(prior) >= 2000 else None
    arms = {k: [] for k in ('BASE', 'N', 'P', 'E', 'EP')}
    arms['BASE'], arms['N'] = base, neutral
    changed = {k: 0 for k in ('P', 'E', 'EP')}
    coverage = {'horses': 0, 'position_available_runs': 0, 'formal_runs': 0}
    for race, original in zip(base, races):
        pfield = {n: horse_values(runs, speed.SPORTSBET, betas[race['date']])
                  for n, runs in original['pf_field'].items()}
        efield = {n: speed.HorseSpeed(None, h.race, h.runs) for n, h in pfield.items()}
        ps, es = candidate_field_scores(pfield), candidate_field_scores(efield)
        for runs in original['pf_field'].values():
            coverage['formal_runs'] += len(runs)
            coverage['position_available_runs'] += sum(bool(r.get('pos_800') and r.get('pos_400')) for r in runs)
        for label in ('P', 'E', 'EP'):
            rows = []
            for row in race['rows']:
                n = str(row['n'])
                value = {'P': ps[n].score, 'E': es[n].score,
                         'EP': (ps[n].score + es[n].score) / 2}[label]
                r = {**row, 'features': {**row['features'], 'pace_figure_score': round(value, 6)}}
                r['ability'] = exact_score(r, MATRIX_WEIGHTS)
                changed[label] += r['ability'] != row['ability']
                rows.append(r)
            arms[label].append({**race, 'rows': rows})
        coverage['horses'] += len(race['rows'])
    for label, built in arms.items():
        write(out / f'{label}.json', {'races': built})
    meta = {'races': len(base), 'days': len(set(dates)), 'first': min(dates), 'last': max(dates),
            'aa_max_score_gap': max_gap, 'aa_pf_differences': pf_gap, 'aa_rank_differences': rank_gap,
            'coverage': coverage, 'changed_horses': changed, 'training_counts_by_date': counts,
            'timing_accuracy_pit': accuracy,
            'fallback_dates': [d for d, b in betas.items() if b is None],
            'dump_sha256': digest(args.dump), 'training_sha256': digest(args.training),
            'protocol_sha256': digest(ROOT / 'docs/experiments/EXP-20261107-01-au-position-environment-protocol.md'),
            'script_sha256': digest(__file__), 'procedure_hash': procedure_hash(),
            'source_audit': 'FLAG: historical source availability not certified; diagnostics only'}
    write(out / 'build.json', meta)
    print(json.dumps(meta, ensure_ascii=False), flush=True)


def cohort_tags(race):
    rows = race['rows']
    top = min(rows, key=lambda r: (-r['ability'], r['n']))
    n = len(rows)
    tags = {'field': '<=8' if n <= 8 else '9-10' if n <= 10 else '11-12' if n <= 12 else '13+',
            'going': str(top.get('going') or 'unknown'), 'style': str(top.get('style') or 'unknown'),
            'venue': race['meeting'].split(' ', 1)[-1].split(' Race ')[0]}
    for key, limits, names in [
        ('sp', (3, 6, 11, 21), ('<3', '3-6', '6-11', '11-21', '21+')),
        ('distance', (1201, 1601), ('<=1200', '1201-1600', '>1600')),
        ('days_since_last', (90,), ('<90', '90+'))]:
        try:
            val = float(str(top.get(key)).strip('$m'))
            tags[key] = names[sum(val >= lim for lim in limits)]
        except (ValueError, TypeError):
            tags[key] = 'unknown'
    starts = top.get('career_starts')
    tags['career'] = 'unknown' if starts is None else 'debut' if starts == 0 else 'experienced'
    return tags


def judge(args):
    out = Path(args.outdir)
    basepred = read(out / 'wf_BASE.json')
    fullbase = read(out / 'BASE.json')['races']
    index = {(r['date'], r['meeting'], r['race']): r for r in fullbase}
    bp = basepred['predictions']
    dates = [r['date'] for r in bp]
    keys = [(r['date'], r['meeting'], r['race']) for r in bp]
    btags = [cohort_tags(index[k]) for k in keys]
    bmetrics = {arm: arm_metric_rows(bp, arm) for arm in ('live', 'refit')}
    bm = bmetrics['live']
    aa = evaluate_full_record(domain='au', mode='walk_forward_oos', dates=dates,
                             baseline_rows=bm, candidate_rows=bm, leakage_audit_passed=True,
                             ranking_metrics=RANKING_METRICS)
    assert aa['verdict'] == 'REJECT'
    power = read(out / 'power.json')
    informative = tuple(k for k in RANKING_METRICS if power[k]['informative'])
    result = {'races': len(bp), 'days': len(set(dates)), 'first': min(dates), 'last': max(dates),
              'aa': aa, 'informative_metrics': informative, 'candidates': {}, 'ablations': {}}
    family_p = {}
    predictions = {'BASE': bp}
    for label in ('P', 'E', 'EP'):
        pred = read(out / f'wf_{label}.json')
        cp = pred['predictions']
        assert pred['procedure_hash'] == basepred['procedure_hash'] == procedure_hash()
        assert [(r['date'], r['meeting'], r['race']) for r in cp] == keys
        assert [[(r['n'], r['pos']) for r in x['rows']] for x in cp] == [[(r['n'], r['pos']) for r in x['rows']] for x in bp]
        predictions[label] = cp
        cm = {arm: arm_metric_rows(cp, arm) for arm in ('live', 'refit')}
        kwargs = dict(domain='au', dates=dates, live_baseline_rows=bm, live_candidate_rows=cm['live'],
                      refit_baseline_rows=bmetrics['refit'], refit_candidate_rows=cm['refit'],
                      baseline_refit_procedure_hash=basepred['procedure_hash'],
                      candidate_refit_procedure_hash=pred['procedure_hash'], ranking_metrics=informative)
        formal = evaluate_with_refit_arms(**kwargs, leakage_audit_passed=False)
        research = evaluate_with_refit_arms(**kwargs, leakage_audit_passed=True)
        # Shared §8 helper labels A1/A0 fixed_rule; verify the same verdict with
        # the correct fitted-leaf mode and record this explicitly.
        fitted = evaluate_full_record(domain='au', mode='walk_forward_oos', dates=dates,
                                     baseline_rows=bm, candidate_rows=cm['live'],
                                     leakage_audit_passed=True, ranking_metrics=informative)
        assert fitted['verdict'] == research['detail']['arms']['fixed']['verdict']
        counts = {'A0': _counts(arm_races(bp, 'live'), lambda r: r['ability']),
                  'B0': _counts(arm_races(bp, 'refit'), lambda r: r['ability']),
                  'A1': _counts(arm_races(cp, 'live'), lambda r: r['ability']),
                  'B1': _counts(arm_races(cp, 'refit'), lambda r: r['ability'])}
        cohorts = {}
        for tag in btags[0]:
            for val in sorted({t[tag] for t in btags}):
                idx = [i for i, t in enumerate(btags) if t[tag] == val]
                for arm in ('live', 'refit'):
                    cohort_days = len({dates[i] for i in idx})
                    cohorts[f'{tag}:{val}:{arm}'] = {'n': len(idx), 'days': cohort_days,
                        'single_day_bootstrap_degenerate': cohort_days == 1, 'metrics': evidence(
                        [bmetrics[arm][i] for i in idx], [cm[arm][i] for i in idx],
                        [dates[i] for i in idx], ('gold', 'good_positional'))}
        raw = research['detail']['arm_p_holm']
        family_p[label] = min(raw.values())
        result['candidates'][label] = {'formal': formal, 'research': research, 'counts': counts,
                                      'fitted_live_weight_check': fitted, 'cohorts': cohorts,
                                      'all_ranking_diagnostic': {arm: evidence(
                                          bmetrics[arm], cm[arm], dates, RANKING_METRICS)
                                          for arm in ('live', 'refit')}}
        print(label, research['verdict'], research['reason'], counts, flush=True)
    result['family_p_holm'] = holm_adjust(family_p)
    for other in ('P', 'E'):
        result['ablations'][f'EP-{other}'] = {arm: evidence(
            arm_metric_rows(predictions[other], arm), arm_metric_rows(predictions['EP'], arm), dates,
            ('gold', 'good_positional', *RANKING_METRICS)) for arm in ('live', 'refit')}
    write(out / 'judgement.json', result)
    print('family Holm', result['family_p_holm'], flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build')
    b.add_argument('--dump', required=True)
    b.add_argument('--training', required=True)
    b.add_argument('--outdir', required=True)
    j = sub.add_parser('judge')
    j.add_argument('--outdir', required=True)
    args = ap.parse_args()
    {'build': build, 'judge': judge}[args.cmd](args)


if __name__ == '__main__':
    main()
