#!/usr/bin/env python3
"""Read frozen Sportsbet Long Form caches; audit meanings, never score horses.

No fetcher is instantiated. Capture metadata and date filtering are diagnostics,
not a certificate that an archived page existed before its target race.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.agents/skills/au_racing'))
from claw_sportsbet_form import parse_runner_blocks, run_date, to_text, RE_TRIAL  # noqa: E402

FIELDS = ('winning_time', 'l600', 'margin', 'pos', 'field', 'settled', 'p1200', 'p800', 'p400')


def identity(run):
    h = run.get('header') or {}
    day = run_date(run)
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day or ''):
        return None
    try:
        datetime.fromisoformat(day)
        race, distance = int(h.get('race')), int(h.get('dist'))
    except (TypeError, ValueError):
        return None
    track = re.sub(r'^First\s+Start\s+', '', RE_TRIAL.sub('', h.get('track') or '').strip(), flags=re.I)
    if not track or race <= 0 or distance <= 0:
        return None
    # No fuzzy track aliases or surface folding in this audit.
    return track, day, race, distance


def prior_runs(runs, target):
    eligible = [(identity(r), r) for r in runs if not r.get('is_trial')]
    return [(k, r) for k, r in eligible if k is not None and k[1] < target]


def consistency(observations, field):
    """Keep distinct runner identities; never silently last-write conflicting values."""
    groups = defaultdict(lambda: defaultdict(set))
    for key, name, run in observations:
        value = run.get(field)
        if value not in (None, ''):
            groups[key][name].add(str(value))
    comparable, conflicts, repeats = 0, [], 0
    for key, names in sorted(groups.items()):
        if len(names) < 2:
            continue
        comparable += 1
        values = set.union(*names.values())
        if len(values) == 1:
            repeats += 1
        else:
            conflicts.append({'key': key, 'by_runner': {n: sorted(v) for n, v in names.items()}})
    return {'comparable_historical_races': comparable, 'same_value_races': repeats,
            'conflicting_races': len(conflicts), 'conflicts': conflicts}


def audit(mapping, cache, target_dates):
    rows, receipts, latest_records = [], [], []
    counts, raw, parsed_all, prior_present, latest_present, headers = (Counter() for _ in range(6))
    target_buckets = defaultdict(lambda: Counter())
    for meeting, meta in sorted(mapping.items()):
        if meta.get('date') not in target_dates:
            continue
        for race_id in meta['races']:
            counts['mapped_pages'] += 1
            url = f"https://www.sportsbetform.com.au/{meta['meetingId']}/{race_id}/"
            path = cache/(hashlib.sha1(url.encode()).hexdigest()+'.html')
            if not path.is_file():
                counts['missing_cache_pages'] += 1
                continue
            body = path.read_bytes()
            text = body.decode('utf-8')
            flat = to_text(text)
            receipts.append({'url': url, 'cache_path': str(path), 'sha256': hashlib.sha256(body).hexdigest(),
                'file_mtime_utc_diagnostic_only': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()})
            counts['cached_pages'] += 1
            raw['winning_time_labels'] += len(re.findall(r'Winning\s+Time\s+(?:\d+:)?\d+\.\d+', flat, re.I))
            raw['l600_labels'] += len(re.findall(r'Sectionals\s+600m\s+[\d.]+s', flat, re.I))
            raw['finished_labels'] += len(re.findall(r'\bFinished\s+', flat))
            for label in ('Finishing Time', 'Runner Time', 'Elapsed Time', 'FinishTime', 'L800', 'L400', 'L200'):
                raw[label] += len(re.findall(r'\b'+re.escape(label)+r'\b', flat, re.I))
            for block in parse_runner_blocks(text):
                counts['target_runner_blocks'] += 1
                runs = block.get('runs') or []
                counts['parsed_runs_all_including_trials_same_day'] += len(runs)
                for run in runs:
                    for field in FIELDS:
                        parsed_all[field] += run.get(field) not in (None, '')
                    for key, value in (run.get('header') or {}).items():
                        headers[key] += value not in (None, '')
                    counts['trial_runs_excluded'] += bool(run.get('is_trial'))
                    key = identity(run)
                    if not run.get('is_trial') and key is None:
                        counts['invalid_identity_runs_excluded'] += 1
                    if not run.get('is_trial') and key is not None and key[1] >= meta['date']:
                        counts['same_or_future_day_runs_excluded'] += 1
                prior = prior_runs(runs, meta['date'])
                for key, run in prior:
                    rows.append((key, block['name'], run))
                    counts['prior_formal_occurrences'] += 1
                    for field in FIELDS:
                        prior_present[field] += run.get(field) not in (None, '')
                if not prior:
                    counts['no_prior_formal_run_in_page'] += 1
                    continue
                latest_day = max(k[1] for k, _ in prior)
                latest = [(k, r) for k, r in prior if k[1] == latest_day]
                # Do not backfill an older observation or choose a conflicting latest.
                signatures = {json.dumps((k, r), sort_keys=True) for k, r in latest}
                if len(signatures) != 1:
                    counts['ambiguous_latest_formal_run'] += 1
                    continue
                key, run = latest[0]
                latest_records.append({'target_meeting': meeting, 'target_date': meta['date'],
                    'source_url': url, 'horse': block['name'], 'previous_key': key,
                    'fields': {f: run.get(f) for f in FIELDS}})
                counts['unique_latest_formal_run'] += 1
                for field in FIELDS:
                    latest_present[field] += run.get(field) not in (None, '')
                for field in ('winning_time', 'l600', 'p800', 'margin'):
                    target_buckets[meta['date']][field] += run.get(field) not in (None, '')
    if not receipts or not rows:
        raise ValueError('no usable Sportsbet cache corpus; cannot infer availability')
    ranges = {}
    for field in ('l600', 'margin', 'pos', 'field', 'p800', 'p400'):
        values = []
        for _, _, run in rows:
            match = re.match(r'([-+]?\d+(?:\.\d+)?)', str(run.get(field) or ''))
            if match:
                values.append(float(match[1]))
        ranges[field] = {'n': len(values), 'min': min(values) if values else None,
                         'median': statistics.median(values) if values else None,
                         'max': max(values) if values else None}
    return {'schema': 'sportsbet-time-inventory/v1', 'target_dates': sorted(target_dates),
        'scope': 'Read-only cached Long Form, not exhaustive Sportsbet mobile/API schema audit',
        'availability': 'FLAG: file mtime is not verified pre-race capture',
        'counts': counts, 'raw_labels': raw, 'parsed_all_presence': parsed_all,
        'prior_formal_occurrence_presence': prior_present, 'latest_formal_presence': latest_present,
        'header_presence_all_runs': headers, 'latest_by_target_date': target_buckets,
        'prior_formal_numeric_ranges': ranges, 'latest_records': latest_records,
        'same_race_consistency': {f: consistency(rows, f) for f in ('winning_time', 'l600')},
        'receipts': receipts,
        'prohibited_inferences': ['winning_time is not own runner time',
            'shared L600 does not certify any individual runner L600',
            'ordinal running position is not lengths behind',
            'race-level L600 clock reference is not certified compatible with winning_time',
            'no certified L800; cannot calculate individual total minus L800',
            'conflicting event clocks cannot be averaged or majority-filled'],
        'scoring_modified': False, 'performance_evaluation_run': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mapping', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--target-date', action='append', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    mapping_raw = args.mapping.read_bytes()
    result = audit(json.loads(mapping_raw), args.cache, set(args.target_date))
    result['mapping_sha256'] = hashlib.sha256(mapping_raw).hexdigest()
    result['code_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result['parser_sha256'] = hashlib.sha256((ROOT/'.agents/skills/au_racing/claw_sportsbet_form.py').read_bytes()).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ('counts', 'raw_labels', 'latest_formal_presence')}, indent=2))


if __name__ == '__main__':
    main()
