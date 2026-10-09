"""Paired corpus replay for the HKJC history-alignment correctness fix.

Two arms, identical frozen inputs per meeting:
  baseline  — the meeting's own Race_*_Logic.json, scored by the baseline checkout.
  candidate — the same Logic, with only the Facts fields that the candidate
              inject_hkjc_fact_anchors.py generates differently (from the same
              formguide + pre-meeting profile cache) transferred in, scored by
              this checkout.

Runners whose profile identity cannot be proven (cache miss, name mismatch,
formguide/Logic name mismatch) abstain: their Logic is left unchanged in both
arms and they are listed in the audit. Nothing is silently dropped.

Results never enter generation. They are read only after both arms are scored.

usage: hkjc_history_alignment_corpus.py <baseline_checkout> <output_dir>
"""
import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import types
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.agents/scripts'))
sys.path.insert(0, str(ROOT / '.agents/skills/hkjc_racing/hkjc_wong_choi/scripts'))
sys.path.insert(0, str(ROOT / '.agents/skills/shared_racing'))
sys.path.insert(0, str(ROOT / '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'))
import inject_hkjc_fact_anchors as candidate  # noqa: E402
import create_hkjc_logic_skeleton as skeleton  # noqa: E402
import hkjc_auto_orchestrator as orch  # noqa: E402
from eval_metrics import race_metrics  # noqa: E402
from model_evaluation_decision import build_evaluation_input, evaluate_candidate  # noqa: E402

DATA_ROOT = Path(os.environ.get(
    'WONGCHOI_HK_DATA_ROOT',
    '/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing'))
SKIP_KEYS = {'_validation_nonce', 'python_auto', 'matrix', 'core_logic',
             'interaction_matrix', 'base_rating', 'fine_tune', 'override',
             'final_rating', 'advantages', 'disadvantages', 'underhorse',
             'race_forgiveness', 'evidence_step_0_14'}
DATE_RE = re.compile(r'\b(\d{2})/(\d{2})/(\d{4})\b')


def meetings():
    for path in sorted(DATA_ROOT.iterdir()):
        if not re.match(r'\d{4}-\d{2}-\d{2}_[A-Za-z]+$', path.name):
            continue
        if (list(path.glob('Race_*_Logic.json')) and list(path.glob('*全日賽果.json'))
                and (path / '.hkjc_cache/profile_cache.json').exists()):
            yield path


def baseline_module():
    module = types.ModuleType('baseline_inject')
    module.__file__ = candidate.__file__
    source = subprocess.check_output(
        ['git', 'show', 'HEAD:.agents/scripts/inject_hkjc_fact_anchors.py'], cwd=ROOT, text=True)
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


def future_dates(value, race_date):
    """Leakage audit: any dd/mm/yyyy on or after the race date in a transferred field."""
    cutoff = datetime.strptime(race_date, '%Y-%m-%d')
    found = []
    for d, m, y in DATE_RE.findall(json.dumps(value, ensure_ascii=False)):
        try:
            if datetime(int(y), int(m), int(d)) >= cutoff:
                found.append(f'{d}/{m}/{y}')
        except ValueError:
            continue
    return found


_CACHE_INDEX = None


def earlier_cache_profile(keys, meeting_date):
    """Latest profile for any of `keys` from a meeting cache dated strictly before
    `meeting_date` (fetched before this meeting, so entries are filtered as-of anyway)."""
    global _CACHE_INDEX
    if _CACHE_INDEX is None:
        _CACHE_INDEX = []
        for path in sorted(DATA_ROOT.glob('20*_*/.hkjc_cache/profile_cache.json')):
            try:
                _CACHE_INDEX.append((path.parent.parent.name[:10], json.loads(path.read_text())))
            except (OSError, ValueError):
                continue
    for date, cache in reversed(_CACHE_INDEX):
        if date >= meeting_date:
            continue
        for key in keys:
            if key and (cache.get(key) or cache.get(str(key).rsplit('_', 1)[-1])):
                return cache.get(key) or cache.get(str(key).rsplit('_', 1)[-1])
    return None


