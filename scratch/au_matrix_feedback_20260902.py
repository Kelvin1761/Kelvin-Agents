#!/usr/bin/env python3
"""Offline, fixed-candidate AU matrix audit. Never changes the live engine/data.

The form variants compile copies of the live method with checked anchors, so
unrelated legacy adjustments remain identical. Outcomes only enter au_eval.
"""
from __future__ import annotations

import argparse
import ast
import dataclasses
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import textwrap

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / '.agents/skills/au_racing/au_wong_choi_auto/scripts'
BASELINE_COMMIT = 'fbf1499878b08aac5829cdae4dbfe5f9b7f2ccb4'
sys.path.insert(0, str(SCRIPTS))
import au_eval as ev  # noqa: E402
from au_auto_orchestrator import _build_field_summary  # noqa: E402
from au_archive_calibrator import ARCHIVE_ROOT  # noqa: E402
from au_dump_engine_leaves import _corpus_meeting_dirs  # noqa: E402
from au_racing_engine import engine_core as ec  # noqa: E402

# Freeze the experiment's scoring contract at its recorded parent, even after
# the production mapper/weights are refactored. No production module is edited.
def frozen_module(filename):
    path = SCRIPTS / 'au_racing_engine' / filename
    source = subprocess.check_output(['git', 'show', f'{BASELINE_COMMIT}:{path.relative_to(ROOT)}'],
                                     cwd=ROOT, text=True)
    namespace = {'__name__': 'au_racing_engine._frozen', '__package__': 'au_racing_engine',
                 '__file__': str(path)}
    exec(compile(source, f'<frozen-{filename}>', 'exec'), namespace)
    return namespace


FROZEN_SCORING = frozen_module('scoring.py')
FROZEN_MAPPER = frozen_module('matrix_mapper.py')


def frozen_scorer(row):
    matrix = FROZEN_MAPPER['map_features_to_matrix_scores'](row['features'])
    core = sum(matrix[k] * w for k,w in FROZEN_SCORING['MATRIX_WEIGHTS'].items())
    return 60+(core-60)/FROZEN_SCORING['MATRIX_ABILITY_SCALE']+float(row.get('wet') or 0)+float(row.get('proven_class') or 0)


ev.default_scorer = frozen_scorer
ev.MATRIX_ABILITY_SCALE = FROZEN_SCORING['MATRIX_ABILITY_SCALE']


def eligible(engine, entry):
    target = engine.race_context.get('audit_date', '')
    date = str(entry.get('date') or '')
    return bool(target and date and date < target)


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise RuntimeError(f'Live method anchor changed: {old[:80]}')
    return source.replace(old, new, 1)


def form_methods():
    # Keep the experiment replayable after adopting candidate C in the worktree.
    # Only the form method changed numerically in this experiment; the scorer
    # verifies every reconstructed baseline leaf against the frozen dump.
    path = (SCRIPTS / 'au_racing_engine/engine_core.py').relative_to(ROOT)
    original = subprocess.check_output(['git', 'show', f'{BASELINE_COMMIT}:{path}'],
                                       cwd=ROOT, text=True)
    tree = ast.parse(original)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'RacingEngine')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_form_score')
    source = textwrap.dedent('\n'.join(original.splitlines()[method.lineno-1:method.end_lineno]))
    a = replace_once(source, '        race_score = base_pts * class_mult', '''        if _candidate_eligible(self, entry):
            median = parse_float(self._field_summary().get("prize_level_field_median"))
            prize = parse_float(entry.get("prize"))
            if median is not None and prize and prize > 0:
                class_mult = max(.7, min(1.2, 1 + CLASS_PRIZE_K * (math.log10(prize) - median) / 60))
        race_score = base_pts * class_mult''')
    a = replace_once(a, 'own_level = horse_prize_level(self.facts_section)', 'own_level = None')
    anchor = '        if i == 0: decay = 1.0'
    c = replace_once(source, anchor, '''        if _candidate_eligible(self, entry) and place == 1 and field_size and field_size >= 2:
            base_pts = 60 + 40 * (field_size - 1) / (field_size + 1)
''' + anchor)
    e = replace_once(source, anchor, '''        if (_candidate_eligible(self, entry) and base_pts > 60
            and "synthetic" in str(entry.get("going", "")).lower()
            and any(x in str(self._today_going()).lower() for x in ("good", "soft", "heavy", "firm"))):
            base_pts = 60 + .5 * (base_pts - 60)
''' + anchor)
    output = {}
    for name, src in [('baseline', source), ('A', a), ('C', c), ('E', e)]:
        namespace = {**ec.__dict__, '_candidate_eligible': eligible}
        exec(compile(src, f'<offline-form-{name}>', 'exec'), namespace)
        output[name] = namespace['_form_score']
    return output


