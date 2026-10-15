#!/usr/bin/env python3
"""Read-only trial-cutoff research; no production engine edits or archive writes."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / '.agents/skills/au_racing/au_wong_choi_auto/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / '.agents/skills/shared_racing'))


def eligible(horse):
    value = horse.get('career_race_starts', horse.get('career_starts'))
    try:
        return float(value) >= 6
    except (TypeError, ValueError):
        return False


def dump_pf(out):
    from au_racing_engine import engine_core as core
    original = core.refresh_pf_own_l600
    counts = Counter()

    def refresh(logic, facts_path):
        result = original(logic, facts_path)
        for horse in logic.get('horses', {}).values():
            if not eligible(horse):
                continue
            data = horse.get('_data') or {}
            metrics = data.get('pf_metrics') or {}
            runs = metrics.get('pf_runs') or []
            kept = [run for run in runs if run.get('run_kind') != 'trial']
            if len(kept) == len(runs):
                continue
            counts['horses_with_trial_pf_removed'] += 1
            counts['trial_pf_rows_removed'] += len(runs) - len(kept)
            source = (metrics.get('pf_aggregates') or {}).get('source', 'unknown')
            data['pf_metrics'] = {
                'pf_runs': kept,
                'pf_aggregates': core._pf_aggregates(kept, source),
            }
        counts['races_read'] += 1
        if counts['races_read'] % 250 == 0:
            print(dict(counts), flush=True)
        return result

    core.refresh_pf_own_l600 = refresh
    sys.argv = ['au_dump_engine_leaves.py', '--out', str(out)]
    runpy.run_path(str(SCRIPTS / 'au_dump_engine_leaves.py'), run_name='__main__')
    out.with_suffix('.counts.json').write_text(json.dumps(dict(counts), indent=2))


def dump_form(out):
    from au_racing_engine import engine_core as core
    original = core.RacingEngine._form_score

    def form(engine):
        if not eligible(engine.horse_data):
            return original(engine)
        saved = engine.data.get('timing_trial_600m_avg_speed')
        engine.data['timing_trial_600m_avg_speed'] = None
        try:
            return original(engine)
        finally:
            engine.data['timing_trial_600m_avg_speed'] = saved

    core.RacingEngine._form_score = form
    sys.argv = ['au_dump_engine_leaves.py', '--out', str(out)]
    runpy.run_path(str(SCRIPTS / 'au_dump_engine_leaves.py'), run_name='__main__')


def evaluate(base_path, pf_path, form_path, out):
    from au_eval import default_scorer, _stage4_metric_rows, _counts
    from au_leaf_power import within_race_auc
    from model_evaluation_decision import evaluate_full_record, holm_adjust

    base = json.loads(base_path.read_text())['races']
    pf = json.loads(pf_path.read_text())['races']
    form = json.loads(form_path.read_text())['races']
    key = lambda race: (race['date'], race['meeting'], race['race'])
    assert [key(r) for r in base] == [key(r) for r in pf]
    assert [key(r) for r in base] == [key(r) for r in form]
    for br, pr in zip(base, pf):
        assert [(r['n'], r['name'], r['pos']) for r in br['rows']] == [
            (r['n'], r['name'], r['pos']) for r in pr['rows']]
    # Include only complete observed race labels, as required by canonical AU eval.
    valid = [i for i, race in enumerate(base)
             if sum(r['pos'] <= 3 for r in race['rows']) >= 3
             and any(r['pos'] == 1 for r in race['rows'])]
    base, pf, form = ([races[i] for i in valid] for races in (base, pf, form))
    changed_features = {'B': Counter(), 'C': Counter()}
    combo = json.loads(json.dumps(pf))
    for br, pr, fr, cr in zip(base, pf, form, combo):
        for b, p, f, c in zip(br['rows'], pr['rows'], fr['rows'], cr['rows']):
            assert (b['n'], b['name'], b['pos']) == (f['n'], f['name'], f['pos'])
            for arm, row in [('B', p), ('C', f)]:
                for k, v in b['features'].items():
                    if v != row['features'][k]:
                        changed_features[arm][k] += 1
                assert row['wet'] == b['wet'] and row['proven_class'] == b['proven_class']
                assert row['features']['preparation_score'] == b['features']['preparation_score']
                assert row['features']['jockey_horse_fit_score'] == b['features']['jockey_horse_fit_score']
            c['features']['form_score'] = f['features']['form_score']
            c['ability'] = round(default_scorer(c), 4)
    assert set(changed_features['C']) <= {'form_score'}, changed_features
    assert set(changed_features['B']) <= {'pace_figure_score'}, changed_features
    errors = [abs(round(default_scorer(r), 4) - r['ability'])
              for race in base + pf + form for r in race['rows']]
    assert max(errors) < 0.000051, max(errors)

    def neutral(row):
        if not eligible(row):
            return row['ability']
        return round(default_scorer({**row, 'features': {
            **row['features'], 'trial_score': 60.0}}), 4)

    def ranked(race, scorer):
        return [r['n'] for r in sorted(race['rows'], key=lambda r: -scorer(r))]

    scorers = {'base': (base, lambda r: r['ability']),
               'A': (base, neutral), 'B': (pf, lambda r: r['ability']),
               'AB': (pf, neutral), 'C': (form, lambda r: r['ability']),
               'ABC': (combo, neutral)}
    metrics = {arm: _stage4_metric_rows(races, scorer)
               for arm, (races, scorer) in scorers.items()}
    dates = [r['date'] for r in base]
    summary = {'races': len(base), 'runners': sum(len(r['rows']) for r in base),
               'dates': [min(dates), max(dates)], 'days': len(set(dates)),
               'replay_max_error': max(errors),
               'leakage_audit': 'FLAG: historical source availability/PIT not independently certified',
               'promotion_authorized': False,
               'baseline_sha256': hashlib.sha256(base_path.read_bytes()).hexdigest(),
               'pf_sha256': hashlib.sha256(pf_path.read_bytes()).hexdigest()}
    summary['form_sha256'] = hashlib.sha256(form_path.read_bytes()).hexdigest()
    summary['changed_features'] = {k: dict(v) for k, v in changed_features.items()}
    # Captured-era inputs are not independent source certification. Keep the
    # leakage safety gate closed: report statistical diagnostics separately.
    def report(indices):
        result = {}
        baseline = [metrics['base'][i] for i in indices]
        ds = [dates[i] for i in indices]
        for arm in scorers:
            rows = [metrics[arm][i] for i in indices]
            values = {k: sum(float(r[k]) for r in rows if r[k] is not None) /
                      max(1, sum(r[k] is not None for r in rows)) for k in rows[0]}
            decision = evaluate_full_record(
                domain='au', mode='fixed_rule', dates=ds, baseline_rows=baseline,
                candidate_rows=rows, leakage_audit_passed=True,
                ranking_metrics=('top3_capture_at5', 'ndcg_at5', 'top5_pairwise_auc'))
            # True above isolates the statistical test; never label it promotion.
            result[arm] = {'means': values, 'statistical_diagnostic': decision,
                           'context_percent': _counts([scorers[arm][0][i] for i in indices],
                                                      scorers[arm][1]),
                           'top4_changed': sum(
                               ranked(base[i], scorers['base'][1])[:4] !=
                               ranked(scorers[arm][0][i], scorers[arm][1])[:4]
                               for i in indices)}
        p_values = {f'{arm}/{metric}': evidence['p_value']
                    for arm in ('A', 'B', 'AB', 'C', 'ABC')
                    for section in ('primary', 'ranking')
                    for metric, evidence in result[arm]['statistical_diagnostic']['detail'][section].items()}
        return {'n': len(indices), 'arms': result, 'holm_p': holm_adjust(p_values)}

    summary['all'] = report(list(range(len(base))))
    summary['capture_era'] = report([i for i, d in enumerate(dates) if d >= '2026-08-05'])
    cohorts = {}
    for i, race in enumerate(base):
        rows = race['rows']
        n = len(rows)
        bucket = '<=8' if n <= 8 else '9-10' if n <= 10 else '11-12' if n <= 12 else '13+'
        pick = max(rows, key=lambda r: r['ability'])
        try:
            sp = float(pick.get('sp') or 0)
        except (TypeError, ValueError):
            sp = 0
        sp_bucket = 'unknown' if sp <= 0 else '1-3' if sp <= 3 else '3-6' if sp <= 6 else '6-11' if sp <= 11 else '11-21' if sp <= 21 else '21+'
        for label in (f'field/{bucket}', f'going/{pick.get("going")}',
                      f'venue/{race["meeting"][11:]}', f'pick_sp/{sp_bucket}',
                      f'pick_stage/{pick.get("prep_stage")}',
                      f'pick_career/{"6+" if eligible(pick) else "<6_or_unknown"}'):
            cohorts.setdefault(label, []).append(i)
    summary['cohorts'] = {name: report(indices) for name, indices in cohorts.items()}
    power = {}
    for label, predicate in [('6+', eligible), ('<6_or_unknown', lambda r: not eligible(r))]:
        concordant = comparable = runners = 0
        for race in base:
            rows = [r for r in race['rows'] if predicate(r) and r['features']['trial_score'] != 60]
            a, b = within_race_auc([(r['features']['trial_score'], r['pos'] <= 3) for r in rows])
            concordant += a
            comparable += b
            runners += len(rows)
        power[label] = {'runners': runners, 'pairs': comparable,
                        'auc': concordant / comparable if comparable else None}
    summary['trial_leaf_power'] = power
    summary['eligibility'] = dict(Counter('6+' if eligible(r) else '<6_or_unknown'
                                         for race in base for r in race['rows']))
    out.write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k not in ('cohorts',)}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('dump-pf', 'dump-form', 'evaluate'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--pf', type=Path)
    parser.add_argument('--form', type=Path)
    args = parser.parse_args()
    if args.mode == 'dump-pf':
        dump_pf(args.out)
    elif args.mode == 'dump-form':
        dump_form(args.out)
    else:
        evaluate(args.baseline, args.pf, args.form, args.out)


if __name__ == '__main__':
    main()