def build_candidate_meeting(meeting, out_dir, base):
    race_date = meeting.name[:10]
    cache = json.loads((meeting / '.hkjc_cache/profile_cache.json').read_text())
    audit = []
    for path in sorted(meeting.glob('Race_*_Logic.json')):
        logic = json.loads(path.read_text())
        context = logic.get('race_analysis', {})
        number = int(context.get('race_number') or re.search(r'Race_(\d+)_', path.name).group(1))
        facts = next(meeting.glob(f'* Race {number} Facts.md'), None)
        guide = next(meeting.glob(f'* Race {number} 賽績.md'), None)
        if not facts or not guide:
            audit.append({'race': number, 'abstain_race': 'missing Facts/賽績'})
            (out_dir / path.name).write_text(json.dumps(logic, ensure_ascii=False))
            continue
        try:
            parsed = candidate.parse_hkjc_formguide(str(guide))
        except ValueError as exc:
            audit.append({'race': number, 'abstain_race': f'formguide/racecard: {exc}'})
            (out_dir / path.name).write_text(json.dumps(logic, ensure_ascii=False))
            continue
        by_number = {str(h['num']): h for h in parsed['horses']}
        card = next(meeting.glob(f'* Race {number} 排位表.md'), None)
        card_info = orch._parse_racecard_meta(card.read_text(encoding='utf-8'))[1] if card else {}
        header = skeleton.extract_race_header(facts.read_text())
        venue = context.get('venue') or ('跑馬地' if 'HappyValley' in meeting.name else '沙田')
        distance = int(re.sub(r'\D', '', str(context.get('distance') or 0)) or 0)
        for no, h in logic['horses'].items():
            row = {'race': number, 'horse': no, 'name': h.get('horse_name')}
            form = by_number.get(no)
            # Identity: archived Logic mostly lacks hkjc_horse_id; the racecard has it.
            # The cached profile must still carry the same name.
            card_row = card_info.get(no) or {}
            cached = None
            for hid in (card_row.get('hkjc_horse_id'), card_row.get('horse_code'),
                        h.get('hkjc_horse_id'), (form or {}).get('brand_no')):
                if hid and (cache.get(hid) or cache.get(str(hid).rsplit('_', 1)[-1])):
                    cached = cache.get(hid) or cache.get(str(hid).rsplit('_', 1)[-1])
                    break
            if (not cached or cached['data'].get('name') != h.get('horse_name')):
                fallback = earlier_cache_profile(
                    (card_row.get('hkjc_horse_id'), card_row.get('horse_code'), h.get('hkjc_horse_id')),
                    race_date)
                if fallback and fallback['data'].get('name') == h.get('horse_name'):
                    cached = fallback
                    row['profile_source'] = 'earlier_meeting_cache'
            if not form or form['name'] != h.get('horse_name'):
                row['abstain'] = 'formguide identity'
            elif not cached or cached['data'].get('name') != h.get('horse_name'):
                row['abstain'] = 'profile identity'
            if 'abstain' in row:
                audit.append(row)
                continue
            profile = candidate.filter_profile_as_of(cached['data'], race_date)
            generated = []
            for module in (base, candidate):
                block = module.generate_horse_block(
                    copy.deepcopy(form), venue, distance, context.get('race_class', 'C4'),
                    copy.deepcopy(profile), race_num=number, race_date=race_date)
                generated.append(skeleton.build_horse_skeleton_from_facts(
                    block, str(facts), number, int(no), race_header=header)[0])
            changes = {}
            for key, value in generated[1].items():
                if key in SKIP_KEYS:
                    continue
                if key == '_data':
                    for field, new in value.items():
                        old = generated[0].get(key, {}).get(field)
                        if old != new:
                            changes[f'_data.{field}'] = {'old': old, 'new': new}
                            h.setdefault('_data', {})[field] = new
                elif generated[0].get(key) != value:
                    changes[key] = {'old': generated[0].get(key), 'new': value}
                    h[key] = value
            row['changes'] = changes
            row['future_dates'] = future_dates({k: v['new'] for k, v in changes.items()}, race_date)
            audit.append(row)
        (out_dir / path.name).write_text(json.dumps(logic, ensure_ascii=False))
    return audit


def score(engine_root, folder):
    env = dict(os.environ, WC_DISABLE_HKJC_PROFILE_ENRICH='1', WC_DISABLE_POST_SUCCESS_DEPLOY='1',
               PYTHONDONTWRITEBYTECODE='1', WONGCHOI_HK_DATA_ROOT=str(DATA_ROOT))
    engine = engine_root / '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_auto_orchestrator.py'
    log = folder / '_engine.log'
    with log.open('w') as handle:
        subprocess.run([sys.executable, str(engine), str(folder)], env=env,
                       stdout=handle, stderr=subprocess.STDOUT)
    # A race the engine refuses (e.g. SCORE-004 on an old Logic) is reported,
    # never compared: only races both arms scored enter the paired sample.
    text = log.read_text(encoding='utf-8', errors='replace')
    failed = set()
    if 'completed with failed races' in text:
        tail = text.split('completed with failed races', 1)[1]
        failed = {int(n) for n in re.findall(r'Race_(\d+)_Logic\.json', tail)}
    return failed


def ranks(folder):
    import csv
    out = {}
    for row in csv.DictReader((folder / 'HKJC_Auto_Scoring.csv').open(encoding='utf-8')):
        out.setdefault(int(row['race_number']), []).append((int(row['rank']), row['horse_number']))
    return {race: [h for _, h in sorted(rows)] for race, rows in out.items()}