def final_form(score, class_score):
    score = ec.clip_score(score)
    if score >= 72 and class_score < 60:
        score -= 4
    return round(score, 2)


def final_fit(score, class_score):
    score = ec.clip_score(score)
    if score >= 72 and class_score < 58:
        score -= 3
    return round(score, 2)


def enrich(race, path, methods, audit):
    logic = json.loads(path.read_text())
    horses = logic['horses']
    context = dict(logic['race_analysis'])
    context['field_summary'] = _build_field_summary(horses)
    context['field_horse_names'] = [h.get('horse_name') for h in horses.values()]
    context['audit_date'] = race['date']
    race['going'] = context.get('track_condition', context.get('going', ''))
    for row in race['rows']:
        horse = dict(horses[str(row['n'])])
        horse.setdefault('horse_number', str(row['n']))
        engine = ec.RacingEngine(horse, context,
            facts_section=(horse.get('_data') or {}).get('facts_section', ''),
            facts_path=str(path.parent / f"{race['date']}_dummy.md"))
        cs = row['features']['class_score']
        old_form = final_form(methods['baseline'](engine)[0], cs)
        old_fit = final_fit(engine._jockey_horse_fit_score()[0], cs)
        if abs(old_form - row['features']['form_score']) > .011:
            raise RuntimeError(f"form baseline mismatch {path} {row['n']}: {old_form}")
        if abs(old_fit - row['features']['jockey_horse_fit_score']) > .011:
            raise RuntimeError(f"fit baseline mismatch {path} {row['n']}: {old_fit}")
        row['audit'] = {'form_detail': engine.form_detail,
                        'fit_detail': engine.jt_fit_detail,
                        'entries': engine._official_entries()[:4],
                        'formline_support': engine._formline_support_summary()}
        for entry in engine._official_entries()[:4]:
            audit['historical_rows'] += 1
            if not eligible(engine, entry):
                audit['invalid_or_future_history_rows'] += 1
        row['candidate_features'] = {}
        for name, method in methods.items():
            if name == 'baseline':
                continue
            row['candidate_features'][name] = {'form_score': final_form(method(engine)[0], cs)}
        original = ec.FIT_MICRO_WEIGHTS
        try:
            ec.FIT_MICRO_WEIGHTS = {**original, 'trial_ok_bonus': 0., 'trial_ok_top_jt_bonus': 0.}
            fit = final_fit(engine._jockey_horse_fit_score()[0], cs)
        finally:
            ec.FIT_MICRO_WEIGHTS = original
        row['candidate_features']['B'] = {'jockey_horse_fit_score': fit}
        row['pure_formline'] = round(ec.clip_score(engine._formline_score()[0]), 2)
        row['audit']['today_going'] = engine._today_going()
        race['going'] = str(engine._today_going())


def scorer(name):
    def score(row):
        if name == 'D':
            overlay = float(row.get('wet') or 0) + float(row.get('proven_class') or 0)
            base_core = ev.default_scorer(row) - overlay
            return (60 + .97 * (base_core - 60)
                    + .03 * (row['pure_formline'] - 60) / ev.MATRIX_ABILITY_SCALE + overlay)
        return ev.default_scorer({**row, 'features': {
            **row['features'], **row['candidate_features'][name]}})
    return score


def delta_counts(races, candidate):
    base, cand = ev._counts(races, ev.default_scorer), ev._counts(races, candidate)
    return {key: cand[key] - base[key] for key in base}


