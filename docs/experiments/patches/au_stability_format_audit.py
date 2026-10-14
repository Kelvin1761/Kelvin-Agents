#!/usr/bin/env python3
"""Verify decoded-form correctness and attribute stability misses on fixed dev.

Tamworth 2026-10-12 is an exposed mechanism case, excluded from validation.
Only the parser correctness fix is evaluated; no penalty or weights are fitted.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / '.agents/skills/au_racing/au_wong_choi_auto/scripts'
sys.path.insert(0, str(SCRIPTS))
from au_eval import date_partitions  # noqa: E402
from au_racing_engine import engine_core  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import parse_recent_finishes  # noqa: E402
from au_auto_orchestrator import _build_field_summary  # noqa: E402
from au_runtime_micro_ablation import prepare_logic_for_scoring  # noqa: E402
from eval_metrics import race_metrics  # noqa: E402


def legacy_parser(text, **_kwargs):
    if not text:
        return None
    raw = str(text).strip()
    if re.fullmatch(r'\d{2,}', raw):
        return [int(ch) if ch != '0' else 10 for ch in raw]
    nums = [int(n) for n in re.findall(r'\d+', raw)]
    return [n if n else 10 for n in nums if n <= 24] if nums else None


def score_horse(horse, prepared, facts_path, parser):
    ctx = copy.deepcopy(prepared['race_analysis'])
    ctx['field_summary'] = _build_field_summary(prepared['horses'])
    ctx['field_horse_names'] = [h['horse_name'] for h in prepared['horses'].values()]
    with patch.object(engine_core, 'parse_recent_finishes', parser):
        engine = engine_core.RacingEngine(copy.deepcopy(horse), ctx,
                                         facts_section=horse['_data'].get('facts_section', ''),
                                         facts_path=facts_path)
        result = engine.analyze_horse()
    return result


def evaluate(race, rows):
    order = sorted(rows, key=lambda r: (-r['ability'], r['n']))
    positions = {r['n']: r['pos'] for r in rows}
    m = race_metrics([r['n'] for r in order], [n for n, p in positions.items() if p <= 3],
                     actual_pos=positions, field_size=len(rows))
    return {k: float(m[k]) for k in ('gold', 'good_positional', 'pass', 'top3_mean_model_rank')}


def boot_delta(base, cand):
    delta = np.array(cand) - np.array(base)
    rng = np.random.default_rng(7)
    means = [float(rng.choice(delta, len(delta), replace=True).mean()) for _ in range(2000)]
    return {'delta': float(delta.mean()), 'ci95': np.quantile(means, [0.025, 0.975]).tolist()}


def summarize_pairs(pairs):
    result = {'n': len(pairs)}
    for k in ('gold', 'good_positional', 'pass', 'top3_mean_model_rank'):
        base = [p['baseline'][k] for p in pairs]
        cand = [p['candidate'][k] for p in pairs]
        result[k] = {'baseline': float(np.mean(base)), 'candidate': float(np.mean(cand)),
                     **boot_delta(base, cand)}
    return result


def stability_errors(race):
    rows = race['rows']
    ability_order = sorted(rows, key=lambda r: (-r['ability'], r['n']))
    placed = [r for r in rows if r['pos'] <= 3]
    stability = lambda r: map_features_to_matrix_scores(r['features'])['stability']
    negatives = [r for r in ability_order[:2] if r['pos'] > 3]
    overlooked = [r for r in placed if r['n'] not in {q['n'] for q in ability_order[:4]}]
    return {
        'high_stability_unplaced_top2': sum(stability(r) >= 60 for r in negatives),
        'low_stability_missed_podium': sum(stability(r) < 60 for r in overlooked),
        'unplaced_top2': [{'n': r['n'], 'name': r['name'], 'pos': r['pos'],
                          'stability': stability(r), 'form': r['features']['form_score'],
                          'pq': r['features']['performance_quality_score'],
                          'pq_evidence': r.get('evidence', {}).get('performance_quality_score')}
                         for r in negatives],
        'missed_podium': [{'n': r['n'], 'name': r['name'], 'pos': r['pos'],
                          'stability': stability(r), 'form': r['features']['form_score'],
                          'pq': r['features']['performance_quality_score']}
                         for r in overlooked],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--diagnostic', type=Path, required=True)
    ap.add_argument('--case', type=Path, required=True)
    ap.add_argument('--phase', choices=('dev', 'terminal'), default='dev')
    ap.add_argument('--results-csv', type=Path)
    args = ap.parse_args()
    races = json.loads(args.data.read_text())['races']
    dev, terminal = date_partitions(races)
    # Keep the previous eligibility set, split and dates exactly unchanged.
    prior = json.loads(args.diagnostic.read_text())['races']
    eligible = {(r['meeting'], r['race']) for r in prior}
    alignment = None
    if args.results_csv:
        from au_archive_calibrator import load_historical_results, choose_track_rows, normalize_horse_name
        alignment = load_historical_results(args.results_csv)
    excluded = Counter()
    if args.phase == 'terminal':
        dev_evidence = json.loads((args.out / 'audit.json').read_text())
        if any(dev_evidence['dev'][k]['ci95'][1] < 0 for k in ('gold', 'good_positional')):
            raise ValueError('Significant development primary regression: terminal remains closed')
        eligible = set()
        for i in terminal:
            race = races[i]
            if race['meeting'] == args.case.parent.name:
                excluded['exposed_case_meeting'] += 1
                continue
            positions = [r['pos'] for r in race['rows']]
            if len(set(positions)) != len(positions) or sorted(p for p in positions if p <= 3) != [1, 2, 3]:
                excluded['incomplete_or_tied_results'] += 1
                continue
            if alignment is not None:
                expected = choose_track_rows(alignment.get((race['date'], race['race']), []), race['metadata']['track'])
                if len(expected) != len(race['rows']):
                    excluded['incomplete_runner_alignment'] += 1
                    continue
            eligible.add((race['meeting'], race['race']))
    records, changed, drifts, case_report = [], [], [], None
    for index, race in enumerate(races, 1):
        path = Path(race['source'])
        is_case = path == args.case
        if (race['meeting'], race['race']) not in eligible and not is_case:
            continue
        logic = json.loads(path.read_text())
        # This is a structural source-format audit, not an outcome-based filter.
        baseline_rows = copy.deepcopy(race['rows'])
        candidate_rows = copy.deepcopy(race['rows'])
        # Rebuild both arms from exactly the same prepared current source.
        # Frozen leaves define the cohort, not a mixed baseline for scoring.
        if logic.get('horses'):
            prepared, facts_path = prepare_logic_for_scoring(logic, path)
            for row in candidate_rows:
                horse = prepared['horses'][str(row['n'])]
                horse.setdefault('horse_number', row['n'])
                data = horse.get('_data') or {}
                raw = data.get('recent_form')
                fmt = data.get('recent_form_format', 'auto')
                corrected = parse_recent_finishes(raw, source_format=fmt)
                old = legacy_parser(raw)
                base = score_horse(horse, prepared, facts_path, legacy_parser)
                cand = score_horse(horse, prepared, facts_path, parse_recent_finishes) if old != corrected or is_case else base
                error = abs(base['ability_score'] - row['ability'])
                if error > 0.01:
                    drifts.append({'meeting': race['meeting'], 'race': race['race'],
                                   'n': row['n'], 'baseline_drift': error})
                base_row = next(r for r in baseline_rows if r['n'] == row['n'])
                base_row['ability'] = base['ability_score']
                base_row['features'] = base['feature_scores']
                row['ability'] = cand['ability_score']
                row['features'] = cand['feature_scores']
                if old != corrected:
                    changed.append({'date': race['date'], 'meeting': race['meeting'],
                                    'race': race['race'], 'n': row['n'], 'name': row['name'],
                                    'raw': raw, 'old_positions': old, 'new_positions': corrected,
                                    'delta': cand['ability_score'] - base['ability_score'],
                                    'consistency_before': base['feature_scores']['consistency_score'],
                                    'consistency_after': cand['feature_scores']['consistency_score'],
                                    'pq_before': base['feature_scores']['performance_quality_score'],
                                    'pq_after': cand['feature_scores']['performance_quality_score'],
                                    'pq_source': cand['score_provenance']['performance_quality_score'],
                                    'partition': 'dev' if index-1 in dev else 'terminal'})
                if is_case and row['n'] == 2:
                    case_report = {'horse': row['name'], 'raw_positions': raw,
                                   'old_positions': old, 'new_positions': corrected,
                                   'baseline': base, 'candidate': cand}
        if (race['meeting'], race['race']) in eligible:
            pair = {'date': race['date'], 'meeting': race['meeting'], 'race': race['race'],
                    'field': len(candidate_rows),
                    'baseline': evaluate(race, baseline_rows), 'candidate': evaluate(race, candidate_rows)}
            pair['stability_errors'] = stability_errors({**race, 'rows': baseline_rows})
            pair['prepared_input_sha256'] = hashlib.sha256(json.dumps(prepared, sort_keys=True).encode()).hexdigest()
            if alignment is not None:
                result_rows = choose_track_rows(alignment.get((race['date'], race['race']), []), race['metadata']['track'])
                sp = {r['horse_slug']: r.get('sp') for r in result_rows}
                first = min(baseline_rows, key=lambda r: (-r['ability'], r['n']))
                pair['baseline_first_sp'] = sp.get(normalize_horse_name(first['name']))
            records.append(pair)
        if is_case:
            # Evaluation rows omit non-finishers; published ranks included the
            # WHOLE pre-race field. Never mix these two rank denominators.
            for n, horse in prepared['horses'].items():
                if int(n) in {r['n'] for r in baseline_rows}:
                    continue
                horse.setdefault('horse_number', int(n))
                b = score_horse(horse, prepared, facts_path, legacy_parser)
                c = score_horse(horse, prepared, facts_path, parse_recent_finishes)
                baseline_rows.append({'n': int(n), 'ability': b['ability_score']})
                candidate_rows.append({'n': int(n), 'ability': c['ability_score']})
            before = sorted(baseline_rows, key=lambda r: (-r['ability'], r['n']))
            after = sorted(candidate_rows, key=lambda r: (-r['ability'], r['n']))
            case_report['rank_before'] = next(i for i, r in enumerate(before, 1) if r['n'] == 2)
            case_report['rank_after'] = next(i for i, r in enumerate(after, 1) if r['n'] == 2)
            case_report['rank_field_size'] = len(before)
        if index == 1 or index % 250 == 0:
            print(f'Audit {index}/{len(races)}; changed {len(changed)}', flush=True)
    summary = summarize_pairs(records)
    dates = sorted({r['date'] for r in records})
    folds = []
    for k, block in enumerate(np.array_split(dates, 5), 1):
        group = [r for r in records if r['date'] in set(block)]
        folds.append({'fold': k, **summarize_pairs(group)})
    cohorts = {}
    for label, predicate in [('≤8', lambda r: r['field'] <= 8), ('9-10', lambda r: 9 <= r['field'] <= 10),
                             ('11-12', lambda r: 11 <= r['field'] <= 12), ('13+', lambda r: r['field'] >= 13)]:
        cohorts[label] = summarize_pairs([r for r in records if predicate(r)])
    if alignment is not None:
        for label, lo, hi in [('sp:≤3', 0, 3), ('sp:3-6', 3, 6), ('sp:6-10', 6, 10), ('sp:10-21', 10, 21), ('sp:21+', 21, float('inf'))]:
            group = [r for r in records if r.get('baseline_first_sp') is not None and lo < float(r['baseline_first_sp']) <= hi]
            if group:
                cohorts[label] = summarize_pairs(group)
    report = {'design': {'purpose': 'parser correctness, not weight tuning',
                         'dataset_sha256': hashlib.sha256(args.data.read_bytes()).hexdigest(),
                         'baseline_method': 'both arms freshly replayed on identical prepared inputs; prior snapshot fixes cohort only',
                         'phase': args.phase,
                         'terminal_metrics_opened': args.phase == 'terminal',
                         'excluded': dict(excluded),
                         'case_excluded_from_validation': str(args.case),
                         'case_meeting_excluded_from_terminal': args.case.parent.name,
                         'weights_changed': False},
              args.phase: summary, 'folds': folds, 'cohorts': cohorts, 'changed': changed,
              'drifts': drifts, 'case': case_report, 'races': records}
    args.out.mkdir(parents=True, exist_ok=True)
    filename = 'audit.json' if args.phase == 'dev' else 'terminal.json'
    (args.out / filename).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(summary), flush=True)
    print(f"Changed horses: {len(changed)}; Tamworth rank {case_report['rank_before']}->{case_report['rank_after']}")


if __name__ == '__main__':
    main()
