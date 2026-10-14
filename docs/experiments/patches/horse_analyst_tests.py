"""Four pre-registered, read-only AU research tests; no production imports patched.

Build candidate inputs from strictly earlier formal runs. Later form contributes
only positioning diagnostic labels. Canonical au_eval owns ranking evaluation.
"""
import argparse
import copy
import hashlib
import json
import math
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / '.agents/skills/au_racing/au_wong_choi_auto/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))
import au_eval as ev  # noqa: E402
import au_speed_rebuild_probe as history  # noqa: E402
from au_racing_engine.scoring import wet_form_feature, _parse_wet_record  # noqa: E402

CAREER = re.compile(r'^Career:\s+(\d+):', re.M)


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def f800(run):
    if (run['p800'] is not None and run['starters'] is not None
            and 1 <= run['p800'] <= run['starters'] and run['starters'] > 1):
        return (run['p800'] - 1) / (run['starters'] - 1)
    return None


def inputs(runs, target, career=None, same_day_or_future=False):
    prior = sorted([r for r in runs if r['date'] < target],
                   key=lambda r: r['date'], reverse=True)
    values = [v for v in (f800(r) for r in prior) if v is not None][:6]
    out = {'history_count': len(prior), 'pace_n': len(values), 'career': career}
    if values:
        out['pace_mean'] = st.mean(values)
    if len(values) >= 2:
        out['pace_confidence'] = (len(values) / (len(values) + 4)
                                  * (1 - min(1, st.pstdev(values) / .5)))
    boundary = (date.fromisoformat(target) - timedelta(days=45)).isoformat()
    # Career counts can be post-race refreshed. Never use them as a completeness
    # certificate where a present/future run is visible in this snapshot.
    # Metadata career counts can be refreshed after the archived race. Boundary
    # coverage must depend only on prior dated runs, never future-row presence.
    covered = bool(prior) and prior[-1]['date'] <= boundary
    out['window_boundary_observed'] = bool(covered)
    if covered:
        recent = [r for r in prior if r['date'] >= boundary]
        out['negative_metres'] = -sum(r['dist'] for r in recent)
        out['negative_starts'] = -len(recent)
        dates = sorted({r['date'] for r in recent})
        gaps = [(date.fromisoformat(b) - date.fromisoformat(a)).days
                for a, b in zip(dates, dates[1:])]
        out['minimum_recovery_days'] = min(gaps) if gaps else None
    return out


def zs(values):
    have = [v for v in values if v is not None]
    if len(have) < 2 or st.pstdev(have) == 0:
        return [0.] * len(values)
    mu, sd = st.mean(have), st.pstdev(have)
    return [0. if v is None else (v - mu) / sd for v in values]


def rho(pairs):
    if len(pairs) < 3:
        return None
    from scipy.stats import spearmanr
    value = float(spearmanr([x for x, _ in pairs], [y for _, y in pairs]).statistic)
    return value if math.isfinite(value) else None