def run(args):
    out = Path(args.output)
    cache = out.with_suffix('.enriched.json')
    if args.phase == 'build':
        races = ev.load_races(args.baseline)
        audit = {'historical_rows': 0, 'invalid_or_future_history_rows': 0}
        paths = {p.name: p for p in _corpus_meeting_dirs(ARCHIVE_ROOT)}
        methods = form_methods()
        for i, race in enumerate(races):
            enrich(race, paths[race['meeting']] / f"Race_{race['race']}_Logic.json", methods, audit)
            if i % 200 == 0:
                print(f'Enriched {i}/{len(races)}', flush=True)
        case_path = Path(args.case)
        case_logic = json.loads(case_path.read_text())
        case = {'meeting': case_path.parent.name, 'date': '2026-09-02', 'race': 3, 'rows': []}
        for n, h in case_logic['horses'].items():
            auto = h.get('python_auto') or {}
            if not auto.get('feature_scores'):
                raise RuntimeError('Case missing saved auto_analysis')
            case['rows'].append({'n': int(n), 'name': h['horse_name'],
                'features': auto['feature_scores'], 'ability': auto['ability_score'],
                'wet': auto.get('wet_form_feature', 0), 'proven_class': auto.get('proven_class_feature', 0)})
        enrich(case, case_path, methods, audit)
        cache.write_text(json.dumps({'races': races, 'case': case, 'audit': audit}, ensure_ascii=False))
        print(f'Saved {cache}', flush=True)
        return
    data = json.loads(cache.read_text())
    races = data['races']
    dev_i, terminal_i = ev.date_partitions(races)
    dev = [races[i] for i in dev_i]
    terminal = [races[i] for i in terminal_i]
    dates = sorted({r['date'] for r in dev})
    folds = [set(dates[len(dates)*k//5:len(dates)*(k+1)//5]) for k in range(5)]
    report = {'audit': data['audit'], 'sample_hash': hashlib.sha256(json.dumps(
        [(r['meeting'], r['race'], [(x['n'], x['pos']) for x in r['rows']]) for r in races],
        sort_keys=True).encode()).hexdigest(), 'baseline_sha256': hashlib.sha256(Path(args.baseline).read_bytes()).hexdigest(),
        'design': {'races': len(races), 'dev': len(dev), 'terminal': len(terminal),
        'dev_window': [dev[0]['date'], dev[-1]['date']],
        'terminal_window': [terminal[0]['date'], terminal[-1]['date']]},
        'baseline': ev.baseline_report(races), 'candidates': {}}
    bt = ev._pairs(dev, ev.default_scorer, True)
    for name in 'ABCDE':
        candidate = scorer(name)
        counts = delta_counts(dev, candidate)
        item = {'dev_delta_pp': counts,
                'dev_top5_auc_delta': ev._auc(ev._pairs(dev, candidate, True)) - ev._auc(bt),
                'folds': [delta_counts([r for r in dev if r['date'] in ds], candidate) for ds in folds],
                'changed_runners': sum(abs(candidate(x)-ev.default_scorer(x)) > .00001 for r in races for x in r['rows']),
                'dev_by_field': {label: delta_counts([r for r in dev if lo <= r['field'] <= hi], candidate)
                                 for lo, hi, label in ev.FIELD_BUCKETS},
                'case': sorted([{'n': x['n'], 'name': x['name'], 'baseline': ev.default_scorer(x),
                                'candidate': candidate(x)} for x in data['case']['rows']], key=lambda x: -x['candidate'])}
        item['dev_eligible'] = counts['gold'] >= 0 and counts['good_positional'] >= 0
        item['decision'] = 'PENDING_TERMINAL' if item['dev_eligible'] else 'REJECT_DEV_PRIMARY_REGRESSION'
        if name == 'D':
            item['leakage'] = 'FLAG: archived opponent summaries lack per-followup timestamps; no promotion'
        if args.phase == 'terminal' and item['dev_eligible'] and name != 'D':
            item['terminal_delta_pp'] = delta_counts(terminal, candidate)
            item['verdict'] = ev.verdict_dict(ev.compare(races, cand_scorer=candidate, label=name,
                leakage_audit_passed=data['audit']['invalid_or_future_history_rows'] == 0))
            evidence = ev.build_evaluation_input(domain='au', dates=[r['date'] for r in races],
                baseline_rows=ev._stage4_metric_rows(races, ev.default_scorer),
                candidate_rows=ev._stage4_metric_rows(races, candidate),
                leakage_audit_passed=data['audit']['invalid_or_future_history_rows'] == 0,
                ranking_metrics=('top3_capture_at5', 'mean_top3_model_rank',
                                 'competitive_recall_at5', 'ndcg_at5', 'top5_pairwise_auc'))
            item['paired_evidence'] = dataclasses.asdict(evidence)
            item['terminal_by_field'] = {label: delta_counts(
                [r for r in terminal if lo <= r['field'] <= hi], candidate)
                for lo, hi, label in ev.FIELD_BUCKETS}
        report['candidates'][name] = item
        print(name, item['decision'], {k: round(counts[k], 4) for k in ('gold', 'good_positional')}, flush=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(out, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', default='/tmp/au-matrix-feedback-baseline.json')
    parser.add_argument('--output', default='/tmp/au-matrix-feedback-eval.json')
    parser.add_argument('--case', default=str(ARCHIVE_ROOT / '2026-09-02 Warwick Farm Race 1-7/Race_3_Logic.json'))
    parser.add_argument('--phase', choices=['build', 'dev', 'terminal'], required=True)
    run(parser.parse_args())