def results(meeting):
    data = json.loads(next(meeting.glob('*全日賽果.json')).read_text())
    out = {}
    for race, payload in data.items():
        pos = {}
        for row in payload.get('results', []):
            m = re.match(r'(\d+)', str(row.get('pos', '')))
            if m:
                pos[str(row['horse_no'])] = int(m.group(1))
        if pos:
            out[int(race)] = pos
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('baseline_checkout', type=Path)
    ap.add_argument('output', type=Path)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    base = baseline_module()
    dates, venues, sizes, base_rows, cand_rows, audit = [], [], [], [], [], []
    for meeting in meetings():
        print(f'== {meeting.name}', flush=True)
        b_dir, c_dir = args.output / 'baseline' / meeting.name, args.output / 'candidate' / meeting.name
        b_dir.mkdir(parents=True)
        c_dir.mkdir(parents=True)
        for path in meeting.glob('Race_*_Logic.json'):
            shutil.copy2(path, b_dir / path.name)
        meeting_audit = build_candidate_meeting(meeting, c_dir, base)
        for row in meeting_audit:
            row['meeting'] = meeting.name
        audit.extend(meeting_audit)
        b_failed = score(args.baseline_checkout, b_dir)
        c_failed = score(ROOT, c_dir)
        for race in sorted(b_failed | c_failed):
            audit.append({'meeting': meeting.name, 'race': race, 'engine_failed':
                          [arm for arm, f in (('baseline', b_failed), ('candidate', c_failed)) if race in f]})
        b_rank, c_rank, res = ranks(b_dir), ranks(c_dir), results(meeting)
        for race in sorted((set(b_rank) & set(c_rank) & set(res)) - b_failed - c_failed):
            pos = res[race]
            top3 = [h for h, p in pos.items() if p <= 3]
            rows = []
            for picks in (b_rank[race], c_rank[race]):
                picks = [h for h in picks if h in pos]
                m = race_metrics(picks, top3, actual_pos=pos, field_size=len(pos))
                m['mean_top3_model_rank'] = m.get('top3_mean_model_rank')
                rows.append(m)
            dates.append(meeting.name[:10])
            venues.append('HV' if 'HappyValley' in meeting.name else 'ST')
            sizes.append(len(pos))
            base_rows.append(rows[0])
            cand_rows.append(rows[1])
            if b_rank[race] != c_rank[race]:
                audit.append({'meeting': meeting.name, 'race': race, 'rank_changed': True,
                              'baseline': b_rank[race][:6], 'candidate': c_rank[race][:6]})

    leaks = [a for a in audit if a.get('future_dates')]
    evidence = build_evaluation_input(
        domain='hkjc', dates=dates, baseline_rows=base_rows, candidate_rows=cand_rows,
        leakage_audit_passed=not leaks,
        ranking_metrics=('top3_capture_at5', 'ndcg_at5', 'competitive_recall_at5',
                         'mean_top3_model_rank'))
    verdict = evaluate_candidate(evidence)

    def mean(rows, key, idx):
        vals = [float(rows[i][key]) for i in idx if rows[i].get(key) is not None]
        return sum(vals) / len(vals) if vals else None
    cohorts = {}
    for name, idx in {
        'HV': [i for i, v in enumerate(venues) if v == 'HV'],
        'ST': [i for i, v in enumerate(venues) if v == 'ST'],
        'field<=10': [i for i, s in enumerate(sizes) if s <= 10],
        'field>=11': [i for i, s in enumerate(sizes) if s >= 11],
    }.items():
        cohorts[name] = {'races': len(idx), **{
            k: {'baseline': mean(base_rows, k, idx), 'candidate': mean(cand_rows, k, idx)}
            for k in ('gold', 'good_positional', 'top3_capture_at5')}}
    runners = [a for a in audit if 'horse' in a]
    summary = {
        'meetings': len(set(dates)), 'races': len(dates),
        'runners': len(runners),
        'runners_changed': sum(bool(a.get('changes')) for a in runners),
        'runners_abstained': {r: sum(a.get('abstain') == r for a in runners)
                              for r in ('formguide identity', 'profile identity')},
        'races_abstained': [a for a in audit if 'abstain_race' in a],
        'races_rank_changed': sum(bool(a.get('rank_changed')) for a in audit),
        'races_engine_failed': [a for a in audit if 'engine_failed' in a],
        'leakage_rows': leaks,
        'cohorts': cohorts,
        'verdict': verdict,
    }
    (args.output / 'audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=1, default=str))
    (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({k: v for k, v in summary.items() if k != 'races_abstained'},
                     ensure_ascii=False, indent=1, default=str))


if __name__ == '__main__':
    main()
