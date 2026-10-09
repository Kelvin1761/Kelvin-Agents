"""Offline correctness replay: apply only Facts deltas caused by the patch.

No result fields enter generation/scoring. Cached profiles are date-filtered;
this does not establish that mutable Logic inputs are immutable pre-off evidence.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.agents/scripts'))
sys.path.insert(0, str(ROOT / '.agents/skills/hkjc_racing/hkjc_wong_choi/scripts'))
import inject_hkjc_fact_anchors as candidate
import create_hkjc_logic_skeleton as skeleton


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('meeting', type=Path)
    ap.add_argument('output', type=Path)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    baseline = types.ModuleType('baseline_inject')
    baseline.__file__ = candidate.__file__
    source = subprocess.check_output(['git', 'show', 'HEAD:.agents/scripts/inject_hkjc_fact_anchors.py'], cwd=ROOT, text=True)
    exec(compile(source, baseline.__file__, 'exec'), baseline.__dict__)
    cache = json.loads((args.meeting / '.hkjc_cache/profile_cache.json').read_text())
    audit = []
    for path in sorted(args.meeting.glob('Race_*_Logic.json')):
        logic = json.loads(path.read_text())
        context = logic['race_analysis']
        number = context['race_number']
        facts = next(args.meeting.glob(f'* Race {number} Facts.md'))
        guide = next(args.meeting.glob(f'* Race {number} 賽績.md'))
        parsed = candidate.parse_hkjc_formguide(str(guide))
        by_number = {str(h['num']): h for h in parsed['horses']}
        header = skeleton.extract_race_header(facts.read_text())
        for no, h in logic['horses'].items():
            form = by_number[no]
            if form['name'] != h['horse_name']:
                raise ValueError(f'identity mismatch {number}/{no}')
            hid = h.get('hkjc_horse_id', '')
            cached = cache.get(hid) or cache.get(hid.rsplit('_', 1)[-1])
            if not cached or cached['data']['name'] != h['horse_name']:
                raise ValueError(f'profile identity missing {number}/{no}')
            profile = candidate.filter_profile_as_of(cached['data'], context['race_date'])
            generated = []
            for module in (baseline, candidate):
                block = module.generate_horse_block(
                    copy.deepcopy(form), context['venue'], int(str(context['distance']).rstrip('m')),
                    context['race_class'], copy.deepcopy(profile), race_num=number,
                    race_date=context['race_date'])
                generated.append(skeleton.build_horse_skeleton_from_facts(
                    block, str(facts), number, int(no), race_header=header)[0])
            changes = {}
            for key, value in generated[1].items():
                if key in {'_validation_nonce', 'python_auto', 'matrix', 'core_logic',
                           'interaction_matrix', 'base_rating', 'fine_tune', 'override',
                           'final_rating', 'advantages', 'disadvantages', 'underhorse',
                           'race_forgiveness', 'evidence_step_0_14'}:
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
            audit.append({'race': number, 'horse': no, 'name': h['horse_name'], 'changes': changes})
        (args.output / path.name).write_text(json.dumps(logic, ensure_ascii=False, indent=2))
    (args.output / 'alignment_delta.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2))
    env = dict(os.environ, WC_DISABLE_HKJC_PROFILE_ENRICH='1', WC_DISABLE_POST_SUCCESS_DEPLOY='1', PYTHONDONTWRITEBYTECODE='1')
    engine = ROOT / '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts/hkjc_auto_orchestrator.py'
    subprocess.run([sys.executable, str(engine), str(args.output)], env=env, check=True)
    print(f'Changed runners: {sum(bool(a["changes"]) for a in audit)}/{len(audit)}')


if __name__ == '__main__':
    main()
