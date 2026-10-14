#!/usr/bin/env python3
"""Fixed, development-only stability design experiments. Never edits live code."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / '.agents/skills/au_racing/au_wong_choi_auto/scripts'
sys.path.insert(0, str(SCRIPTS))
from au_auto_orchestrator import _build_field_summary  # noqa: E402
from au_eval import _stage4_metric_rows, _pairs, _counts  # noqa: E402
from au_racing_engine.engine_core import RacingEngine, _surface_kind  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import (  # noqa: E402
    CONSISTENCY_MICRO_WEIGHTS, compose_matrix_score, MATRIX_WEIGHTS,
)
from au_runtime_micro_ablation import prepare_logic_for_scoring  # noqa: E402

RECENCY = (1.0, 0.8, 0.6, 0.4)
CANDIDATES = ('A', 'B', 'AB')
FORM_SHARES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def contextual_quality(runs, today_distance, today_going, as_of):
    """Same raw quality; reweight existing dated runs by contextual similarity."""
    if len(runs) < 2:
        return None, {}
    today_surface = _surface_kind(today_going)
    values, weights, compatibility, ages = [], [], [], []
    for i, run in enumerate(runs[:4]):
        run_date = str(run.get('date') or '')
        if not run_date or run_date >= as_of:
            raise ValueError(f'Unproven PIT PQ evidence {run_date} >= {as_of}')
        ages.append((date.fromisoformat(as_of) - date.fromisoformat(run_date)).days)
        distance = run.get('distance') or 0
        factor = 1.0
        if today_distance and distance:
            factor *= (min(float(distance), float(today_distance)) /
                       max(float(distance), float(today_distance))) ** 2
        old_surface = _surface_kind(run.get('going', ''))
        if today_surface and old_surface and today_surface != old_surface:
            factor *= 0.25
        values.append(float(run['quality']))
        compatibility.append(factor)
        weights.append(RECENCY[i] * factor)
    raw = sum(v * w for v, w in zip(values, weights)) / sum(weights)
    effective_n = sum(weights) ** 2 / sum(w * w for w in weights)
    mean = sum(v * w for v, w in zip(values, RECENCY)) / sum(RECENCY[:len(values)])
    spread = (sum(w * (v - mean) ** 2 for v, w in zip(values, RECENCY)) /
              sum(RECENCY[:len(values)])) ** 0.5
    # Match the live digest's six-decimal raw precision; identity context must
    # not create changes merely by restoring hidden floating-point digits.
    return round(raw, 6), {'effective_n': effective_n, 'quality_sd': spread,
                 'weighted_compatibility': sum(RECENCY[i] * f for i, f in enumerate(compatibility)) /
                                           sum(RECENCY[:len(compatibility)]),
                 'newest_age_days': min(ages), 'oldest_age_days': max(ages),
                 'run_count': len(values), 'context_weights': weights}


def fallback_quality(score, source, career_starts):
    if source != 'consistency_fallback' or career_starts <= 0:
        return score
    return max(0.0, min(100.0, score - (CONSISTENCY_MICRO_WEIGHTS['base'] - 60.0)))


def build_snapshot(prior, dest):
    source = json.loads(prior.read_text())['races']
    races = []
    code_digest = hashlib.sha256()
    for path in sorted((SCRIPTS / 'au_racing_engine').glob('*.py')):
        code_digest.update(path.name.encode())
        code_digest.update(path.read_bytes())
    for index, selected in enumerate(source, 1):
        path = Path(selected['source']) if 'source' in selected else None
        if path is None:
            # Diagnostic records retain identity; retrieve path via fixed runtime.
            raise ValueError('Source path required in fixed dev manifest')
        logic = json.loads(path.read_text())
        prepared, facts_path = prepare_logic_for_scoring(logic, path)
        context = dict(prepared['race_analysis'])
        context['field_summary'] = _build_field_summary(prepared['horses'])
        context['field_horse_names'] = [h['horse_name'] for h in prepared['horses'].values()]
        positions = {int(r['n']): r['pos'] for r in selected['rows']}
        full_rows = []
        meta = selected['metadata']
        for num, horse in sorted(prepared['horses'].items(), key=lambda item: int(item[0])):
            number = int(num)
            hd = dict(horse)
            hd.setdefault('horse_number', number)
            data = hd.get('_data') or {}
            engine = RacingEngine(hd, context, facts_section=data.get('facts_section', ''),
                                  facts_path=facts_path)
            result = engine.analyze_horse()
            detail = result['stability_detail']
            pq_source = result['score_provenance']['performance_quality_score']
            raw = (detail.get('performance_quality') or {}).get('raw')
            runs = (detail.get('performance_quality') or {}).get('runs') or []
            contextual_raw, reliability = (None, {})
            if pq_source == 'class_adjusted_margin_field_relative':
                contextual_raw, reliability = contextual_quality(
                    runs, meta.get('distance') or 0, meta.get('going', ''), selected['date'])
            full_rows.append({
                'n': number, 'name': hd['horse_name'],
                'features': result['feature_scores'], 'ability': result['ability_score'],
                'overlay': result['ability_score'] - compose_matrix_score(result['matrix_scores']),
                'pq_source': pq_source, 'pq_raw': raw, 'contextual_raw': contextual_raw,
                'pq_field_raw': data.get('performance_quality_raw'),
                'pq_runs': runs, 'pq_detail': detail.get('performance_quality'),
                'form_detail': detail.get('form'), 'consistency_detail': detail.get('consistency'),
                'career_starts': engine._career_starts(),
                'official_entries': [{k: e.get(k) for k in ('date', 'venue', 'distance', 'going', 'placing', 'field_size')}
                                     for e in engine._official_entries()[:4]],
                'reliability': reliability,
            })
        # Outcome fields enter ONLY after every horse in the full field is scored.
        for row in full_rows:
            row['pos'] = positions.get(row['n'])
        races.append({'date': selected['date'], 'meeting': selected['meeting'],
                      'race': selected['race'], 'metadata': meta, 'source': str(path),
                      'full_rows': full_rows,
                      'field_summary': context['field_summary'],
                      'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        if index == 1 or index % 100 == 0:
            print(f'Stability dev snapshot {index}/{len(source)}', flush=True)
    write_json(dest, {'design': {'scope': 'previously fixed DEVELOPMENT only',
                                 'manifest_sha256': hashlib.sha256(prior.read_bytes()).hexdigest(),
                                 'engine_sha256': code_digest.hexdigest(),
                                 'weights': MATRIX_WEIGHTS,
                                 'terminal_included': False,
                                 'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()},
                      'races': races})


def candidate_race(race):
    full = race['full_rows']
    # Preserve raw contributors to the live field summary, including runners
    # without joined outcomes. Change only fresh complete PQ contributors.
    raw = [round(float(r['contextual_raw']), 6) if r['contextual_raw'] is not None else float(r['pq_field_raw'])
           for r in full if r['pq_field_raw'] is not None]
    mean = statistics.mean(raw) if raw else None
    sd = statistics.pstdev(raw) if len(raw) >= 2 else 0.0
    rows = []
    for old in full:
        if old['pos'] is None:
            continue
        row = dict(old)
        pq = float(old['features']['performance_quality_score'])
        a = fallback_quality(pq, old['pq_source'], old['career_starts'])
        b = pq
        if old['contextual_raw'] is not None and len(raw) >= 3 and sd > 0:
            b = max(0.0, min(100.0, 60 + 20 * (round(float(old['contextual_raw']), 6) - mean) / sd))
        row['candidate_features'] = {}
        for key, score in [('A', a), ('B', b), ('AB', a if old['pq_source'] == 'consistency_fallback' else b)]:
            fs = dict(old['features'])
            fs['performance_quality_score'] = score
            row['candidate_features'][key] = fs
        rows.append(row)
    return {**race, 'rows': rows, 'field': len(rows)}


def scorer(candidate=None, neutral_stability=False, form_share=None):
    def score(row):
        fs = row['features'] if candidate is None else row['candidate_features'][candidate]
        matrix = map_features_to_matrix_scores(fs)
        if form_share is not None:
            matrix['stability'] = round(max(0.0, min(100.0,
                60 + form_share * (fs['form_score'] - 60) +
                (1 - form_share) * (fs['performance_quality_score'] - 60))), 2)
        if neutral_stability:
            matrix['stability'] = 60.0
        return compose_matrix_score(matrix) + row['overlay']
    return score


def paired_summary(base, cand, indices, boot=2000):
    keys = tuple(base[0])
    out = {'n': len(indices)}
    rng = np.random.default_rng(7)
    draws = rng.integers(0, len(indices), (boot, len(indices)))
    for key in keys:
        b = np.array([base[i][key] for i in indices], dtype=float)
        c = np.array([cand[i][key] for i in indices], dtype=float)
        delta = c - b
        ci = np.quantile(delta[draws].mean(axis=1), [0.025, 0.975]).tolist()
        out[key] = {'baseline': float(b.mean()), 'candidate': float(c.mean()),
                    'delta': float(delta.mean()), 'ci95': ci}
    return out


def health_summary(races):
    by_source = defaultdict(list)
    for race in races:
        for row in race['rows']:
            by_source[row['pq_source']].append(row)
    out = {}
    for source, rows in by_source.items():
        out[source] = {
            'runners': len(rows),
            'pq_mean': statistics.mean(r['features']['performance_quality_score'] for r in rows),
            'missing_form': sum(not (r.get('form_detail') or {}).get('rows') for r in rows),
            'positive_pq': sum(r['features']['performance_quality_score'] > 60 for r in rows),
            'career_positive_no_official_entries': sum(r['career_starts'] > 0 and not r['official_entries'] for r in rows),
        }
    return out


def mix_audit(races, baseline, folds, groups):
    all_ids = list(range(len(races)))
    metric_rows, grid = {}, {}
    for share in FORM_SHARES:
        metrics = _stage4_metric_rows(races, scorer(form_share=share))
        metric_rows[share] = metrics
        summary = paired_summary(baseline, metrics, all_ids)
        grid[str(share)] = {'development': summary,
                            'folds': [paired_summary(baseline, metrics, block) for block in folds],
                            'cohorts': {key: paired_summary(baseline, metrics, group) for key, group in groups.items() if key.startswith('field:')},
                            'decision': 'DEV_REJECT' if any(summary[k]['delta'] < -1e-12 for k in ('gold', 'good_positional')) else 'DEV_ONLY_NOT_VALIDATED'}
    forward, baseline_forward, candidate_forward = [], [], []
    for k in range(1, len(folds)):
        train = [i for fold in folds[:k] for i in fold]
        test = folds[k]
        acceptable = []
        for share, metrics in metric_rows.items():
            delta = {key: np.mean([metrics[i][key] - baseline[i][key] for i in train])
                     for key in ('gold', 'good_positional')}
            if all(v >= -1e-12 for v in delta.values()) and any(v > 1e-12 for v in delta.values()):
                acceptable.append(share)
        locked = float(statistics.median(acceptable)) if acceptable else 0.6
        metrics = _stage4_metric_rows([races[i] for i in test], scorer(form_share=locked))
        b = [baseline[i] for i in test]
        summary = paired_summary(b, metrics, list(range(len(test))))
        forward.append({'test_fold': k+1, 'train_races': len(train), 'test_races': len(test),
                        'train_acceptable_form_shares': acceptable, 'locked_form_share': locked,
                        'test_dates': [min(races[i]['date'] for i in test), max(races[i]['date'] for i in test)],
                        'summary': summary})
        baseline_forward.extend(b)
        candidate_forward.extend(metrics)
    pooled = paired_summary(baseline_forward, candidate_forward, list(range(len(baseline_forward))))
    return {'grid': grid, 'forward': forward, 'forward_pooled': pooled,
            'selection': 'previous folds only; median of primary-nonregressing, primary-improving ratios; otherwise baseline .6',
            'promotion': 'not evaluated on untouched terminal; do not deploy dev optimum'}


def evidence_share(row, mode):
    if mode not in ('D1', 'D2', 'D12'):
        raise ValueError(f'Unknown evidence route {mode}')
    has_form = bool((row.get('form_detail') or {}).get('rows'))
    if mode in ('D1', 'D12') and not has_form and row['pq_source'] == 'class_adjusted_margin_field_relative':
        return 0.0
    if mode in ('D2', 'D12') and has_form and row['pq_source'] == 'consistency_fallback':
        return 1.0
    return 0.6


def evaluate_routes(snapshot, out):
    payload = json.loads(snapshot.read_text())
    if payload['design'].get('terminal_included') is not False:
        raise ValueError('Development snapshots only')
    races = [candidate_race(r) for r in payload['races']]
    baseline = _stage4_metric_rows(races, scorer())
    indices = list(range(len(races)))
    dates = sorted({r['date'] for r in races})
    folds = [[i for i, r in enumerate(races) if r['date'] in set(block)] for block in np.array_split(dates, 5)]
    raw, candidates = {}, {}
    for mode in ('D1', 'D2', 'D12'):
        def route_score(row):
            return scorer(form_share=evidence_share(row, mode))(row)
        metrics = _stage4_metric_rows(races, route_score)
        raw[mode] = metrics
        summary = paired_summary(baseline, metrics, indices)
        fold_results = [paired_summary(baseline, metrics, block) for block in folds]
        repaired = harmed = 0
        for b, c in zip(baseline, metrics):
            bg, cg = b['gold'] or b['good_positional'], c['gold'] or c['good_positional']
            repaired += not bg and cg
            harmed += bg and not cg
        candidates[mode] = {
            'development': summary, 'folds': fold_results,
            'primary_nonnegative_folds': sum(all(f[k]['delta'] >= -1e-12 for k in ('gold', 'good_positional')) for f in fold_results),
            'changed_runners': sum(abs(route_score(row) - scorer()(row)) > .0001 for race in races for row in race['rows']),
            'repaired_misses': repaired, 'harmed_successes': harmed,
            'decision': 'DEV_REJECT' if any(summary[k]['delta'] < -1e-12 for k in ('gold', 'good_positional')) else 'DEV_ONLY_NOT_VALIDATED',
        }
        print(mode, json.dumps({'gold': summary['gold']['delta'], 'good': summary['good_positional']['delta'],
                                'decision': candidates[mode]['decision']}), flush=True)
    report = {'design': {**payload['design'], 'terminal_opened': False,
                         'snapshot_sha256': hashlib.sha256(snapshot.read_bytes()).hexdigest()},
              'candidates': candidates,
              'interactions': {'D12_minus_D1': paired_summary(raw['D1'], raw['D12'], indices),
                               'D12_minus_D2': paired_summary(raw['D2'], raw['D12'], indices)}}
    write_json(out / 'routing_results.json', report)


def evaluate(snapshot, out):
    payload = json.loads(snapshot.read_text())
    if payload['design'].get('terminal_included') is not False:
        raise ValueError('Only fixed development snapshots are permitted')
    if payload['design']['weights'] != MATRIX_WEIGHTS:
        raise ValueError('Baseline weight drift')
    races = [candidate_race(r) for r in payload['races']]
    base_score = scorer()
    max_error = max(abs(base_score(r) - r['ability']) for race in races for r in race['rows'])
    if max_error > .01:
        raise ValueError(f'Replica drift {max_error}')
    baseline = _stage4_metric_rows(races, base_score)
    neutral = _stage4_metric_rows(races, scorer(neutral_stability=True))
    ids = list(range(len(races)))
    dates = sorted({r['date'] for r in races})
    folds = [[i for i, r in enumerate(races) if r['date'] in set(block)] for block in np.array_split(dates, 5)]
    groups = defaultdict(list)
    for i, race in enumerate(races):
        n = len(race['rows'])
        bucket = '≤8' if n <= 8 else '9-10' if n <= 10 else '11-12' if n <= 12 else '13+'
        groups['field:' + bucket].append(i)
        groups['track:' + race['metadata']['track']].append(i)
        groups['going:' + race['metadata']['going']].append(i)
        if any(r['career_starts'] > 0 and r['pq_source'] == 'consistency_fallback' for r in race['rows']):
            groups['has_non_debut_fallback'].append(i)
        if any(r['reliability'].get('weighted_compatibility', 1) < .75 for r in race['rows']):
            groups['has_context_mismatch'].append(i)
        distance = race['metadata'].get('distance') or 0
        groups['distance:' + ('≤1200' if distance <= 1200 else '1201-1600' if distance <= 1600 else '1601-2000' if distance <= 2000 else '2001+')].append(i)
    candidates, raw_metric_rows = {}, {}
    component_budget = paired_summary(baseline, neutral, ids)
    for name in CANDIDATES:
        fn = scorer(name)
        metrics = _stage4_metric_rows(races, fn)
        raw_metric_rows[name] = metrics
        summary = paired_summary(baseline, metrics, ids)
        fold_results = [paired_summary(baseline, metrics, block) for block in folds]
        primary_regression = any(summary[k]['delta'] < -1e-12 for k in ('gold', 'good_positional'))
        changed = sum(abs(fn(r) - base_score(r)) > .0001 for race in races for r in race['rows'])
        repaired, harmed, changed_races = 0, 0, 0
        for i, race in enumerate(races):
            b_order = sorted(race['rows'], key=lambda r: (-base_score(r), r['n']))
            c_order = sorted(race['rows'], key=lambda r: (-fn(r), r['n']))
            changed_races += [r['n'] for r in b_order] != [r['n'] for r in c_order]
            b_good = baseline[i]['gold'] or baseline[i]['good_positional']
            c_good = metrics[i]['gold'] or metrics[i]['good_positional']
            repaired += not b_good and c_good
            harmed += b_good and not c_good
        information = {}
        for key in ('top3_capture_at5', 'mean_top3_model_rank', 'competitive_recall_at5', 'ndcg_at5', 'top5_pairwise_auc'):
            half_width = (summary[key]['ci95'][1] - summary[key]['ci95'][0]) / 2
            budget = abs(component_budget[key]['delta'])
            information[key] = {'stability_neutral_budget': budget, 'paired_ci_half_width': half_width,
                                'informative_at_component_scale': budget >= half_width}
        candidates[name] = {'development': summary, 'folds': fold_results,
                            'cohorts': {key: paired_summary(baseline, metrics, group) for key, group in groups.items() if len(group) >= 20},
                            'changed_runners': changed, 'changed_races': changed_races,
                            'repaired_misses': repaired, 'harmed_successes': harmed,
                            'canonical_pass': {'baseline': _counts(races, base_score)['pass'], 'candidate': _counts(races, fn)['pass']},
                            'metric_information': information,
                            'decision': 'DEV_REJECT' if primary_regression else 'DEV_ONLY_NOT_VALIDATED',
                            'primary_nonnegative_folds': sum(all(f[k]['delta'] >= -1e-12 for k in ('gold', 'good_positional')) for f in fold_results)}
        print(name, json.dumps({'decision': candidates[name]['decision'], 'gold': summary['gold']['delta'],
                               'good': summary['good_positional']['delta'], 'repair': repaired, 'harm': harmed}), flush=True)
    interactions = {
        'AB_minus_A': paired_summary(raw_metric_rows['A'], raw_metric_rows['AB'], ids),
        'AB_minus_B': paired_summary(raw_metric_rows['B'], raw_metric_rows['AB'], ids),
    }
    mix = mix_audit(races, baseline, folds, groups)
    report = {'design': {**payload['design'], 'snapshot_sha256': hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                         'terminal_opened': False, 'replica_max_error': max_error,
                         'promotion': 'NOT PERMITTED: exposed development data only',
                         'leakage_audit': 'new contextual inputs dated before race; existing reconstructed baseline PIT not fully certified'},
              'baseline': {'canonical_counts': _counts(races, base_score)},
              'source_health': health_summary(races), 'component_budget': component_budget,
              'candidates': candidates, 'interactions': interactions, 'mix': mix}
    write_json(out / 'results.json', report)
    write_json(out / 'comparison_rows.json', {'baseline': baseline, 'candidates': raw_metric_rows,
                                             'identity': [{'date': r['date'], 'meeting': r['meeting'], 'race': r['race']} for r in races]})
    (out / 'REPORT.md').write_text(render(report), encoding='utf-8')


def render(report):
    lines = ['# Stability 設計：固定 development 消融', '',
             '**唔係已證實改善；terminal 未開，唔准部署本輪權重或候選。**', '',
             'A：非初出 PQ fallback 移除固定正截距；B：按歷史途程／跑道接近程度重算完整 PQ；AB：兩項組合。', '',
             '| 候選 | Gold Δ | Good Δ | 救返失手／破壞成功 | Gold＋Good無回歸 folds | 判決 |',
             '|---|---:|---:|---:|---:|---|']
    for key, candidate in report['candidates'].items():
        d = candidate['development']
        lines.append(f"| {key} | {100*d['gold']['delta']:+.3f}pp | {100*d['good_positional']['delta']:+.3f}pp | {candidate['repaired_misses']}/{candidate['harmed_successes']} | {candidate['primary_nonnegative_folds']}/5 | {candidate['decision']} |")
    lines += ['', '## 排序指標', '', '| 候選 | capture@5 Δ | 前三平均rank Δ | NDCG@5 Δ | Top5 AUC Δ |', '|---|---:|---:|---:|---:|']
    for key, c in report['candidates'].items():
        d = c['development']
        lines.append(f"| {key} | {d['top3_capture_at5']['delta']:+.5f} | {d['mean_top3_model_rank']['delta']:+.5f} | {d['ndcg_at5']['delta']:+.5f} | {d['top5_pairwise_auc']['delta']:+.5f} |")
    lines += ['', '所有 bootstrap CI、五段日期 folds、cohorts、stability 消融預算及組合邊際見 results.json。', '',
              '## FORM:PQ 配比（單獨改配比）', '',
              '| FORM:PQ | Gold Δ | Good Δ | 判決 |', '|---|---:|---:|---|']
    for share, result in report['mix']['grid'].items():
        d = result['development']
        lines.append(f"| {float(share):.0%}:{1-float(share):.0%} | {100*d['gold']['delta']:+.3f}pp | {100*d['good_positional']['delta']:+.3f}pp | {result['decision']} |")
    lines += ['', '## 前段選配比，後段測試', '',
              '| Fold | 鎖定 FORM 份額 | Gold Δ | Good Δ |', '|---|---:|---:|---:|']
    for f in report['mix']['forward']:
        d = f['summary']
        lines.append(f"| {f['test_fold']} | {f['locked_form_share']:.0%} | {100*d['gold']['delta']:+.3f}pp | {100*d['good_positional']['delta']:+.3f}pp |")
    lines += ['',
              '## 來源健康', '', '| PQ 來源 | 馬匹 | FORM缺可用名次 | PQ高於60 | 有生涯但正式entries缺失 |', '|---|---:|---:|---:|---:|']
    for source, h in report['source_health'].items():
        lines.append(f"| {source} | {h['runners']} | {h['missing_form']} | {h['positive_pq']} | {h['career_positive_no_official_entries']} |")
    lines += ['', '## 解讀界線', '',
              '- 高分往績、今日適用性、證據可信程度分開保存；波動本身只作 risk metadata，唔自動扣分。',
              '- context 權重只改原有最多四場完整 dated runs 嘅平均；完全同情境時應不變。',
              '- 場內尺度包括完整賽前馬群；無賽果馬仍參與原本 PQ field summary。',
              '- 來源缺資料仍保留 unknown；recovered score 不冒認完整 raw evidence。',
              '- 之前 terminal 已曝光，本輪完全冇分析；dev folds 已曝光，唔叫 pristine holdout。',
              '- 現行 baseline 全量 runtime 重建，PIT 歷史統計未逐欄核證；只適合研究。', '',
              f"Snapshot SHA256：`{report['design']['snapshot_sha256']}`", '']
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', type=Path)
    ap.add_argument('--snapshot', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--build', action='store_true')
    ap.add_argument('--routing', action='store_true')
    args = ap.parse_args()
    if args.build:
        if not args.manifest:
            ap.error('--build requires --manifest')
        build_snapshot(args.manifest, args.snapshot)
    if args.routing:
        evaluate_routes(args.snapshot, args.out)
    else:
        evaluate(args.snapshot, args.out)


if __name__ == '__main__':
    main()
