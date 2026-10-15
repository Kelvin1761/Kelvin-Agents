#!/usr/bin/env python3
"""Freeze EXP-08's last chronological R1 profile; capture research-only shadows.

This does not certify historical availability or schedule any future execution.
Only consumes captured pre-race auto scores; never reads result positions/prices.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from au_neutral_speed_20261015 import ROOT, DIMS, MATRIX_WEIGHTS
from au_racing_engine.full_time_speed import MODEL_VERSION, read_bundle
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores
from au_racing_engine.scoring import compose_matrix_score

SYDNEY = ZoneInfo('Australia/Sydney')
ENGINE = ROOT / '.agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine'


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def fingerprint():
    files = {str(path.relative_to(ENGINE)): path for path in sorted(ENGINE.rglob('*.py'))}
    files['@shadow_script'] = Path(__file__).resolve()
    files['@research_input_helper'] = Path(__file__).with_name('au_neutral_speed_20261015.py')
    return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()}


def stamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('timezone required')
    return result


def freeze(results_path, now):
    report = json.loads(results_path.read_text())
    # Last chronological profile, never max test performance or latest accepted search.
    last = report['windows'][-1]
    selected = last['arms']['R1']
    if selected['fallback'] is not None:
        raise ValueError('last R1 window has no accepted frozen profile')
    config = {'schema': 'au-speed-forward-v1', 'research_only': True,
        'model': 'EXP08_LAST_CHRONOLOGICAL_R1', 'frozen_at': now.isoformat(),
        'valid_from': '2026-10-16', 'train_through': selected['train_through'],
        'weights': selected['weights'], 'baseline_weights': dict(MATRIX_WEIGHTS),
        'speed_scale': 10., 'baseline_speed_gain': 1.5, 'engine_sha256': fingerprint(),
        'source_report_sha256': hashlib.sha256(results_path.read_bytes()).hexdigest(),
        'minimum_new_days': 30, 'minimum_races': 1000, 'minimum_speed_comparable_races': 200,
        'warning': 'Single fixed profile does not inherit six-window Gold+3/Good+5; not deployed.'}
    assert set(config['weights']) == {*DIMS, 'A'}
    assert abs(sum(config['weights'].values())-sum(MATRIX_WEIGHTS.values())) < 1e-8
    config['config_sha256'] = digest(config)
    return config


def validate_config(config):
    body = {k: v for k, v in config.items() if k != 'config_sha256'}
    if digest(body) != config.get('config_sha256'):
        raise ValueError('frozen config hash mismatch')
    if config['schema'] != 'au-speed-forward-v1' or not config['research_only']:
        raise ValueError('not a research shadow config')
    if config['engine_sha256'] != fingerprint() or config['baseline_weights'] != dict(MATRIX_WEIGHTS):
        raise ValueError('engine changed since freeze; new registration required')
    weights = config['weights']
    if set(weights) != {*DIMS, 'A'} or any(not math.isfinite(v) or v < 0 for v in weights.values()):
        raise ValueError('invalid weights')
    if abs(sum(weights.values())-sum(MATRIX_WEIGHTS.values())) > 1e-8:
        raise ValueError('weight sum changed')


def shadow(logic, config, bundle_path, now):
    validate_config(config)
    audit = logic.get('race_analysis', {}).get('full_time_speed', {})
    if audit.get('status') != 'ready' or audit.get('model_version') != MODEL_VERSION:
        raise ValueError('captured full-time evidence not ready')
    target = audit['target_date']
    predicted = stamp(audit['prediction_at'])
    captured = stamp(audit['captured_at'])
    frozen = stamp(config['frozen_at'])
    if not (frozen <= predicted <= now and captured <= predicted):
        raise ValueError('freeze/capture/prediction chronology invalid')
    if (target < config['valid_from'] or target <= now.astimezone(SYDNEY).date().isoformat()
            or predicted.astimezone(SYDNEY).date().isoformat() > target
            or config['train_through'] >= target):
        raise ValueError('target is not an eligible new pre-race day; same-day jump time is unverified')
    context = logic['race_analysis'].get('meeting_intelligence') or {}
    if context.get('date') != target:
        raise ValueError('meeting date differs from captured target')
    info = bundle_path.stat()
    bundle = read_bundle(str(bundle_path), info.st_mtime_ns, info.st_size)
    if (bundle['events_sha256'] != audit['source_hash'] or
            stamp(bundle['captured_at']) != captured or bundle['valid_from'] > target):
        raise ValueError('captured source bundle does not match prediction')
    if any(e['date'] >= target for e in bundle['events']):
        raise ValueError('source snapshot contains same/future-day events')
    result = {'schema': 'au-speed-forward-prediction-v1', 'research_only': True,
        'target_date': target, 'race_number': logic['race_analysis']['race_number'],
        'meeting': context.get('venue'), 'prediction_at': predicted.isoformat(),
        'recorded_at': now.isoformat(), 'config_sha256': config['config_sha256'],
        'input_sha256': digest(logic), 'source_sha256': bundle['events_sha256'], 'horses': []}
    # No result positions or odds are accessed anywhere in this scoring path.
    for number, horse in sorted(logic['horses'].items(), key=lambda x: int(x[0])):
        auto = horse['python_auto']
        detail = auto['full_time_speed_detail']
        if detail.get('model_version') != MODEL_VERSION:
            raise ValueError('horse time version mismatch')
        if detail.get('status') == 'observed' and detail.get('source_hash') != audit['source_hash']:
            raise ValueError('horse source mismatch')
        contribution = float(auto['full_time_speed_feature'])
        if not math.isfinite(contribution) or abs(contribution) > 4.5:
            raise ValueError('invalid captured speed contribution')
        if abs(contribution-float(detail.get('contribution', 0))) > 1e-6:
            raise ValueError('time detail/contribution mismatch')
        if detail.get('status') != 'observed' and contribution != 0:
            raise ValueError('missing evidence has nonzero speed')
        matrix = map_features_to_matrix_scores(auto['feature_scores'])
        wet, proof = float(auto['wet_form_feature']), float(auto['proven_class_feature'])
        pure = round(compose_matrix_score(matrix), 4)
        base = round(pure+wet+proof, 4)
        baseline = round(base+contribution, 4)
        if abs(baseline-float(auto['ability_score'])) > .000051:
            raise ValueError('captured baseline cannot be reproduced')
        delta = 0.
        for key in DIMS:
            delta += (matrix[key]-60)*config['weights'][key]
        delta += config['speed_scale']*(contribution/config['baseline_speed_gain'])*config['weights']['A']
        candidate = round(round(60+delta, 4)+wet+proof, 4)
        if not math.isfinite(candidate):
            raise ValueError('nonfinite shadow score')
        result['horses'].append({'number': int(number), 'name': horse['horse_name'],
            'baseline': baseline, 'candidate': candidate,
            'speed_observed': detail.get('status') == 'observed'})
    if len(result['horses']) < 4:
        raise ValueError('incomplete field')
    for key in ('baseline', 'candidate'):
        result[key+'_order'] = [h['number'] for h in sorted(result['horses'], key=lambda h: (-h[key], h['number']))]
    result['record_sha256'] = digest(result)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='action', required=True)
    f = sub.add_parser('freeze')
    f.add_argument('--results', type=Path, required=True)
    f.add_argument('--out', type=Path, required=True)
    s = sub.add_parser('capture')
    s.add_argument('--logic', type=Path, required=True)
    s.add_argument('--config', type=Path, required=True)
    s.add_argument('--bundle', type=Path, required=True)
    s.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    record = (freeze(args.results, now) if args.action == 'freeze' else
              shadow(json.loads(args.logic.read_text()), json.loads(args.config.read_text()), args.bundle, now))
    # Immutable create only: a second call cannot silently replace a prediction/config.
    with args.out.open('x') as handle:
        json.dump(record, handle, indent=2, allow_nan=False)
    print(args.out)


if __name__ == '__main__':
    main()
