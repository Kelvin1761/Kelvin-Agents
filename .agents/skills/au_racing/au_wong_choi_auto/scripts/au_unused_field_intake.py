"""AU unused-field source inventory and prior-only speed reference fitting.

Source audit PASS must come from an independent audit. Hash/time validation here
cannot create historical availability evidence. No labels or rankings are used.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime
import hashlib
from pathlib import Path
import re
import statistics
from au_result_identity import normalize_venue_name


def _timestamp(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('source/cutoff timestamp requires explicit timezone')
    return result


def inventory(root):
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError('scored corpus root does not exist')
    meetings = {}; records = []
    for base in [root, root / 'Archive']:
        if not base.is_dir():
            continue
        for path in sorted(base.iterdir()):
            if not path.is_dir() or not re.match(r'^\d{4}-\d{2}-\d{2}', path.name):
                continue
            if path.name in meetings:
                raise ValueError('duplicate meeting identity across corpus roots')
            meetings[path.name] = path
            forms = sorted(path.glob('*Formguide.md'))
            depths = []
            for form in forms:
                text = form.read_text(encoding='utf-8', errors='replace')
                chunks = re.split(r'^\[\d+\].*?\(\d+\)\s*$', text, flags=re.M)[1:]
                depths.extend(len(re.findall(r'^.*?\sR\d+\s\d{4}-\d{2}-\d{2}\s+\d+m\s+cond:', chunk, re.M)) for chunk in chunks)
            records.append({'meeting': path.name, 'path': str(path), 'date': path.name[:10],
                            'archived': base != root, 'formguides': len(forms),
                            'meeting_scoring': (path / 'Meeting_Auto_Scoring.csv').is_file(),
                            'race_scoring_files': len(list(path.glob('Race_*_Auto_Scoring.csv'))),
                            'logic_files': len(list(path.glob('Race_*_Logic.json'))),
                            'runner_blocks': len(depths),
                            'observed_mean_form_depth': statistics.mean(depths) if depths else None,
                            'depth_kind': 'parsed history count; not PIT certification'})
    return {'schema': 'au-unused-field-inventory/v1', 'root': str(root), 'meetings': records,
            'counts': {'meetings': len(records), 'archived': sum(x['archived'] for x in records),
                       'with_formguides': sum(bool(x['formguides']) for x in records),
                       'with_any_scoring': sum(x['meeting_scoring'] or bool(x['race_scoring_files']) for x in records)},
            'limits': ['No stale meeting-id mapping or source_compare file required for inventory.',
                       'Observed depth is not evidence of field availability at prediction time.',
                       'No labels, AUC, feature selection, market data or candidate scoring computed.']}


def fit_speed_standards(sources, prediction_at):
    cutoff = _timestamp(prediction_at); events = defaultdict(set); flags = []; accepted = []
    paths = [str(Path(x['path']).resolve()) for x in sources]
    if len(paths) != len(set(paths)):
        raise ValueError('duplicate standard source path')
    for source in sources:
        path = Path(source['path'])
        if source.get('audit') != 'PASS':
            flags.append({'path': str(path), 'reason': 'source_audit_not_passed'}); continue
        available = _timestamp(source['available_at'])
        if available >= cutoff:
            flags.append({'path': str(path), 'reason': 'source_not_before_cutoff'}); continue
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != source['sha256']:
            raise ValueError('standard source hash changed')
        accepted.append(dict(source))
        for line in body.decode('utf-8').splitlines():
            if '**(TRIAL)**' in line:
                continue
            match = re.match(r'^(\S.*?)\sR(\d+)\s(\d{4}-\d{2}-\d{2})\s+(\d+)m\s+cond:(\S+)', line)
            timing = re.search(r'WinningTime:(?:(\d+):)?([\d.]+)', line)
            if not match or not timing or match[3] >= cutoff.date().isoformat():
                continue
            seconds = (int(timing[1]) * 60 if timing[1] else 0) + float(timing[2])
            if not 25 < seconds < 260:
                continue
            key = (normalize_venue_name(match[1]), int(match[2]), match[3], int(match[4]))
            events[key].add((seconds, match[5]))
        if path.read_bytes() != body:
            raise ValueError('standard source changed during read')
    per = defaultdict(list)
    for event, values in events.items():
        if len(values) != 1:
            flags.append({'event': event, 'reason': 'conflicting_event_time_or_going'}); continue
        per[(event[0], event[3])].append(next(iter(values)))
    standard = {key: statistics.median(x[0] for x in values) for key, values in per.items() if len(values) >= 10}
    residuals = defaultdict(list)
    for key, values in per.items():
        if key in standard:
            for seconds, condition in values:
                residuals[condition].append(seconds - standard[key])
    going = {key: statistics.median(values) for key, values in residuals.items() if len(values) >= 40}
    return {'cutoff': prediction_at, 'standard': standard, 'going': going, 'unique_events': len(events),
            'accepted_sources': accepted, 'flags': flags,
            'availability_scope': 'independent source audit required; not certified by this fitter'}