def build(leaves, output):
    raw = json.loads(leaves.read_text())['races']
    mi = history.meeting_index()
    sources, blocks, targets, exclusions = {}, {}, defaultdict(set), Counter()
    for race in raw:
        md = mi.get(race['meeting'])
        fg = next(iter(md.glob(f"* Race {race['race']} Formguide.md")), None) if md else None
        if not fg:
            exclusions['no_formguide'] += 1
            continue
        sources[str(fg)] = fingerprint(fg)
        text = fg.read_text(encoding='utf-8', errors='replace')
        heads = list(history.HORSE.finditer(text))
        named = {}
        for i, head in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            block = text[head.end():end]
            runs = history.parse_runs(block)
            # The reused parser extracts date, venue and distance; attach race
            # number to deduplicate exact race identities, not similar outcomes.
            formal = []
            for match in history.RUN.finditer(block):
                parsed = history.parse_runs(match.group(0))
                if parsed:
                    item = parsed[0]
                    item['race'] = int(match.group('race'))
                    formal.append(item)
            unique = {}
            for run in formal:
                key = (run['date'], history.norm(run['venue']), run['race'])
                unique.setdefault(key, run)
            runs = list(unique.values())
            nm = history.norm(head.group(2))
            for run in runs:
                v = f800(run)
                if v is not None:
                    targets[(nm, run['date'])].add((history.norm(run['venue']),
                                                  run['race'], round(v, 9)))
            count = CAREER.search(block)
            same_future = any(r['date'] >= race['date'] for r in runs)
            named[nm] = inputs(runs, race['date'], int(count.group(1)) if count else None,
                               same_future)
        blocks[(race['meeting'], race['race'])] = named

    races = []
    for race in raw:
        if race['date'] < '2026-08-05':
            exclusions['pre_clean_date'] += 1
            continue
        rows = race['rows']
        if sorted(r['pos'] for r in rows) != list(range(1, len(rows) + 1)):
            exclusions['incomplete_or_deadheat_positions'] += 1
            continue
        if len({history.norm(r['name']) for r in rows}) != len(rows):
            exclusions['duplicate_runner_identity'] += 1
            continue
        md = mi[race['meeting']]
        lp = md / f"Race_{race['race']}_Logic.json"
        sources[str(lp)] = fingerprint(lp)
        logic = json.loads(lp.read_text())
        ctx = logic.get('race_analysis') or {}
        race['going'] = ctx.get('going') or (ctx.get('meeting_intelligence') or {}).get('going') or ''
        race['class'] = ctx.get('race_class') or ''
        horses = {history.norm(h.get('horse_name', '')): h for h in logic['horses'].values()}
        for row in rows:
            nm = history.norm(row['name'])
            row['_ha'] = dict(blocks.get((race['meeting'], race['race']), {}).get(nm, {}))
            target_set = targets.get((nm, race['date']), set())
            if len(target_set) == 1:
                target = next(iter(target_set))
                # Race number must agree, even if venue spelling is abbreviated.
                if target[1] == race['race']:
                    row['_diagnostic_f800'] = target[2]
            elif len(target_set) > 1:
                exclusions['ambiguous_position_label_rows'] += 1
            data = (horses.get(nm, {}).get('_data') or {})
            row['_ha']['wet_scenarios'] = {
                g: wet_form_feature(g, data.get('going_stats_line'))
                for g in ('Good 4', 'Soft 6', 'Heavy 8')}
            row['_ha']['wet_record_starts'] = _parse_wet_record(
                'Soft 6', data.get('going_stats_line'))[0]
            row['_ha']['career'] = data.get('career_starts', row['_ha'].get('career'))
        races.append(race)
    source_state = {str(p): fingerprint(p) for p in
                    sorted((SCRIPTS / 'au_racing_engine').glob('*.py'))}
    payload = {'races': races, 'exclusions': dict(exclusions), 'source_hashes': sources,
               'engine_hashes': source_state, 'leaves_sha256': fingerprint(leaves)}
    output.write_text(json.dumps(payload))
    print(json.dumps({'races': len(races), 'exclusions': exclusions}, default=dict), flush=True)


def scorer(k, feature):
    return lambda row: ev.default_scorer(row) + k * row['_ha_z'][feature]


def diagnostics(races):
    pairs, errors = [], []
    for race in races:
        for row in race['rows']:
            h = row['_ha']
            if 'pace_confidence' in h and '_diagnostic_f800' in row:
                error = abs(h['pace_mean'] - row['_diagnostic_f800'])
                pairs.append((h['pace_confidence'], error))
                errors.append(error)
    return {'labelled_runners': len(pairs), 'confidence_error_rho': rho(pairs),
            'mean_position_error': st.mean(errors) if errors else None}


def cohort_rows(races, candidate):
    groups = defaultdict(list)
    for race in races:
        n = len(race['rows'])
        field = '<=8' if n <= 8 else '9-10' if n <= 10 else '11-12' if n <= 12 else '13+'
        groups['field:' + field].append(race)
        groups['venue:' + re.sub(r'^\d{4}-\d{2}-\d{2} | Race.*$', '', race['meeting'])].append(race)
        groups['going:' + race['going']].append(race)
        groups['class:' + ('maiden' if re.search(r'maiden|\bmdn\b', race['class'], re.I) else 'other')].append(race)
        rank1 = max(race['rows'], key=ev.default_scorer)
        career = rank1['_ha'].get('career')
        groups['top_pick_career:' + ('missing' if career is None else '<=4' if career <= 4 else '>4')].append(race)
        sp = rank1.get('sp')
        bucket = 'missing' if sp is None else '<=3' if sp <= 3 else '3-10' if sp <= 10 else '10-21' if sp <= 21 else '>21'
        groups['top_pick_sp:' + bucket].append(race)
    out = {}
    for key, group in groups.items():
        b, c = ev._counts(group, ev.default_scorer), ev._counts(group, candidate)
        detail = {'races': len(group), 'gold_delta_pp': c['gold'] - b['gold'],
                  'good_delta_pp': c['good_positional'] - b['good_positional']}
        if len(group) >= 30:
            bm = ev._stage4_metric_rows(group, ev.default_scorer)
            cm = ev._stage4_metric_rows(group, candidate)
            import numpy as np
            rng = np.random.default_rng(7)
            ix = rng.integers(0, len(group), (2000, len(group)))
            for metric in ('gold', 'good_positional'):
                values = np.array([y[metric] - x[metric] for x, y in zip(bm, cm)])
                detail[metric + '_ci_pp'] = (np.quantile(values[ix].mean(axis=1), [.025, .975])*100).tolist()
        out[key] = detail
    return out


def test(data, out):
    payload = json.loads(data.read_text())
    races = payload['races']
    # Detect concurrent code changes; never silently compare a different engine.
    if any(fingerprint(p) != sha for p, sha in payload['engine_hashes'].items()):
        raise RuntimeError('Engine source changed during research; rebuild baseline')
    mismatch = max(abs(ev.default_scorer(row) - row['ability'])
                   for race in races for row in race['rows'])
    if mismatch > .0002:
        raise RuntimeError(f'Current scorer does not reproduce baseline: {mismatch}')
    di, ti = ev.date_partitions(races, ev.HOLDOUT)
    dev, terminal = [races[i] for i in di], [races[i] for i in ti]
    days = sorted({r['date'] for r in dev})
    folds = [[r for r in dev if r['date'] in set(days[round(i * len(days)/5):round((i+1)*len(days)/5)])]
             for i in range(5)]
    baseline = ev.baseline_report(races)
    result = {'baseline': baseline, 'eligibility': payload['exclusions'],
              'replica_max_error': mismatch, 'dev_dates': [days[0], days[-1]],
              'terminal_dates': [terminal[0]['date'], terminal[-1]['date']],
              'diagnostic_dev': diagnostics(dev),
              'diagnostic_folds': [diagnostics(f) for f in folds], 'candidates': {}}
    result['coverage'] = {f: sum(f in row['_ha'] for r in races for row in r['rows'])
                          for f in ('pace_mean', 'pace_confidence', 'negative_metres', 'negative_starts')}
    result['total_runners'] = sum(len(r['rows']) for r in races)
    bcounts = ev._counts(dev, ev.default_scorer)
    bauc = ev._auc(ev._pairs(dev, ev.default_scorer, True))
    for feature in ('pace_confidence', 'negative_metres', 'negative_starts'):
        for race in races:
            zz = zs([r['_ha'].get(feature) for r in race['rows']])
            for row, z in zip(race['rows'], zz):
                row.setdefault('_ha_z', {})[feature] = z
        grid, eligible = [], []
        for k in (.5, 1., 1.5, 2., 3.):
            cand = scorer(k, feature)
            cc = ev._counts(dev, cand)
            fold_passes = sum(all(ev._counts(f, cand)[metric] >= ev._counts(f, ev.default_scorer)[metric]
                                  for metric in ('gold', 'good_positional')) for f in folds)
            aucdelta = ev._auc(ev._pairs(dev, cand, True)) - bauc
            gd, gg = cc['gold'] - bcounts['gold'], cc['good_positional'] - bcounts['good_positional']
            ok = gd >= 0 and gg >= 0 and aucdelta > 0 and fold_passes >= 3
            grid.append({'k': k, 'gold_delta_pp': gd, 'good_delta_pp': gg,
                         'auc_delta': aucdelta, 'fold_passes': fold_passes, 'eligible': ok})
            if ok:
                eligible.append(k)
        item = {'grid': grid, 'verdict': 'REJECT_DEV', 'terminal_opened': False}
        if eligible:
            k = st.median(eligible)
            cand = scorer(k, feature)
            verdict = ev.compare(races, ev.default_scorer, cand,
                                 label=f'{feature} k={k}', leakage_audit_passed=True)
            item.update(k=k, verdict=verdict.stage4_verdict, terminal_opened=True,
                        canonical=ev.verdict_dict(verdict),
                        terminal_cohorts=cohort_rows(terminal, cand))
        result['candidates'][feature] = item
        print(feature, json.dumps(item), flush=True)

    sensitivity = []
    swaps = 0
    for race in races:
        ranked = sorted(race['rows'], key=lambda row: -ev.default_scorer(row))
        top4 = {r['n'] for r in ranked[:4]}
        wet_covered = sum(r['_ha'].get('wet_record_starts', 0) > 0 for r in ranked)
        informative = wet_covered >= .7 * len(ranked)
        stable1, stable4 = True, True
        for going in ('Good 4', 'Soft 6', 'Heavy 8'):
            scenario = sorted(ranked, key=lambda r: -(ev.default_scorer(r) - r['wet']
                                                      + r['_ha']['wet_scenarios'][going]))
            stable1 &= scenario[0]['n'] == ranked[0]['n']
            stable4 &= {r['n'] for r in scenario[:4]} == top4
        known = [r for r in ranked if 'pace_mean' in r['_ha']]
        leader_changed = None
        if len(known) >= .7 * len(ranked):
            others = [r for r in known if r['n'] != ranked[0]['n']]
            leader = min(others, key=lambda r: r['_ha']['pace_mean']) if others else None
            leader_changed = bool(leader and leader in ranked[:4])
        actual3 = {r['n'] for r in ranked if r['pos'] <= 3}
        sensitivity.append({'date': race['date'], 'stable_top1': stable1,
                            'stable_top4': stable4, 'wet_informative': informative,
                            'leader_removed_top4_changed': leader_changed,
                            'gold': actual3 <= top4,
                            'good': all(r['pos'] <= 3 for r in ranked[:2])})
        for row in ranked:
            row['_diverse_score'] = ev.default_scorer(row)
        if len(ranked) >= 5:
            styles = [r['_ha'].get('pace_mean') for r in ranked[:5]]
            if (all(v is not None for v in styles)
                    and len({v < .5 for v in styles[:4]}) == 1
                    and (styles[4] < .5) != (styles[0] < .5)
                    and ev.default_scorer(ranked[3]) - ev.default_scorer(ranked[4]) <= 2):
                ranked[3]['_diverse_score'], ranked[4]['_diverse_score'] = (
                    ranked[4]['_diverse_score'], ranked[3]['_diverse_score'])
                swaps += 1
    result['sensitivity'] = {}
    for name, indices in [('dev', di), ('terminal', ti)]:
        rows = [sensitivity[i] for i in indices]
        counts = {}
        for key in ('stable_top1', 'stable_top4', 'leader_removed_top4_changed'):
            groups = {}
            for value in (True, False):
                group = [r for r in rows if r[key] is value and
                         (r['wet_informative'] or key == 'leader_removed_top4_changed')]
                groups[str(value)] = {'races': len(group),
                                      'gold_pct': 100*st.mean(r['gold'] for r in group) if group else None,
                                      'good_pct': 100*st.mean(r['good'] for r in group) if group else None}
            counts[key] = groups
        result['sensitivity'][name] = counts
        result['sensitivity'][name]['wet_informative_races'] = sum(r['wet_informative'] for r in rows)
    result['sensitivity_scope'] = 'Wet overlay only; hypothetical removal changes set membership by construction. Not a full scenario engine or predicted scratching.'
    diversity = lambda row: row['_diverse_score']
    cc = ev._counts(dev, diversity)
    dg, gg = cc['gold'] - bcounts['gold'], cc['good_positional'] - bcounts['good_positional']
    diversity_auc_delta = ev._auc(ev._pairs(dev, diversity, True)) - bauc
    diversity_folds = sum(all(ev._counts(f, diversity)[metric] >= ev._counts(f, ev.default_scorer)[metric]
                              for metric in ('gold', 'good_positional')) for f in folds)
    diagnostic = result['diagnostic_dev']['confidence_error_rho']
    prerequisite = (diagnostic is not None and diagnostic < 0 and
                    sum((x['confidence_error_rho'] or 0) < 0 for x in result['diagnostic_folds']) >= 3)
    item = {'swapped_races': swaps, 'dev_gold_delta_pp': dg, 'dev_good_delta_pp': gg,
            'dev_auc_delta': diversity_auc_delta, 'fold_passes': diversity_folds,
            'pace_prerequisite': prerequisite, 'terminal_opened': False,
            'verdict': 'REJECT_PREREQUISITE' if not prerequisite else 'REJECT_DEV'}
    if prerequisite and dg >= 0 and gg >= 0 and diversity_auc_delta > 0 and diversity_folds >= 3:
        v = ev.compare(races, ev.default_scorer, diversity, label='fixed fourth/fifth pace diversity',
                       leakage_audit_passed=True)
        item.update(verdict=v.stage4_verdict, terminal_opened=True,
                    canonical=ev.verdict_dict(v), terminal_cohorts=cohort_rows(terminal, diversity))
    result['candidates']['top4_diversity'] = item
    result['diagnostic_terminal'] = diagnostics(terminal)
    result['dataset_sha256'] = fingerprint(data)
    out.write_text(json.dumps(result, indent=2))
    print('completed', out, flush=True)


def supplement(data, out):
    """Diagnostic uncertainty/field-size controls and outcome-blind runtime stress.

    This follows the locked ranking test; it neither tunes nor creates a scorer.
    """
    import numpy as np
    races = json.loads(data.read_text())['races']
    di, ti = ev.date_partitions(races, ev.HOLDOUT)
    dev = [races[i] for i in di]
    values = [row['_ha']['pace_confidence'] for race in dev for row in race['rows']
              if 'pace_confidence' in row['_ha'] and '_diagnostic_f800' in row]
    threshold = st.median(values)
    output = {'confidence_threshold_dev_median': threshold,
              'diagnostic_only_no_scoring_change': True, 'splits': {}}
    for split, indices in [('dev', di), ('terminal', ti)]:
        sums, strata = [], defaultdict(list)
        for index in indices:
            race = races[index]
            agg = [0., 0., 0., 0.]
            for row in race['rows']:
                h = row['_ha']
                if 'pace_confidence' in h and '_diagnostic_f800' in row:
                    error = abs(h['pace_mean'] - row['_diagnostic_f800'])
                    side = 0 if h['pace_confidence'] >= threshold else 2
                    agg[side] += error
                    agg[side+1] += 1
            if agg[1]+agg[3]:
                sums.append(agg)
            if sum(r['_ha'].get('wet_record_starts', 0) > 0 for r in race['rows']) < .7*len(race['rows']):
                continue
            ranked = sorted(race['rows'], key=lambda r: -ev.default_scorer(r))
            ids = {r['n'] for r in ranked[:4]}
            stable = all({r['n'] for r in sorted(ranked, key=lambda r: -(
                ev.default_scorer(r)-r['wet']+r['_ha']['wet_scenarios'][g]))[:4]} == ids
                         for g in ('Good 4', 'Soft 6', 'Heavy 8'))
            n = len(ranked)
            field = '<=8' if n <= 8 else '9-10' if n <= 10 else '11-12' if n <= 12 else '13+'
            gold = {r['n'] for r in ranked if r['pos'] <= 3} <= ids
            good = all(r['pos'] <= 3 for r in ranked[:2])
            strata[field].append((stable, gold, good))
        arr = np.array(sums)
        pooled = arr.sum(axis=0)
        rng = np.random.default_rng(7)
        ix = rng.integers(0, len(arr), (2000, len(arr)))
        boots = arr[ix].sum(axis=1)
        valid = (boots[:, 1] > 0) & (boots[:, 3] > 0)
        diff = boots[valid, 0]/boots[valid, 1] - boots[valid, 2]/boots[valid, 3]
        result = {'labelled_races': len(arr), 'high_n': int(pooled[1]), 'low_n': int(pooled[3]),
                  'high_error': pooled[0]/pooled[1], 'low_error': pooled[2]/pooled[3],
                  'high_minus_low_ci': np.quantile(diff, [.025, .975]).tolist()}
        field_rows, adjusted = {}, {'gold': [], 'good': []}
        for field, rows in strata.items():
            a, b = [r for r in rows if r[0]], [r for r in rows if not r[0]]
            detail = {'stable_n': len(a), 'unstable_n': len(b)}
            if a and b:
                for metric, col in [('gold', 1), ('good', 2)]:
                    delta = st.mean(r[col] for r in a) - st.mean(r[col] for r in b)
                    detail[metric + '_stable_minus_unstable_pp'] = 100*delta
                    adjusted[metric].append((len(rows), delta))
            field_rows[field] = detail
        result['sensitivity_by_field'] = field_rows
        result['field_standardized_sensitivity_delta_pp'] = {
            m: 100*sum(w*d for w,d in pairs)/sum(w for w,_ in pairs)
            if pairs else None for m,pairs in adjusted.items()}
        # Diagnostic group comparison, not a paired model-improvement interval.
        weights, bootstrap_fields = [], []
        for rows in strata.values():
            values = np.array(rows, dtype=float)
            if not (values[:, 0].any() and (values[:, 0] == 0).any()):
                continue
            ix = rng.integers(0, len(values), (2000, len(values)))
            sample = values[ix]
            stable = sample[:, :, 0]
            ns, nu = stable.sum(axis=1), (1-stable).sum(axis=1)
            rates = []
            for col in (1, 2):
                rates.append(np.divide((stable*sample[:, :, col]).sum(axis=1), ns,
                                       out=np.full(2000, np.nan), where=ns > 0)
                             - np.divide(((1-stable)*sample[:, :, col]).sum(axis=1), nu,
                                         out=np.full(2000, np.nan), where=nu > 0))
            weights.append(len(rows))
            bootstrap_fields.append(np.array(rates))
        if bootstrap_fields:
            boot = sum(w*v for w,v in zip(weights, bootstrap_fields))/sum(weights)
            result['field_standardized_sensitivity_ci_pp'] = {
                metric: (np.nanquantile(boot[i], [.025, .975])*100).tolist()
                for i, metric in enumerate(('gold', 'good'))}
        output['splits'][split] = result

    # Outcome-blind mechanical sample: 16 lowest hash identities. Rebuild the
    # full engine under three going conditions and one hypothetical removal.
    from au_auto_orchestrator import _build_field_summary
    from au_racing_engine.engine_core import (RacingEngine, backfill_pf_metrics,
                                               refresh_pf_own_l600, backfill_prize_column)
    mi = history.meeting_index()
    sample = sorted(races, key=lambda r: hashlib.sha256(
        f"{r['meeting']}|{r['race']}".encode()).hexdigest())[:16]
    full = []
    for race in sample:
        md = mi[race['meeting']]
        lp = md/f"Race_{race['race']}_Logic.json"
        logic = json.loads(lp.read_text())
        fp = md/f"{race['date'][5:]} Race {race['race']} Facts.md"
        backfill_pf_metrics(logic, fp)
        refresh_pf_own_l600(logic, fp)
        backfill_prize_column(logic, md, race['race'], race['date'])

        def runtime(going=None, remove=None):
            horses = copy.deepcopy(logic['horses'])
            if remove is not None:
                horses.pop(str(remove), None)
            ctx = copy.deepcopy(logic['race_analysis'])
            if going:
                ctx['going'] = going
                ctx.setdefault('meeting_intelligence', {})['going'] = going
                ctx.setdefault('speed_map', {})['going'] = going
            # Remove known scratched leader from the map as well as field data.
            if remove is not None:
                for key in ('leaders', 'pressers', 'on_pace', 'mid_pack', 'closers', 'unclassified'):
                    sm = ctx.get('speed_map') or {}
                    sm[key] = [n for n in sm.get(key, []) if str(n) != str(remove)]
            ctx['field_summary'] = _build_field_summary(horses)
            ctx['field_horse_names'] = [h.get('horse_name') for h in horses.values()]
            scores = []
            for row in race['rows']:
                if row['n'] == remove:
                    continue
                hd = dict(horses[str(row['n'])])
                hd.setdefault('horse_number', row['n'])
                e = RacingEngine(hd, ctx, facts_section=(hd.get('_data') or {}).get('facts_section', ''),
                                 facts_path=str(md/f"{race['date']}_dummy.md"))
                scores.append((e.analyze_horse()['ability_score'], row['n']))
            return [n for _, n in sorted(scores, key=lambda pair: -pair[0])]

        baseline = runtime()
        ranked = sorted(race['rows'], key=lambda r: -ev.default_scorer(r))
        known = [r for r in ranked if 'pace_mean' in r['_ha'] and r['n'] != baseline[0]]
        leader = min(known, key=lambda r:r['_ha']['pace_mean'])['n'] if known else None
        removal = runtime(remove=leader) if leader is not None else None
        expected = [n for n in baseline if n != leader]
        full.append({'meeting': race['meeting'], 'race': race['race'], 'baseline_top4': baseline[:4],
                     'going_top4': {g: runtime(g)[:4] for g in ('Good 4', 'Soft 6', 'Heavy 8')},
                     'removed_runner': leader, 'removed_top4': removal[:4] if removal else None,
                     'removal_reranks_remaining': removal != expected if removal else None})
    output['runtime_stress_sample'] = full
    output['dataset_sha256'] = fingerprint(data)
    out.write_text(json.dumps(output, indent=2))
    print('supplement complete', out, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['build', 'test', 'supplement'])
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'build':
        build(args.data, args.out)
    elif args.mode == 'test':
        test(args.data, args.out)
    else:
        supplement(args.data, args.out)
